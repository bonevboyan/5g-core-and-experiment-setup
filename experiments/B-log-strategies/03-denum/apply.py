#!/usr/bin/env python3
"""
B-log-strategies/03-denum/apply.py

Apply Denum compression to a Loki CSV log file and record metrics.

Denum achieves high compression by specialised handling of numeric tokens:
  - IP addresses     → combined integer, delta-encoded
  - Timestamps       → combined integer, delta-encoded
  - Other numbers    → grouped by digit-length, stored as binary sequences
  - String/template  → dictionary-encoded, then lzma-compressed
"""

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
from collections import defaultdict
from pathlib import Path

import pyppmd
import regex as re

SCRIPT_DIR = Path(__file__).parent
B_DIR      = SCRIPT_DIR.parent
LIB_DIR    = B_DIR / "lib"

sys.path.insert(0, str(LIB_DIR))
from measure_overhead import ResourceTracker, time_linear_scan, count_lines, dir_bytes

# ──────────────────────────────────────────────────────────────────────────────
# Numeric patterns for Open5GS logs
# ──────────────────────────────────────────────────────────────────────────────

_ip_pat  = re.compile(r'(\d+)\.(\d+)\.(\d+)\.(\d+)')
_ts_ms   = re.compile(r'(\d+):(\d+):(\d+)\.(\d+)')   # HH:MM:SS.mmm
_ts_hms  = re.compile(r'(\d+):(\d+):(\d+)')           # HH:MM:SS
_ts_hm   = re.compile(r'(\d+):(\d+)')                 # HH:MM or date-part
_num_pat = re.compile(r'(?<![a-zA-Z0-9])\d+(?![a-zA-Z0-9])')
_alpha   = 'abcdefghijklmnopqrstuvwxyz'


def _replace_and_group(lst: list[str]) -> tuple[list[str], dict]:
    patterns: dict = defaultdict(list)
    replaced: list = []

    def _combine_ip(m):
        nums = re.findall(r'\d+', m.group())
        patterns['<I>'].append(int(''.join(n.zfill(3) for n in nums)))
        return '<I>'

    def _combine(key, m):
        nums = re.findall(r'\d+', m.group())
        patterns[key].append(int(''.join(nums)))
        return key

    def _num_replace(m):
        num = m.group()
        if len(num) >= 15:
            return num
        idx = min(len(num) - 1, len(_alpha) - 1)
        key = f'<{_alpha[idx]}>'
        patterns[key].append(num)
        return key

    for item in lst:
        s = _ip_pat.sub(_combine_ip, item)
        s = _ts_ms.sub(lambda m: _combine('<TT>', m), s)
        s = _ts_hms.sub(lambda m: _combine('<T>', m), s)
        s = _ts_hm.sub(lambda m: _combine('<TT>', m), s)
        s = _num_pat.sub(_num_replace, s)
        replaced.append(s)

    return replaced, dict(patterns)


def _zigzag_enc(n: int) -> int:
    return (n << 1) ^ (n >> 63)


def _elastic_enc(n: int) -> bytes:
    cur = _zigzag_enc(n)
    buf = b''
    while True:
        if cur < 0x80:
            buf += bytes([cur])
            break
        buf += bytes([(cur & 0x7F) | 0x80])
        cur >>= 7
    return buf


def _delta_transform(nums: list) -> list:
    if not nums:
        return []
    out = [int(nums[0])]
    last = int(nums[0])
    for v in nums[1:]:
        out.append(int(v) - last)
        last = int(v)
    return out


def _compress_chunk(chunk: list[str], chunk_dir: Path):
    chunk_dir.mkdir(parents=True, exist_ok=True)
    lzma_dir = chunk_dir / "lzma"
    ppmd_dir = chunk_dir / "PPMd"
    lzma_dir.mkdir(exist_ok=True)
    ppmd_dir.mkdir(exist_ok=True)

    templates, num_groups = _replace_and_group(chunk)

    DELTA_KEYS = {'<I>', '<T>', '<TT>'}
    for key, vals in num_groups.items():
        label = key.strip('<>')
        fname = lzma_dir / f"_{label}_.bin"
        with open(fname, 'ab') as f:
            if key in DELTA_KEYS:
                for v in _delta_transform(vals):
                    f.write(_elastic_enc(v))
            else:
                for v in vals:
                    try:
                        f.write(_elastic_enc(int(v)))
                    except (ValueError, OverflowError):
                        pass

    variable_set: list[str] = []
    final_templates: list[str] = []
    digit_re = re.compile(r'\d')
    for tmpl in templates:
        parts   = re.split(r'(\s+)', tmpl)
        cleaned = ''
        for part in parts:
            if digit_re.search(part) and not part.startswith('<'):
                variable_set.append(part)
                cleaned += '<*>'
            else:
                cleaned += part
        final_templates.append(cleaned)

    var_to_id: dict = {}
    var_id = 1
    var_ids: list[int] = []
    for v in variable_set:
        if v not in var_to_id:
            var_to_id[v] = var_id
            var_id += 1
        var_ids.append(var_to_id[v])

    with open(lzma_dir / "variablesetmapping.txt", 'a', encoding='ISO-8859-1') as f:
        for v in var_to_id:
            f.write(v + '\n')
    with open(lzma_dir / "variablesetids.bin", 'ab') as f:
        for vid in var_ids:
            f.write(_elastic_enc(vid))

    tmpl_to_id: dict = {}
    tmpl_id = 1
    tmpl_ids: list[int] = []
    for t in final_templates:
        if t not in tmpl_to_id:
            tmpl_to_id[t] = tmpl_id
            tmpl_id += 1
        tmpl_ids.append(tmpl_to_id[t])

    with open(lzma_dir / "allmapping.txt", 'a', encoding='ISO-8859-1') as f:
        for t in tmpl_to_id:
            f.write(t + '\n')
    with open(lzma_dir / "allids.bin", 'ab') as f:
        for tid in tmpl_ids:
            f.write(_elastic_enc(tid))

    _compress_dir_lzma(lzma_dir)
    _compress_dir_ppmd(ppmd_dir, lzma_dir)


def _compress_dir_lzma(d: Path):
    files = [p for p in d.iterdir() if p.is_file() and p.suffix != '.xz']
    if not files:
        return
    with tarfile.open(str(d / "temp.tar.xz"), "w:xz") as tar:
        for fp in files:
            tar.add(str(fp), arcname=fp.name)
    for fp in files:
        fp.unlink()


def _compress_dir_ppmd(ppmd_dir: Path, source_dir: Path):
    mappings = [p for p in source_dir.iterdir() if p.suffix == '.txt']
    if not mappings:
        return
    tar_path = ppmd_dir / "temp.tar"
    with tarfile.open(str(tar_path), "w") as tar:
        for fp in mappings:
            tar.add(str(fp), arcname=fp.name)
    with open(tar_path, 'rb') as fin:
        data = fin.read()
    compressed = pyppmd.Ppmd8Encoder(6, 16 << 20).encode(data)
    with open(ppmd_dir / "temp.ppmd", 'wb') as fout:
        fout.write(compressed)
    tar_path.unlink()


CHUNK_SIZE = 100_000


def compress_log(log_path: Path, output_dir: Path) -> int:
    with open(log_path, 'r', encoding='ISO-8859-1') as f:
        all_lines = f.readlines()

    chunks = [all_lines[i:i + CHUNK_SIZE]
              for i in range(0, len(all_lines), CHUNK_SIZE)]
    for chunk_id, chunk in enumerate(chunks, start=1):
        _compress_chunk(chunk, output_dir / str(chunk_id))

    return len(all_lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv",      required=True)
    ap.add_argument("--outdir",   required=True)
    ap.add_argument("--scenario", default="unknown")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    out_dir  = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_bytes = csv_path.stat().st_size

    log_path = out_dir / "Open5GS.log"
    subprocess.run(
        [sys.executable, str(LIB_DIR / "extract_lines.py"),
         "--csv", str(csv_path), "--out", str(log_path)],
        check=True,
    )

    n_lines   = count_lines(log_path)
    log_bytes = log_path.stat().st_size

    compressed_dir = out_dir / "compressed"

    print(f"[denum] input: {n_lines} lines, "
          f"{log_bytes / 1024:.1f} KB (log), {csv_bytes / 1024:.1f} KB (csv)")

    if compressed_dir.exists():
        shutil.rmtree(compressed_dir)

    with ResourceTracker() as rt:
        compress_log(log_path, compressed_dir)

    print(f"  [denum] wall={rt.wall_s:.3f}s  mem={rt.peak_mem_mb:.0f}MB")

    out_bytes = dir_bytes(compressed_dir)

    if out_bytes == 0:
        compression_ratio   = float("nan")
        reduction_pct       = float("nan")
        corpus_coverage_pct = float("nan")
    else:
        compression_ratio   = log_bytes / out_bytes
        reduction_pct       = (1.0 - out_bytes / log_bytes) * 100.0
        corpus_coverage_pct = log_bytes / csv_bytes * 100.0

    throughput_mb_s = (log_bytes / 1024 / 1024) / rt.wall_s if rt.wall_s > 0 else 0.0

    _, query_latency    = time_linear_scan(log_path)
    total_query_latency = rt.wall_s + query_latency

    metrics = {
        "strategy":               "denum",
        "scenario":               args.scenario,
        "input_lines":            n_lines,
        "input_log_bytes":        log_bytes,
        "input_csv_bytes":        csv_bytes,
        "corpus_coverage_pct":    round(corpus_coverage_pct, 2),
        "output_bytes":           out_bytes,
        "compression_ratio":      round(compression_ratio, 3),
        "reduction_pct":          round(reduction_pct, 2),
        "throughput_mb_s":        round(throughput_mb_s, 3),
        "decompression_required": True,
        "wall_s":                 round(rt.wall_s, 3),
        "cpu_s":                  round(rt.cpu_s, 3),
        "peak_mem_mb":            round(rt.peak_mem_mb, 1),
        "query_latency_s":        round(query_latency, 4),
        "total_query_latency_s":  round(total_query_latency, 4),
    }

    metrics_path = out_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"[denum] ratio={compression_ratio:.2f}x  "
          f"reduction={reduction_pct:.1f}%  "
          f"wall={rt.wall_s:.3f}s  mem={rt.peak_mem_mb:.0f}MB")
    print(f"[denum] metrics → {metrics_path}")


if __name__ == "__main__":
    main()
