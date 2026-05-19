"""
analysis/RQ2/rq2b_overhead.py

RQ2 sub-question 2 (processing overhead): CPU time, wall time, peak memory,
query latency, and throughput for each reduction strategy.

Produces:
  figures/rq2b_cpu_wall_time.pdf           — grouped bar: cpu_s and wall_s per strategy
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
    FIGURE_DPI, FIGURE_SIZE_WIDE, FIGURE_SIZE_LARGE,
    FONT_SIZE_TITLE, FONT_SIZE_LABEL, FONT_SIZE_TICK, FONT_SIZE_LEGEND,
)
from load_data import load_all_strategy_metrics


def _check_data(df: pd.DataFrame, label: str) -> bool:
    if df.empty:
        print(f"  [{label}] No data available — skipping.")
        return False
    return True


# ---------------------------------------------------------------------------
# Figure 1: CPU time vs wall time (steady scenario, per strategy)
# ---------------------------------------------------------------------------

def plot_cpu_wall_time(df: pd.DataFrame):
    steady = df[df["scenario"] == "steady"].copy()
    if steady.empty:
        steady = df.groupby("strategy").mean(numeric_only=True).reset_index()
        title_suffix = "(mean across scenarios)"
    else:
        title_suffix = "(steady-state)"

    strats_present = [s for s in STRATEGIES if s in steady["strategy"].values]
    if not strats_present:
        print("  [rq2b] No CPU/wall data — skipping.")
        return

    x     = np.arange(len(strats_present))
    width = 0.35

    cpu_vals  = [float(steady[steady["strategy"] == s]["cpu_s"].values[0])
                 if s in steady["strategy"].values else np.nan for s in strats_present]
    wall_vals = [float(steady[steady["strategy"] == s]["wall_s"].values[0])
                 if s in steady["strategy"].values else np.nan for s in strats_present]

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_WIDE, dpi=FIGURE_DPI)

    bars_wall = ax.bar(x - width / 2, wall_vals, width,
                       label="Wall time (s)", color="#78909C", alpha=0.85)
    bars_cpu  = ax.bar(x + width / 2, cpu_vals, width,
                       label="CPU time (s)",
                       color=[PALETTE[s] for s in strats_present], alpha=0.85)

    for bars, vals in [(bars_wall, wall_vals), (bars_cpu, cpu_vals)]:
        for bar, v in zip(bars, vals):
            if not np.isnan(v):
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.002,
                        f"{v:.2f}s",
                        ha="center", va="bottom", fontsize=FONT_SIZE_TICK - 1)

    ax.set_xticks(x)
    ax.set_xticklabels([STRATEGY_LABELS[s] for s in strats_present],
                       fontsize=FONT_SIZE_TICK)
    ax.set_ylabel("Time (s)", fontsize=FONT_SIZE_LABEL)
    ax.set_title(f"RQ2b — Processing time per strategy {title_suffix}",
                 fontsize=FONT_SIZE_TITLE)
    ax.legend(fontsize=FONT_SIZE_LEGEND)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)

    fig.tight_layout()
    out = FIGURES_DIR / "rq2b_cpu_wall_time.pdf"
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
    out = FIGURES_DIR / "rq2b_peak_memory.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2b] Saved {out}")


# ---------------------------------------------------------------------------
# Figure 3: Total query latency 
# ---------------------------------------------------------------------------

def plot_query_latency(df: pd.DataFrame):
    steady = df[df["scenario"] == "steady"].copy()
    if steady.empty:
        steady = df.groupby("strategy").mean(numeric_only=True).reset_index()
        title_suffix = "(mean across scenarios)"
    else:
        title_suffix = "(steady-state)"

    strats_present = [s for s in STRATEGIES if s in steady["strategy"].values]
    if not strats_present:
        print("  [rq2b] No query latency data — skipping.")
        return

    raw_latency   = [float(steady[steady["strategy"] == s]["query_latency_s"].values[0])
                     if s in steady["strategy"].values else np.nan for s in strats_present]
    total_latency = [float(steady[steady["strategy"] == s]["total_query_latency_s"].values[0])
                     if s in steady["strategy"].values else np.nan for s in strats_present]

    x     = np.arange(len(strats_present))
    width = 0.35

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_WIDE, dpi=FIGURE_DPI)

    ax.bar(x - width / 2, raw_latency, width,
           label="Query only (grep scan)", color="#B0BEC5", alpha=0.9)
    ax.bar(x + width / 2, total_latency, width,
           label="Total (processing + query)",
           color=[PALETTE[s] for s in strats_present], alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([STRATEGY_LABELS[s] for s in strats_present],
                       fontsize=FONT_SIZE_TICK)
    ax.set_ylabel("Latency (s)", fontsize=FONT_SIZE_LABEL)
    ax.set_title(f"RQ2b — Query latency per strategy {title_suffix}",
                 fontsize=FONT_SIZE_TITLE)
    ax.legend(fontsize=FONT_SIZE_LEGEND)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)

    fig.tight_layout()
    out = FIGURES_DIR / "rq2b_query_latency.pdf"
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
        if row.empty or "throughput_mb_s" not in row.columns:
            tput_vals.append(np.nan)
        else:
            tput_vals.append(float(row["throughput_mb_s"].values[0]))

    if all(np.isnan(v) for v in tput_vals):
        print("  [rq2b] No throughput data — skipping.")
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
    ax.set_ylabel("Throughput (MB/s)", fontsize=FONT_SIZE_LABEL)
    ax.set_title(f"RQ2b — Processing throughput per strategy {title_suffix}",
                 fontsize=FONT_SIZE_TITLE)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)

    fig.tight_layout()
    out = FIGURES_DIR / "rq2b_throughput.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2b] Saved {out}")


# ---------------------------------------------------------------------------
# Table: overhead summary
# ---------------------------------------------------------------------------

def save_summary_table(df: pd.DataFrame):
    cols = ["strategy_label", "scenario", "wall_s", "cpu_s",
            "peak_mem_mb", "query_latency_s", "total_query_latency_s",
            "throughput_mb_s"]
    out_df = df[[c for c in cols if c in df.columns]].copy()

    rename = {
        "strategy_label":        "Strategy",
        "scenario":              "Scenario",
        "wall_s":                "Wall time (s)",
        "cpu_s":                 "CPU time (s)",
        "peak_mem_mb":           "Peak memory (MiB)",
        "query_latency_s":       "Query latency (s)",
        "total_query_latency_s": "Total latency (s)",
        "throughput_mb_s":       "Throughput (MB/s)",
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
    plot_cpu_wall_time(df)
    plot_peak_memory(df)
    plot_query_latency(df)
    plot_throughput(df)
    print("[rq2b] Done.")


if __name__ == "__main__":
    run()
