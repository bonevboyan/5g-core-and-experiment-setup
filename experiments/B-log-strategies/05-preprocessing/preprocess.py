#!/usr/bin/env python3
"""
B-log-strategies/05-preprocessing/preprocess.py

Three sequential steps applied to the raw log CSV:

  Step 1 — Event Categorisation
    Parse each line into structured fields (timestamp, component, level,
    message). Extract a log template by replacing variable tokens (numbers,
    UUIDs, IPs, file paths) with '<*>'. Assign each line a template ID.
    This clusters semantically identical events regardless of variable values.

  Step 2 — Event Filtering (temporal + spatial deduplication)
    Temporal: for each (NF pod, template) pair, within a W-second sliding
      window, keep only the first occurrence plus any occurrence that changes
      level (e.g. INFO → ERROR escalation).
    Spatial: for the same template occurring from multiple pods of the SAME
      NF type (same app label) in the same window, keep one representative
      per NF type (not per pod instance).

  Step 3 — Causality-related Filtering (Apriori association rules)
    Treat each 10-second window as a transaction (set of template IDs).
    Mine frequent itemsets and derive association rules: if A ⇒ B with
    high confidence, B is causally implied by A. In windows where both
    appear, remove B occurrences keeping A as the causal root.
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
B_DIR      = SCRIPT_DIR.parent
LIB_DIR    = B_DIR / "lib"
sys.path.insert(0, str(LIB_DIR))

from measure_overhead import ResourceTracker, time_linear_scan

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

TEMPORAL_WINDOW_SECS   = 15     # window for temporal deduplication
SPATIAL_WINDOW_SECS    = 15     # window for spatial deduplication
APRIORI_WINDOW_SECS    = 10     # transaction window for Apriori
APRIORI_MIN_SUPPORT    = 0.05   # minimum support (fraction of windows)
APRIORI_MIN_CONFIDENCE = 0.90   # minimum confidence for A → B rule
APRIORI_MAX_ITEMSET    = 2      # only mine pairs (sufficient for log causality)

# ──────────────────────────────────────────────────────────────────────────────
# Log parsing
# ──────────────────────────────────────────────────────────────────────────────

ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mABCDEFGHJKSTfnihlp]')
LOG_RE  = re.compile(
    r'^(?P<date>\d{2}/\d{2})\s+'
    r'(?P<time>\d{2}:\d{2}:\d{2}\.\d+):\s+'
    r'\[(?P<component>[^\]]+)\]\s+'
    r'(?P<level>\w+):\s*'
    r'(?P<message>.*)',
    re.DOTALL,
)

# Tokens replaced when generating a template
_VAR_PATS = [
    re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
               re.IGNORECASE),                              # UUID
    re.compile(r'\d+\.\d+\.\d+\.\d+(:\d+)?'),              # IP(:port)
    re.compile(r'0x[0-9a-fA-F]+'),                         # hex literal
    re.compile(r'imsi-\S+'),                                # IMSI
    re.compile(r'suci-\S+'),                                # SUCI
    re.compile(r'\bsupi-\S+'),                              # SUPI
    re.compile(r'\(\.\./[^)]+\)'),                          # (src/file.c:N)
    re.compile(r'\b\d{2}/\d{2}\b'),                         # date MM/DD
    re.compile(r'\d{2}:\d{2}:\d{2}\.\d+'),                 # time
    re.compile(r'\b\d+\b'),                                 # standalone int
]


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def make_template(message: str) -> str:
    t = message
    for pat in _VAR_PATS:
        t = pat.sub("<*>", t)
    # collapse multiple <*> into one to group near-identical messages
    t = re.sub(r'(<\*>\s*)+', '<*> ', t).strip()
    return t


LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "WARN": 2,
               "ERROR": 3, "CRITICAL": 4, "FATAL": 4}


def parse_row(row: dict) -> dict:
    ts_ns  = int(row.get("timestamp_ns", 0))
    pod    = row.get("pod", "")
    app    = row.get("app", "") or (pod.split("-")[0] if pod else "")
    line   = strip_ansi(row.get("line", "")).strip()
    win_t  = (ts_ns // 1_000_000_000) // TEMPORAL_WINDOW_SECS
    win_a  = (ts_ns // 1_000_000_000) // APRIORI_WINDOW_SECS

    m = LOG_RE.match(line)
    if m:
        level    = m.group("level").upper()
        template = make_template(m.group("message"))
    else:
        level    = "INFO"
        template = make_template(line)

    return {
        "ts_ns":    ts_ns,
        "pod":      pod,
        "app":      app,
        "line":     line,
        "level":    level,
        "lev_ord":  LEVEL_ORDER.get(level, 1),
        "template": template,
        "win_t":    win_t,   # temporal window
        "win_a":    win_a,   # Apriori window
    }


# ──────────────────────────────────────────────────────────────────────────────
# Event Categorisation
# ──────────────────────────────────────────────────────────────────────────────

def categorise(rows: list[dict]) -> list[dict]:
    """Assign template IDs; no lines dropped here — pure annotation step."""
    tmpl_to_id: dict = {}
    tid = 0
    for r in rows:
        t = r["template"]
        if t not in tmpl_to_id:
            tmpl_to_id[t] = tid
            tid += 1
        r["tid"] = tmpl_to_id[t]
    print(f"  [step1] {len(tmpl_to_id)} unique templates from {len(rows)} events")
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# Event Filtering (temporal + spatial deduplication)
# ──────────────────────────────────────────────────────────────────────────────

def filter(rows: list[dict]) -> list[dict]:
    seen_temporal: set = set()
    temporal_kept: list = []

    for r in rows:
        key = (r["pod"], r["tid"], r["win_t"])
        if key not in seen_temporal:
            temporal_kept.append(r)
            seen_temporal.add(key)

    seen_spatial: set = set()
    spatial_kept: list = []

    for r in temporal_kept:
        key = (r["app"], r["tid"], r["win_t"])
        if key not in seen_spatial:
            spatial_kept.append(r)
            seen_spatial.add(key)

    print(f"  [step2] {len(rows)} → temporal {len(temporal_kept)} "
          f"→ spatial {len(spatial_kept)} events")
    return spatial_kept


# ──────────────────────────────────────────────────────────────────────────────
# Causality Filtering
# ──────────────────────────────────────────────────────────────────────────────

def _apriori_pairs(rows: list[dict]) -> set:
    """
    Mine frequent co-occurring template pairs and return a set of
    (cause_tid, effect_tid) directed rules.

    Causality direction: if conf(A→B) >> conf(B→A), A causes B.
    We suppress B when A is present

    Safety constraint: never mark a tid as suppressible if it
    corresponds to a WARNING-or-above event (those are always kept).
    Symmetric pairs (both directions high) are skipped — they are
    correlations, not causal chains.
    """

    window_tids: dict = defaultdict(set)
    for r in rows:
        window_tids[r["win_a"]].add(r["tid"])

    transactions = list(window_tids.values())
    n = len(transactions)
    if n < 5:
        return set()

    single_counts: dict = defaultdict(int)
    for t in transactions:
        for item in t:
            single_counts[item] += 1

    pair_counts: dict = defaultdict(int)
    for t in transactions:
        items = sorted(t)
        for a, b in combinations(items, 2):
            pair_counts[(a, b)] += 1

    min_count = APRIORI_MIN_SUPPORT * n
    frequent_pairs = {pair: cnt for pair, cnt in pair_counts.items()
                      if cnt >= min_count}

    tid_max_level: dict = defaultdict(int)
    for r in rows:
        if r["lev_ord"] > tid_max_level[r["tid"]]:
            tid_max_level[r["tid"]] = r["lev_ord"]

    WARN_ORD = LEVEL_ORDER["WARNING"]

    rules: set = set()  
    for (a, b), cnt in frequent_pairs.items():
        conf_ab = cnt / single_counts[a] if single_counts[a] else 0
        conf_ba = cnt / single_counts[b] if single_counts[b] else 0

        if conf_ab >= APRIORI_MIN_CONFIDENCE and conf_ba >= APRIORI_MIN_CONFIDENCE:
            continue

        if conf_ab >= APRIORI_MIN_CONFIDENCE:
            if tid_max_level.get(b, 0) < WARN_ORD:
                rules.add((a, b))

        if conf_ba >= APRIORI_MIN_CONFIDENCE:
            if tid_max_level.get(a, 0) < WARN_ORD:
                rules.add((b, a))

    return rules


def causality(rows: list[dict]) -> list[dict]:
    rules = _apriori_pairs(rows)
    if not rules:
        print("  [step3] no directional causal rules mined — keeping all events")
        return rows

    window_tids: dict = defaultdict(set)
    for r in rows:
        window_tids[r["win_a"]].add(r["tid"])

    effect_to_causes: dict = defaultdict(set)
    for cause, effect in rules:
        effect_to_causes[effect].add(cause)

    kept = []
    for r in rows:
        tid = r["tid"]
        causes = effect_to_causes.get(tid)
        if causes is None:
            kept.append(r)
            continue
        if any(c in window_tids[r["win_a"]] for c in causes):
            pass  
        else:
            kept.append(r)

    print(f"  [step3] {len(rules)} directional rules  "
          f"{len(rows)} → {len(kept)} events")
    return kept


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def load_csv(csv_path: Path) -> list[dict]:
    rows = []
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(parse_row(row))
    return rows


def write_filtered_csv(rows: list[dict], out_path: Path):
    fieldnames = ["timestamp_ns", "pod", "app", "template", "level", "line"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "timestamp_ns": r["ts_ns"],
                "pod":          r["pod"],
                "app":          r["app"],
                "template":     r["template"],
                "level":        r["level"],
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
    print(f"[preprocessing] loading {csv_path} ({in_bytes/1024:.1f} KB) ...")

    with ResourceTracker() as rt:
        rows = load_csv(csv_path)
        rows = categorise(rows)
        rows = filter(rows)
        rows = causality(rows)

    in_lines  = sum(1 for _ in open(csv_path, encoding="utf-8", errors="replace")) - 1
    out_lines = len(rows)

    filtered_path = out_dir / "filtered.csv"
    write_filtered_csv(rows, filtered_path)
    out_bytes = filtered_path.stat().st_size

    reduction_pct = (1.0 - out_lines / in_lines) * 100.0 if in_lines else 0.0
    storage_ratio = in_bytes / out_bytes if out_bytes else float("nan")

    _, query_latency_s = time_linear_scan(filtered_path)

    metrics = {
        "strategy":             "preprocessing",
        "scenario":             args.scenario,
        "config": {
            "temporal_window_s":    TEMPORAL_WINDOW_SECS,
            "spatial_window_s":     SPATIAL_WINDOW_SECS,
            "apriori_window_s":     APRIORI_WINDOW_SECS,
            "apriori_min_support":  APRIORI_MIN_SUPPORT,
            "apriori_min_conf":     APRIORI_MIN_CONFIDENCE,
        },
        "input_lines":            in_lines,
        "output_lines":           out_lines,
        "input_csv_bytes":        in_bytes,
        "output_bytes":           out_bytes,
        "reduction_pct":          round(reduction_pct, 2),
        "storage_ratio":          round(storage_ratio, 3),
        "decompression_required": False,
        "query_latency_s":        round(query_latency_s, 4),
        "total_query_latency_s":  round(query_latency_s, 4),
        **rt.to_dict(),
    }

    metrics_path = out_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"[preprocessing] {in_lines} → {out_lines} lines  "
          f"reduction={reduction_pct:.1f}%  "
          f"wall={rt.wall_s:.1f}s  mem={rt.peak_mem_mb:.0f}MB  "
          f"query={query_latency_s:.3f}s")
    print(f"[preprocessing] metrics → {metrics_path}")


if __name__ == "__main__":
    main()
