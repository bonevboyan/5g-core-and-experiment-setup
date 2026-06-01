"""
analysis/RQ2/rq2b_overhead.py

RQ2 sub-question 2 (processing overhead): CPU time, peak memory,
query latency, and throughput for each reduction strategy.

Produces:
  figures/rq2b_cpu_time.pdf                — bar: cpu_s per strategy (fair comparison)
  figures/rq2b_peak_memory.pdf             — bar: peak RSS per strategy x scenario
  figures/rq2b_query_latency.pdf           — total query latency comparison
  figures/rq2b_throughput.pdf              — MB/s throughput
  tables/rq2b_overhead_summary.csv         — full table
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import (
    FIGURES_DIR, TABLES_DIR, PALETTE, SCENARIO_LABELS, STRATEGY_LABELS,
    STRATEGIES, SCENARIOS,
    FIGURE_DPI, FIGURE_EXT, FIGURE_SIZE_WIDE, FIGURE_SIZE_LARGE,
    FONT_SIZE_TITLE, FONT_SIZE_LABEL, FONT_SIZE_TICK, FONT_SIZE_LEGEND,
)
from load_data import load_all_strategy_metrics


def _check_data(df: pd.DataFrame, label: str) -> bool:
    if df.empty:
        print(f"  [{label}] No data available — skipping.")
        return False
    return True


# ---------------------------------------------------------------------------
# Figure 1: CPU time per strategy (steady scenario)
# ---------------------------------------------------------------------------

def plot_cpu_time(df: pd.DataFrame):
    steady = df[df["scenario"] == "steady"].copy()
    if steady.empty:
        steady = df.groupby("strategy").mean(numeric_only=True).reset_index()
        title_suffix = "(mean across scenarios)"
    else:
        title_suffix = "(steady-state)"

    strats_present = [s for s in STRATEGIES if s in steady["strategy"].values]
    if not strats_present:
        print("  [rq2b] No CPU data — skipping.")
        return

    cpu_vals = [float(steady[steady["strategy"] == s]["cpu_s"].values[0])
                if s in steady["strategy"].values else np.nan
                for s in strats_present]

    if all(np.isnan(v) for v in cpu_vals):
        print("  [rq2b] No cpu_s data — skipping.")
        return

    x = np.arange(len(strats_present))
    fig, ax = plt.subplots(figsize=FIGURE_SIZE_WIDE, dpi=FIGURE_DPI)

    bars = ax.bar(x, cpu_vals, 0.6,
                  color=[PALETTE[s] for s in strats_present], alpha=0.85)
    for bar, v in zip(bars, cpu_vals):
        if not np.isnan(v):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.002,
                    f"{v:.2f}s",
                    ha="center", va="bottom", fontsize=FONT_SIZE_TICK - 1)

    ax.set_xticks(x)
    ax.set_xticklabels([STRATEGY_LABELS[s] for s in strats_present],
                       fontsize=FONT_SIZE_TICK)
    ax.set_ylabel("CPU time (s)", fontsize=FONT_SIZE_LABEL)
    ax.set_title(
        f"RQ2b — CPU time consumed by reduction {title_suffix}",
        fontsize=FONT_SIZE_TITLE,
    )
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)

    fig.tight_layout()
    out = FIGURES_DIR / f"rq2b_cpu_time.{FIGURE_EXT}"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2b] Saved {out}")


# ---------------------------------------------------------------------------
# Figure 2: Peak memory per strategy × scenario
# ---------------------------------------------------------------------------

def plot_peak_memory(df: pd.DataFrame):
    pivot = df.pivot_table(index="scenario", columns="strategy",
                           values="peak_mem_mb", aggfunc="mean")
    pivot = pivot.reindex(index=SCENARIOS, columns=STRATEGIES)
    present_scenarios = [s for s in SCENARIOS if s in pivot.index
                         and not pivot.loc[s].isna().all()]
    pivot = pivot.loc[present_scenarios]

    if pivot.empty:
        print("  [rq2b] No peak_mem_mb data — skipping.")
        return

    n_scen  = len(pivot)
    n_strat = len(STRATEGIES)
    x       = np.arange(n_scen)
    width   = 0.8 / n_strat

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_LARGE, dpi=FIGURE_DPI)

    for i, strat in enumerate(STRATEGIES):
        if strat not in pivot.columns:
            continue
        vals   = pivot[strat].values.astype(float)
        offset = (i - n_strat / 2 + 0.5) * width
        ax.bar(x + offset, vals, width * 0.9,
               label=STRATEGY_LABELS[strat],
               color=PALETTE[strat], alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([SCENARIO_LABELS.get(s, s) for s in present_scenarios],
                       fontsize=FONT_SIZE_TICK, rotation=15, ha="right")
    ax.set_ylabel("Peak RSS memory (MiB)", fontsize=FONT_SIZE_LABEL)
    ax.set_title("RQ2b — Peak memory usage per strategy and scenario",
                 fontsize=FONT_SIZE_TITLE)
    ax.legend(fontsize=FONT_SIZE_LEGEND, loc="upper right")
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)

    fig.tight_layout()
    out = FIGURES_DIR / f"rq2b_peak_memory.{FIGURE_EXT}"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2b] Saved {out}")


# ---------------------------------------------------------------------------
# Figure 3: Query latency 
# ---------------------------------------------------------------------------

def plot_query_latency(df: pd.DataFrame):
    steady = df[df["scenario"] == "steady"].copy()
    if steady.empty:
        steady = df.groupby("strategy").mean(numeric_only=True).reset_index()
        title_suffix = "(mean across scenarios)"
    else:
        title_suffix = "(steady-state)"

    strats_present = [s for s in STRATEGIES if s in steady["strategy"].values]
    latency_vals = [
        float(steady[steady["strategy"] == s]["query_latency_s"].values[0])
        if not steady[steady["strategy"] == s].empty else np.nan
        for s in strats_present
    ]

    if all(np.isnan(v) for v in latency_vals):
        print("  [rq2b] No query_latency_s data — skipping.")
        return

    x, width = np.arange(len(strats_present)), 0.5
    fig, ax = plt.subplots(figsize=FIGURE_SIZE_WIDE, dpi=FIGURE_DPI)

    for i, (s, v) in enumerate(zip(strats_present, latency_vals)):
        if np.isnan(v):
            continue
        ax.bar(i, v, width, color=PALETTE[s], alpha=0.85)
        ax.text(i, v * 1.12, f"{v:.4f}s",
                ha="center", va="bottom", fontsize=FONT_SIZE_TICK - 1)

    ax.set_xticks(x)
    ax.set_xticklabels([STRATEGY_LABELS[s] for s in strats_present],
                       fontsize=FONT_SIZE_TICK)
    ax.set_ylabel("Query latency (s)", fontsize=FONT_SIZE_LABEL)
    ax.set_title(
        f"RQ2b — Query latency per strategy {title_suffix}\n"
        "Lossless: decompression + scan.  Lossy: scan of filtered output only.",
        fontsize=FONT_SIZE_TITLE,
    )
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)

    fig.tight_layout()
    out = FIGURES_DIR / f"rq2b_query_latency.{FIGURE_EXT}"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2b] Saved {out}")


# ---------------------------------------------------------------------------
# Figure 5: CPU cost normalised by input size (cpu_per_mb)
# ---------------------------------------------------------------------------

def plot_cpu_per_mb(df: pd.DataFrame):
    steady = df[df["scenario"] == "steady"].copy()
    if steady.empty:
        steady = df.groupby("strategy").mean(numeric_only=True).reset_index()
        title_suffix = "(mean across scenarios)"
    else:
        title_suffix = "(steady-state)"

    strats_present = [s for s in STRATEGIES if s in steady["strategy"].values]
    if "cpu_per_mb" not in steady.columns:
        print("  [rq2b] No cpu_per_mb data — skipping.")
        return

    vals = [
        float(steady[steady["strategy"] == s]["cpu_per_mb"].values[0])
        if s in steady["strategy"].values else np.nan
        for s in strats_present
    ]

    if all(np.isnan(v) for v in vals):
        print("  [rq2b] No cpu_per_mb data — skipping.")
        return

    x = np.arange(len(strats_present))
    fig, ax = plt.subplots(figsize=FIGURE_SIZE_WIDE, dpi=FIGURE_DPI)

    bars = ax.bar(x, vals, 0.6,
                  color=[PALETTE[s] for s in strats_present], alpha=0.85)
    for bar, v in zip(bars, vals):
        if not np.isnan(v):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.0005,
                    f"{v:.4f}",
                    ha="center", va="bottom", fontsize=FONT_SIZE_TICK - 1)

    ax.set_xticks(x)
    ax.set_xticklabels([STRATEGY_LABELS[s] for s in strats_present],
                       fontsize=FONT_SIZE_TICK)
    ax.set_ylabel("CPU time per MB of input (s/MB)", fontsize=FONT_SIZE_LABEL)
    ax.set_title(f"RQ2b — CPU overhead per MB of input {title_suffix}",
                 fontsize=FONT_SIZE_TITLE)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)

    fig.tight_layout()
    out = FIGURES_DIR / f"rq2b_cpu_per_mb.{FIGURE_EXT}"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2b] Saved {out}")


# ---------------------------------------------------------------------------
# Figure 4: Throughput (MB/s) per strategy
# ---------------------------------------------------------------------------

def plot_throughput(df: pd.DataFrame):
    steady = df[df["scenario"] == "steady"].copy()
    if steady.empty:
        steady = df.groupby("strategy").mean(numeric_only=True).reset_index()
        title_suffix = "(mean across scenarios)"
    else:
        title_suffix = "(steady-state)"

    strats_present = [s for s in STRATEGIES if s in steady["strategy"].values]
    tput_vals = []
    for s in strats_present:
        row = steady[steady["strategy"] == s]
        col = "cpu_throughput_mb_s"
        if row.empty or col not in row.columns:
            tput_vals.append(np.nan)
        else:
            tput_vals.append(float(row[col].values[0]))

    if all(np.isnan(v) for v in tput_vals):
        print("  [rq2b] No cpu_throughput_mb_s data — skipping.")
        return

    x = np.arange(len(strats_present))
    fig, ax = plt.subplots(figsize=FIGURE_SIZE_WIDE, dpi=FIGURE_DPI)

    bars = ax.bar(x, tput_vals, 0.6,
                  color=[PALETTE[s] for s in strats_present], alpha=0.85)
    for bar, v in zip(bars, tput_vals):
        if not np.isnan(v):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.01,
                    f"{v:.2f}",
                    ha="center", va="bottom", fontsize=FONT_SIZE_TICK)

    ax.set_xticks(x)
    ax.set_xticklabels([STRATEGY_LABELS[s] for s in strats_present],
                       fontsize=FONT_SIZE_TICK)
    ax.set_ylabel("CPU throughput (MB / CPU-s)", fontsize=FONT_SIZE_LABEL)
    ax.set_title(
        f"RQ2b — Processing throughput per strategy {title_suffix}",
        fontsize=FONT_SIZE_TITLE,
    )
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)

    fig.tight_layout()
    out = FIGURES_DIR / f"rq2b_throughput.{FIGURE_EXT}"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2b] Saved {out}")


# ---------------------------------------------------------------------------
# Table: overhead summary
# ---------------------------------------------------------------------------

def save_summary_table(df: pd.DataFrame):
    cols = ["strategy_label", "scenario", "cpu_s", "cpu_per_mb",
            "peak_mem_mb", "decompression_latency_s", "query_latency_s",
            "throughput_mb_s", "log_throughput_mb_s", "cpu_throughput_mb_s"]
    out_df = df[[c for c in cols if c in df.columns]].copy()

    rename = {
        "strategy_label":          "Strategy",
        "scenario":                "Scenario",
        "cpu_s":                   "CPU time (s)",
        "cpu_per_mb":              "CPU time per MB (s/MB)",
        "peak_mem_mb":             "Peak memory (MiB)",
        "decompression_latency_s": "Decompression latency (s)",
        "query_latency_s":         "Query latency (s)",
        "throughput_mb_s":         "Throughput MB/s vs CSV (offline)",
        "log_throughput_mb_s":     "Throughput MB/s vs raw log (offline)",
        "cpu_throughput_mb_s":     "CPU throughput (MB/CPU-s)",
    }
    out_df = out_df.rename(columns={k: v for k, v in rename.items() if k in out_df.columns})
    out_df["Scenario"] = out_df["Scenario"].map(lambda s: SCENARIO_LABELS.get(s, s))

    path = TABLES_DIR / "rq2b_overhead_summary.csv"
    out_df.to_csv(path, index=False, float_format="%.4f")
    print(f"  [rq2b] Saved {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run():
    print("[rq2b] Loading strategy metrics...")
    df = load_all_strategy_metrics()

    if not _check_data(df, "rq2b"):
        return

    save_summary_table(df)
    plot_cpu_time(df)
    plot_peak_memory(df)
    plot_query_latency(df)
    plot_throughput(df)
    plot_cpu_per_mb(df)
    print("[rq2b] Done.")


if __name__ == "__main__":
    run()
