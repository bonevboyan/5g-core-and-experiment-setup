#!/usr/bin/env python3
"""
B-log-strategies/02-logshrink/apply.py

Apply LogShrink compression to a Loki CSV log file and record metrics.

LogShrink compresses logs by:
  1. Training a template model on sampled lines (Drain-based parser + LCS analysis)
  2. Encoding log events as (template_id, variable_values) column-oriented storage
  3. Applying gzip as the final-pass kernel compressor
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
B_DIR      = SCRIPT_DIR.parent
REPOS      = B_DIR / "cloned_repos"
LIB_DIR    = B_DIR / "lib"
LOGSHRINK  = REPOS / "LogShrink" / "python_compression"

sys.path.insert(0, str(LIB_DIR))
from measure_overhead import ResourceTracker, time_linear_scan, count_lines, dir_bytes

DS            = "Open5GS"
HEADER_LENGTH = 4
WINDOW        = 50
THRESHOLD     = 10
N_CANDIDATE   = 16
KERNEL        = "gzip"


def run_logshrink(log_path: Path, out_dir: Path) -> int:
    """Run LogShrink on log_path. Returns compressed_bytes."""
    with tempfile.TemporaryDirectory(prefix="logshrink_in_") as tmpdir:
        ds_dir = Path(tmpdir) / DS
        ds_dir.mkdir()
        shutil.copy2(log_path, ds_dir / f"{DS}.log")

        template_dir = LOGSHRINK / "template" / DS
        template_dir.mkdir(parents=True, exist_ok=True)

        compressed_dir = out_dir / "compressed"
        compressed_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable, "run.py",
            "-I",   tmpdir + "/",
            "-ds",  DS,
            "-E",   "E",
            "-C",
            "-K",   KERNEL,
            "-V",
            "-P",
            "-S",
            "-wh",  str(WINDOW),
            "-th",  str(THRESHOLD),
            "-NC",  str(N_CANDIDATE),
            "-L",   str(HEADER_LENGTH),
            "-outdir", str(compressed_dir),
        ]

        proc = subprocess.Popen(cmd, cwd=str(LOGSHRINK),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        _stdout, stderr = proc.communicate()

        compressed_bytes = dir_bytes(compressed_dir)

        if proc.returncode != 0:
            if "ZeroDivisionError" in stderr and compressed_bytes > 0:
                pass 
            else:
                print("[logshrink] STDERR:", stderr[-2000:], file=sys.stderr)
                raise RuntimeError(f"LogShrink failed (rc={proc.returncode})")

        return compressed_bytes


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

    log_path = out_dir / f"{DS}.log"
    subprocess.run(
        [sys.executable, str(LIB_DIR / "extract_lines.py"),
         "--csv", str(csv_path), "--out", str(log_path)],
        check=True,
    )

    n_lines   = count_lines(log_path)
    log_bytes = log_path.stat().st_size

    print(f"[logshrink] input: {n_lines} lines, "
          f"{log_bytes / 1024:.1f} KB (log), {csv_bytes / 1024:.1f} KB (csv)")

    compressed_dir = out_dir / "compressed"
    if compressed_dir.exists():
        shutil.rmtree(compressed_dir)

    with ResourceTracker() as rt:
        out_bytes = run_logshrink(log_path, out_dir)

    print(f"  [logshrink] wall={rt.wall_s:.2f}s  mem={rt.peak_mem_mb:.0f}MB")

    if out_bytes == 0:
        print("[logshrink] WARNING: compressed output empty", file=sys.stderr)
        compression_ratio   = float("nan")
        reduction_pct       = float("nan")
        corpus_coverage_pct = float("nan")
    else:
        # Compare against the corpus log bytes (Open5GS NFs + UERANSIM), not the
        # full Loki CSV which also contains excluded apps (mongodb, beyla).
        compression_ratio   = log_bytes / out_bytes
        reduction_pct       = (1.0 - out_bytes / log_bytes) * 100.0
        corpus_coverage_pct = log_bytes / csv_bytes * 100.0

    throughput_mb_s = (log_bytes / 1024 / 1024) / rt.wall_s if rt.wall_s > 0 else 0.0

    _, query_latency    = time_linear_scan(log_path)
    total_query_latency = rt.wall_s + query_latency

    metrics = {
        "strategy":               "logshrink",
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

    print(f"[logshrink] ratio={compression_ratio:.2f}x  "
          f"reduction={reduction_pct:.1f}%  "
          f"wall={rt.wall_s:.2f}s  mem={rt.peak_mem_mb:.0f}MB")
    print(f"[logshrink] metrics → {metrics_path}")


if __name__ == "__main__":
    main()
