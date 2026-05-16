#!/usr/bin/env python3
"""
B-log-strategies/04-salo/apply.py

Selective Adaptive Log Observability

Two-level selection:
Level 1 — Location priority (static per NF type):
  Core NFs (AMF, SMF, UPF, NRF):       keep WARNING+ events and rare templates
  Support NFs (UDM, UDR, PCF, ...):    keep ERROR+ events in steady state
  Infrastructure / unknown:             keep ERROR+ events in steady state
Level 2 — Necessity score (adaptive):
  A log event is necessary when any of these hold:
    (a) Its level meets the location-tier threshold (always collected)
    (b) Its log template is "rare" (< RARITY_THRESHOLD fraction of windows)
    (c) Its NF is currently flagged as unhealthy (collect ALL logs)

Adaptive flagging:
  An NF is flagged when its ERROR count in a 60-second window reaches
  ERROR_FLAG_THRESHOLD. 
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
B_DIR      = SCRIPT_DIR.parent
LIB_DIR    = B_DIR / "lib"
sys.path.insert(0, str(LIB_DIR))

from measure_overhead import ResourceTracker, time_linear_scan

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

WINDOW_SECS          = 60   # seconds per health-assessment window
ERROR_FLAG_THRESHOLD = 5   # ERROR events per window required to flag an NF
LOOKFORWARD_WINDOWS  = 2    # extra windows kept flagged after error burst ends

LEVEL_ORDER = {
    "DEBUG": 0, "INFO": 1,
    "WARNING": 2, "WARN": 2,
    "ERROR": 3, "CRITICAL": 4, "FATAL": 4,
}

CORE_NFS    = {"amf", "smf", "upf", "nrf"}
SUPPORT_NFS = {"udm", "udr", "pcf", "ausf", "bsf", "nssf"}

# Minimum severity to keep when NF is healthy 
TIER_THRESHOLD = {
    "core":           LEVEL_ORDER["WARNING"],
    "support":        LEVEL_ORDER["ERROR"],
    "infrastructure": LEVEL_ORDER["ERROR"],
    "unknown":        LEVEL_ORDER["ERROR"],
}

# Template appearing in fewer than this fraction of windows is treated as rare
RARITY_THRESHOLD = 0.05

ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mABCDEFGHJKSTfnihlp]')
LOG_RE  = re.compile(
    r'^(?P<date>\d{2}/\d{2})\s+'
    r'(?P<time>\d{2}:\d{2}:\d{2}\.\d+):\s+'
    r'\[(?P<component>[^\]]+)\]\s+'
    r'(?P<level>\w+):\s*'
    r'(?P<message>.*)',
    re.DOTALL,
)
_VAR_PATS = [
    re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.IGNORECASE),
    re.compile(r'\d+\.\d+\.\d+\.\d+(:\d+)?'),
    re.compile(r'imsi-\S+'),
    re.compile(r'suci-\S+'),
    re.compile(r'\bsupi-\S+'),
    re.compile(r'0x[0-9a-fA-F]+'),
    re.compile(r'\b\d+\b'),
]


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def location_tier(app: str) -> str:
    a = app.lower()
    if a in CORE_NFS:
        return "core"
    if a in SUPPORT_NFS:
        return "support"
    if "mongo" in a or "db" in a:
        return "infrastructure"
    return "unknown"


def make_template(msg: str) -> str:
    t = msg
    for pat in _VAR_PATS:
        t = pat.sub("<*>", t)
    return re.sub(r'(<\*>\s*)+', '<*> ', t).strip()


def parse_row(row: dict) -> dict:
    ts_ns  = int(row.get("timestamp_ns", 0))
    pod    = row.get("pod", "")
    app    = row.get("app", "") or (pod.split("-")[0] if pod else "unknown")
    line   = strip_ansi(row.get("line", "")).strip()
    window = (ts_ns // 1_000_000_000) // WINDOW_SECS

    m = LOG_RE.match(line)
    if m:
        level = m.group("level").upper()
        tmpl  = make_template(m.group("message"))
    else:
        level = "INFO"
        tmpl  = make_template(line)

    return {
        "ts_ns":    ts_ns,
        "pod":      pod,
        "app":      app,
        "line":     line,
        "level":    level,
        "lev_ord":  LEVEL_ORDER.get(level, 1),
        "template": tmpl,
        "window":   window,
    }


def load_csv(csv_path: Path) -> list[dict]:
    rows = []
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(parse_row(row))
    return rows


def compute_rare_templates(rows: list[dict]) -> set:
    """Templates appearing in < RARITY_THRESHOLD fraction of windows are rare."""
    tmpl_windows: dict = defaultdict(set)
    all_windows: set   = set()
    for r in rows:
        tmpl_windows[r["template"]].add(r["window"])
        all_windows.add(r["window"])

    n = len(all_windows)
    if n == 0:
        return set()
    return {t for t, wins in tmpl_windows.items() if len(wins) / n < RARITY_THRESHOLD}


def compute_flagged_windows(rows: list[dict]) -> set:
    """
    (app, window) pairs where full collection applies.
    Flagging is triggered by ERROR bursts and propagates LOOKFORWARD_WINDOWS forward.
    """
    error_counts: dict = defaultdict(int)
    for r in rows:
        if r["lev_ord"] >= LEVEL_ORDER["ERROR"]:
            error_counts[(r["app"], r["window"])] += 1

    triggering: dict = defaultdict(set)
    for (app, win), cnt in error_counts.items():
        if cnt >= ERROR_FLAG_THRESHOLD:
            triggering[app].add(win)

    flagged: set = set()
    for app, wins in triggering.items():
        for win in wins:
            for offset in range(LOOKFORWARD_WINDOWS + 1):
                flagged.add((app, win + offset))
    return flagged


def apply_salo(rows: list[dict], rare_templates: set, flagged: set) -> list[dict]:
    kept = []
    for r in rows:
        if (r["app"], r["window"]) in flagged:
            kept.append(r)
            continue
        threshold = TIER_THRESHOLD[location_tier(r["app"])]
        if r["lev_ord"] >= threshold or r["template"] in rare_templates:
            kept.append(r)
    return kept


def write_filtered_csv(rows: list[dict], out_path: Path):
    fieldnames = ["timestamp_ns", "pod", "app", "line"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "timestamp_ns": r["ts_ns"],
                "pod":          r["pod"],
                "app":          r["app"],
                "line":         r["line"],
            })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv",      required=True)
    ap.add_argument("--outdir",   required=True)
    ap.add_argument("--scenario", default="unknown")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    out_dir  = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    in_bytes = csv_path.stat().st_size
    print(f"[salo] loading {csv_path} ({in_bytes / 1024:.1f} KB) ...")

    with ResourceTracker() as rt:
        rows           = load_csv(csv_path)
        rare_templates = compute_rare_templates(rows)
        flagged        = compute_flagged_windows(rows)
        kept           = apply_salo(rows, rare_templates, flagged)

    in_lines  = len(rows)
    out_lines = len(kept)

    filtered_path = out_dir / "filtered.csv"
    write_filtered_csv(kept, filtered_path)
    out_bytes = filtered_path.stat().st_size

    reduction_pct = (1.0 - out_lines / in_lines) * 100.0 if in_lines else 0.0
    storage_ratio = in_bytes / out_bytes if out_bytes else float("nan")

    _, query_latency_s = time_linear_scan(filtered_path)

    metrics = {
        "strategy": "salo",
        "scenario": args.scenario,
        "config": {
            "window_secs":          WINDOW_SECS,
            "error_flag_threshold": ERROR_FLAG_THRESHOLD,
            "lookforward_windows":  LOOKFORWARD_WINDOWS,
            "rarity_threshold":     RARITY_THRESHOLD,
            "core_nfs":             sorted(CORE_NFS),
            "support_nfs":          sorted(SUPPORT_NFS),
        },
        "input_lines":            in_lines,
        "output_lines":           out_lines,
        "input_csv_bytes":        in_bytes,
        "output_bytes":           out_bytes,
        "reduction_pct":          round(reduction_pct, 2),
        "storage_ratio":          round(storage_ratio, 3),
        "nf_flagged_windows":     len(flagged),
        "rare_templates_kept":    len(rare_templates),
        "decompression_required": False,
        "query_latency_s":        round(query_latency_s, 4),
        "total_query_latency_s":  round(query_latency_s, 4),
        **rt.to_dict(),
    }

    metrics_path = out_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"[salo] {in_lines} → {out_lines} lines  "
          f"reduction={reduction_pct:.1f}%  "
          f"wall={rt.wall_s:.1f}s  mem={rt.peak_mem_mb:.0f}MB  "
          f"query={query_latency_s:.3f}s")
    print(f"[salo] metrics → {metrics_path}")


if __name__ == "__main__":
    main()
