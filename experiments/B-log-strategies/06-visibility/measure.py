#!/usr/bin/env python3
"""
B-log-strategies/06-visibility/measure.py

Measure retained visibility for each reduction strategy.

"Visibility" = ability to recover fault-related events after applying a strategy.

Three complementary metrics per strategy:

  fault_line_retention_pct
    Fraction of keyword-matched fault lines from the original that survive.
    Works for all scenarios; uses heuristic keywords (ERROR, CRITICAL, etc.).

  fault_window_retention_pct
    Fraction of all log lines from the fault injection window (per timeline.json)
    that survive.  Only available for fault scenarios; set to null otherwise.
    This is a ground-truth metric: we know exactly when chaos was injected.

  total_retention_pct
    Overall fraction of log lines retained regardless of content.

For lossless strategies (LogShrink, Denum) the filtered_csv is absent; all
three metrics are 100% by definition because the compressed artifact preserves
every byte of the original.
"""

import argparse
import csv
import json
import re
from pathlib import Path

ANSI_RE        = re.compile(r'\x1b\[[0-9;]*[mABCDEFGHJKSTfnihlp]')
FAULT_LEVEL_RE = re.compile(r'\]\s+(ERROR|CRITICAL|FATAL):', re.IGNORECASE)
FAULT_KW_RE    = re.compile(
    r'\b(error|exception|refused|failed|fatal|oom|killed|crash|abort|'
    r'timeout|reject|unreachable|cannot|unable|denied|panic)\b',
    re.IGNORECASE,
)
GO_LEVEL_RE = re.compile(r'(?:^|\s)level=(\w+)', re.IGNORECASE)

_VAR_PATS_VIS = [
    re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.IGNORECASE),
    re.compile(r'\d+\.\d+\.\d+\.\d+(:\d+)?'),
    re.compile(r'0x[0-9a-fA-F]+'),
    re.compile(r'imsi-\S+'),
    re.compile(r'suci-\S+'),
    re.compile(r'\(\.\./[^)]+\)'),
    re.compile(r'\b\d+\b'),
]


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def is_fault_line(line: str) -> bool:
    line = strip_ansi(line)
    lm = GO_LEVEL_RE.search(line)
    if lm and lm.group(1).upper() in ("DEBUG", "INFO"):
        return False
    return bool(FAULT_LEVEL_RE.search(line) or FAULT_KW_RE.search(line))


def make_template_vis(line: str) -> str:
    t = line
    for pat in _VAR_PATS_VIS:
        t = pat.sub('<*>', t)
    return re.sub(r'(<\*>\s*)+', '<*> ', t).strip()


def load_csv_rows(csv_path: Path) -> list[dict]:
    """Load rows as {ts_ns, line} dicts."""
    rows = []
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "ts_ns": int(row.get("timestamp_ns", 0)),
                "line":  strip_ansi(row.get("line", "")),
            })
    return rows


def load_timeline(timeline_path: Path) -> dict | None:
    if not timeline_path.exists():
        return None
    with open(timeline_path) as f:
        return json.load(f)


def measure_visibility(
    original_rows: list[dict],
    filtered_rows: list[dict] | None,
    timeline: dict | None,
) -> dict:
    """
    Compute visibility metrics.

    If filtered_rows is None (lossless), all original rows are treated as retained.
    If timeline is provided, also compute fault_window_retention_pct.
    """
    retained = filtered_rows if filtered_rows is not None else original_rows

    in_lines  = len(original_rows)
    out_lines = len(retained)
    in_fault  = sum(1 for r in original_rows if is_fault_line(r["line"]))
    out_fault = sum(1 for r in retained        if is_fault_line(r["line"]))

    in_fault_templates  = {make_template_vis(r["line"]) for r in original_rows if is_fault_line(r["line"])}
    out_fault_templates = {make_template_vis(r["line"]) for r in retained       if is_fault_line(r["line"])}
    retained_templates  = in_fault_templates & out_fault_templates

    total_ret  = (out_lines / in_lines * 100.0) if in_lines else 100.0
    fault_ret  = (out_fault / in_fault * 100.0) if in_fault else 100.0
    tmpl_ret   = (len(retained_templates) / len(in_fault_templates) * 100.0
                  if in_fault_templates else 100.0)

    result: dict = {
        "input_total_lines":            in_lines,
        "output_total_lines":           out_lines,
        "input_fault_lines":            in_fault,
        "output_fault_lines":           out_fault,
        "input_fault_templates":        len(in_fault_templates),
        "retained_fault_templates":     len(retained_templates),
        "total_retention_pct":          round(total_ret, 2),
        "fault_line_retention_pct":     round(fault_ret, 2),
        "fault_template_retention_pct": round(tmpl_ret, 2),
        "fault_visibility_pct":         round(fault_ret, 2),
        "fault_window_retention_pct":   None,
    }

    if timeline is not None:
        try:
            fault_start_ns = int(timeline["fault"]["start"]) * 1_000_000_000
            fault_end_ns   = int(timeline["fault"]["end"])   * 1_000_000_000

            in_window  = [r for r in original_rows if fault_start_ns <= r["ts_ns"] <= fault_end_ns]
            out_window = [r for r in retained       if fault_start_ns <= r["ts_ns"] <= fault_end_ns]

            if in_window:
                window_ret = len(out_window) / len(in_window) * 100.0
                result["fault_window_retention_pct"] = round(window_ret, 2)
                result["fault_window_total_lines"]   = len(in_window)
                result["fault_window_retained_lines"] = len(out_window)
        except (KeyError, TypeError, ValueError):
            pass

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--original",          required=True,
                    help="Path to all_logs.csv (baseline)")
    ap.add_argument("--timeline",          default=None,
                    help="Path to timeline.json for fault-window metric")
    ap.add_argument("--logshrink-dir",     default=None)
    ap.add_argument("--denum-dir",         default=None)
    ap.add_argument("--salo-dir",          default=None)
    ap.add_argument("--preprocessing-dir", default=None)
    ap.add_argument("--outdir",            required=True)
    ap.add_argument("--scenario",          default="unknown")
    args = ap.parse_args()

    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    original_rows = load_csv_rows(Path(args.original))
    timeline      = load_timeline(Path(args.timeline)) if args.timeline else None

    in_fault = sum(1 for r in original_rows if is_fault_line(r["line"]))
    print(f"[visibility] original: {len(original_rows)} lines, {in_fault} fault lines")

    results: dict = {"scenario": args.scenario, "strategies": {}}

    for strat, strat_dir in [("logshrink", args.logshrink_dir),
                              ("denum",     args.denum_dir)]:
        if strat_dir is None:
            continue
        results["strategies"][strat] = measure_visibility(original_rows, None, timeline)

    for strat, strat_dir in [("salo",         args.salo_dir),
                              ("preprocessing", args.preprocessing_dir)]:
        if strat_dir is None:
            continue
        filtered_csv = Path(strat_dir) / "filtered.csv"
        if not filtered_csv.exists():
            print(f"  [{strat}] filtered.csv not found — skipping")
            continue
        filtered_rows = load_csv_rows(filtered_csv)
        results["strategies"][strat] = measure_visibility(original_rows, filtered_rows, timeline)

    for strat, data in results["strategies"].items():
        fv  = data.get("fault_visibility_pct", "?")
        tr  = data.get("total_retention_pct", "?")
        fwr = data.get("fault_window_retention_pct")
        fwr_str = f"  fault_window={fwr}%" if fwr is not None else ""
        print(f"  [{strat}] fault_visibility={fv}%  total_retention={tr}%{fwr_str}")

    metrics_path = out_dir / "visibility_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[visibility] → {metrics_path}")


if __name__ == "__main__":
    main()
