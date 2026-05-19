"""
analysis/RQ2/load_data.py

Data loaders for the B-log-strategies experiment outputs.
"""

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from config import (
    STRATEGIES, STRATEGY_DIRS, VISIBILITY_DIR,
    SCENARIOS, FAULT_SCENARIOS,
    LOSSLESS_STRATEGIES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path):
    if not path.exists():
        warnings.warn(f"Missing file: {path}")
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        warnings.warn(f"Failed to read {path}: {e}")
        return {}


# ---------------------------------------------------------------------------
# Per-strategy metrics 
# ---------------------------------------------------------------------------

def load_strategy_metrics(strategy: str, scenario: str) -> dict:
    """
    Load metrics.json for one strategy × scenario.

    Returns the raw dict from the file, or {} if not found.
    """
    path = STRATEGY_DIRS[strategy] / scenario / "metrics.json"
    return _read_json(path)


def load_all_strategy_metrics() -> pd.DataFrame:
    """
    Load metrics.json for every strategy × scenario combination and return
    a single normalised DataFrame with one row per (strategy, scenario).

    Unified columns (NaN where not applicable):
        strategy, scenario
        input_bytes         — corpus log bytes for compression; CSV bytes for filtering
        output_bytes        — bytes after reduction
        input_lines         — raw event count (lossy only; NaN for lossless)
        output_lines        — events kept    (lossy only; NaN for lossless)
        reduction_pct       — 100 × (1 − output/input) in bytes
        line_reduction_pct  — 100 × (1 − output_lines/input_lines); NaN for lossless
        compression_ratio   — input_bytes / output_bytes
        wall_s              — wall-clock time (s)
        cpu_s               — CPU time (s)
        peak_mem_mb         — peak RSS (MiB)
        query_latency_s     — time to grep the output for ERROR
        total_query_latency_s — processing time + query_latency_s
        throughput_mb_s     — MB/s throughput during processing
        decompression_required — bool
    """
    rows = []
    for strategy in STRATEGIES:
        for scenario in SCENARIOS:
            raw = load_strategy_metrics(strategy, scenario)
            if not raw:
                continue

            in_bytes  = raw.get("input_log_bytes") or raw.get("input_csv_bytes") or np.nan
            out_bytes = raw.get("output_bytes", np.nan)

            in_lines  = raw.get("input_lines",  np.nan)
            out_lines = raw.get("output_lines", np.nan)

            if not np.isnan(in_lines) and not np.isnan(out_lines) and in_lines > 0:
                line_red_pct = (1.0 - out_lines / in_lines) * 100.0
            else:
                line_red_pct = np.nan

            comp_ratio = raw.get("compression_ratio") or raw.get("storage_ratio") or np.nan
            if np.isnan(comp_ratio) and not np.isnan(in_bytes) and not np.isnan(out_bytes) and out_bytes > 0:
                comp_ratio = in_bytes / out_bytes

            mb = in_bytes / (1024 ** 2) if not np.isnan(in_bytes) else np.nan
            wall = raw.get("wall_s", np.nan)
            tput = raw.get("throughput_mb_s") or (mb / wall if wall and wall > 0 else np.nan)

            rows.append({
                "strategy":              strategy,
                "scenario":              scenario,
                "input_bytes":           in_bytes,
                "output_bytes":          out_bytes,
                "input_lines":           in_lines,
                "output_lines":          out_lines,
                "reduction_pct":         raw.get("reduction_pct", np.nan),
                "line_reduction_pct":    line_red_pct,
                "compression_ratio":     comp_ratio,
                "wall_s":                wall,
                "cpu_s":                 raw.get("cpu_s", np.nan),
                "peak_mem_mb":           raw.get("peak_mem_mb", np.nan),
                "query_latency_s":       raw.get("query_latency_s", np.nan),
                "total_query_latency_s": raw.get("total_query_latency_s", np.nan),
                "throughput_mb_s":       tput,
                "decompression_required": bool(raw.get("decompression_required", False)),
                "corpus_coverage_pct":   raw.get("corpus_coverage_pct", np.nan),
            })

    if not rows:
        warnings.warn("No strategy metrics found — did the B experiments run?")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["strategy_label"] = df["strategy"].map(
        {"logshrink": "LogShrink", "denum": "Denum",
         "salo": "SALO", "preprocessing": "Log Preprocessing"}
    )
    return df


# ---------------------------------------------------------------------------
# Visibility metrics 
# ---------------------------------------------------------------------------

def load_visibility_metrics(scenario: str) -> dict:
    """
    Load visibility_metrics.json for one scenario.
    Returns raw dict, or {} if not found.
    """
    path = VISIBILITY_DIR / scenario / "visibility_metrics.json"
    return _read_json(path)


def load_all_visibility() -> pd.DataFrame:
    """
    Load visibility_metrics.json for every scenario and flatten into a
    DataFrame with one row per (strategy, scenario).

    Columns:
        strategy, scenario
        total_retention_pct
        fault_line_retention_pct
        fault_template_retention_pct
        fault_visibility_pct           — template-level fault detectability
        novelty_retention_pct          — NaN if no novelty anomalies
        novelty_false_negative_pct
        fault_window_retention_pct     — NaN for non-fault scenarios
        input_total_lines, output_total_lines
        input_fault_lines, output_fault_lines
        novelty_anomaly_count
    """
    rows = []
    for scenario in SCENARIOS:
        raw = load_visibility_metrics(scenario)
        if not raw:
            continue
        strats = raw.get("strategies", {})
        for strategy, vis in strats.items():
            rows.append({
                "strategy":                    strategy,
                "scenario":                    scenario,
                "total_retention_pct":         vis.get("total_retention_pct", np.nan),
                "fault_line_retention_pct":    vis.get("fault_line_retention_pct", np.nan),
                "fault_template_retention_pct":vis.get("fault_template_retention_pct", np.nan),
                "fault_visibility_pct":        vis.get("fault_visibility_pct", np.nan),
                "novelty_retention_pct":       vis.get("novelty_retention_pct", np.nan),
                "novelty_false_negative_pct":  vis.get("novelty_false_negative_pct", np.nan),
                "fault_window_retention_pct":  vis.get("fault_window_retention_pct", np.nan),
                "fault_window_total_lines":    vis.get("fault_window_total_lines", np.nan),
                "fault_window_retained_lines": vis.get("fault_window_retained_lines", np.nan),
                "input_total_lines":           vis.get("input_total_lines", np.nan),
                "output_total_lines":          vis.get("output_total_lines", np.nan),
                "input_fault_lines":           vis.get("input_fault_lines", np.nan),
                "output_fault_lines":          vis.get("output_fault_lines", np.nan),
                "novelty_anomaly_count":       vis.get("novelty_anomaly_count", np.nan),
            })

    if not rows:
        warnings.warn("No visibility metrics found — did phase 06-visibility run?")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["strategy_label"] = df["strategy"].map(
        {"logshrink": "LogShrink", "denum": "Denum",
         "salo": "SALO", "preprocessing": "Log Preprocessing"}
    )
    return df


# ---------------------------------------------------------------------------
# Combined
# ---------------------------------------------------------------------------

def load_combined() -> pd.DataFrame:
    """
    Join strategy metrics with visibility metrics on (strategy, scenario).
    Returns a DataFrame suitable for scatter/Pareto plots.
    """
    metrics = load_all_strategy_metrics()
    vis     = load_all_visibility()

    if metrics.empty and vis.empty:
        return pd.DataFrame()
    if metrics.empty:
        return vis
    if vis.empty:
        return metrics

    merged = metrics.merge(vis, on=["strategy", "scenario"], how="outer",
                           suffixes=("", "_vis"))
    if "strategy_label" in merged.columns:
        pass
    elif "strategy_label_vis" in merged.columns:
        merged["strategy_label"] = merged["strategy_label_vis"]
    return merged
