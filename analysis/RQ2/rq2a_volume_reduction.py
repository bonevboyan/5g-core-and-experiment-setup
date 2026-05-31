"""
analysis/RQ2/rq2a_volume_reduction.py

RQ2 sub-question 1: How much does each strategy reduce log volume?

Produces:
  figures/rq2a_reduction_pct_by_scenario.pdf  — grouped bar: reduction % per strategy x scenario
  figures/rq2a_storage_bytes_comparison.pdf   — stacked bar: input vs output bytes per strategy
  figures/rq2a_line_reduction_pct.pdf         — lossy-only line-event reduction
  tables/rq2a_volume_reduction_summary.csv    — full table
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
    FIGURES_DIR, TABLES_DIR, PALETTE, SCENARIO_PALETTE,
    STRATEGIES, SCENARIOS, SCENARIO_LABELS, STRATEGY_LABELS,
    FIGURE_DPI, FIGURE_EXT, FIGURE_SIZE_WIDE, FIGURE_SIZE_LARGE,
    FONT_SIZE_TITLE, FONT_SIZE_LABEL, FONT_SIZE_TICK, FONT_SIZE_LEGEND,
    LOSSLESS_STRATEGIES,
)
from load_data import load_all_strategy_metrics


def _check_data(df: pd.DataFrame, label: str) -> bool:
    if df.empty:
        print(f"  [{label}] No data available — skipping.")
        return False
    return True


# ---------------------------------------------------------------------------
# Figure 1: Reduction_pct per strategy
# ---------------------------------------------------------------------------

def plot_reduction_pct(df: pd.DataFrame):
    pivot = df.pivot_table(index="scenario", columns="strategy",
                           values="reduction_pct", aggfunc="mean")
    pivot = pivot.reindex(index=SCENARIOS, columns=STRATEGIES)

    present_scenarios = [s for s in SCENARIOS if s in pivot.index and not pivot.loc[s].isna().all()]
    pivot = pivot.loc[present_scenarios]

    if pivot.empty:
        print("  [rq2a] No reduction_pct data to plot.")
        return

    n_scen   = len(pivot)
    n_strat  = len(STRATEGIES)
    x        = np.arange(n_scen)
    width    = 0.8 / n_strat

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_LARGE, dpi=FIGURE_DPI)

    for i, strat in enumerate(STRATEGIES):
        if strat not in pivot.columns:
            continue
        vals = pivot[strat].values.astype(float)
        offset = (i - n_strat / 2 + 0.5) * width
        bars = ax.bar(x + offset, vals, width * 0.9,
                      label=STRATEGY_LABELS[strat],
                      color=PALETTE[strat], alpha=0.85)
        for bar, v in zip(bars, vals):
            if not np.isnan(v):
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.5,
                        f"{v:.1f}%",
                        ha="center", va="bottom",
                        fontsize=FONT_SIZE_TICK - 1, rotation=90)

    ax.set_xticks(x)
    ax.set_xticklabels([SCENARIO_LABELS.get(s, s) for s in present_scenarios],
                       fontsize=FONT_SIZE_TICK, rotation=15, ha="right")
    ax.set_ylabel("Storage reduction (%)", fontsize=FONT_SIZE_LABEL)
    ax.set_title(
        "RQ2a — Telemetry volume reduction by strategy and scenario"
        fontsize=FONT_SIZE_TITLE,
    )
    ax.legend(fontsize=FONT_SIZE_LEGEND, loc="upper right")
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    ax.set_ylim(0, max(pivot.max().max() * 1.25, 10))

    fig.tight_layout()
    out = FIGURES_DIR / f"rq2a_reduction_pct_by_scenario.{FIGURE_EXT}"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2a] Saved {out}")


# ---------------------------------------------------------------------------
# Figure 2: Input vs output per strategy (steady-state)
# ---------------------------------------------------------------------------

def plot_storage_bytes(df: pd.DataFrame):
    steady = df[df["scenario"] == "steady"].copy()
    if steady.empty:
        # Fall back to first available scenario
        first = df["scenario"].iloc[0]
        steady = df[df["scenario"] == first].copy()
        title_suffix = f"({SCENARIO_LABELS.get(first, first)})"
    else:
        title_suffix = "(steady-state)"

    strategies_present = [s for s in STRATEGIES if s in steady["strategy"].values]
    if not strategies_present:
        print("  [rq2a] No storage bytes data — skipping.")
        return

    x       = np.arange(len(strategies_present))
    width   = 0.45

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_WIDE, dpi=FIGURE_DPI)

    in_bytes  = [steady[steady["strategy"] == s]["input_bytes"].values[0]
                 / (1024 ** 2) for s in strategies_present]
    out_bytes = [steady[steady["strategy"] == s]["output_bytes"].values[0]
                 / (1024 ** 2) for s in strategies_present]

    bars_in  = ax.bar(x - width / 2, in_bytes, width,
                      label="Input (Loki CSV)", color="#90A4AE", alpha=0.9)
    bars_out = ax.bar(x + width / 2, out_bytes, width,
                      label="Output (after reduction)",
                      color=[PALETTE[s] for s in strategies_present], alpha=0.85)

    for bar, v in zip(bars_in, in_bytes):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                f"{v:.1f}", ha="center", va="bottom", fontsize=FONT_SIZE_TICK - 1)
    for bar, v in zip(bars_out, out_bytes):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                f"{v:.1f}", ha="center", va="bottom", fontsize=FONT_SIZE_TICK - 1)

    ax.set_xticks(x)
    ax.set_xticklabels([STRATEGY_LABELS[s] for s in strategies_present],
                       fontsize=FONT_SIZE_TICK)
    ax.set_ylabel("Storage (MiB)", fontsize=FONT_SIZE_LABEL)
    ax.set_title(
        f"RQ2a — Storage before and after reduction {title_suffix}",
        fontsize=FONT_SIZE_TITLE,
    )
    ax.legend(fontsize=FONT_SIZE_LEGEND)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)

    fig.tight_layout()
    out = FIGURES_DIR / f"rq2a_storage_bytes_comparison.{FIGURE_EXT}"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2a] Saved {out}")


# ---------------------------------------------------------------------------
# Figure 3: Line-event reduction 
# ---------------------------------------------------------------------------

def plot_line_reduction(df: pd.DataFrame):
    all_strats = df.copy()
    all_strats["line_reduction_pct"] = all_strats["line_reduction_pct"].fillna(0.0)

    if all_strats.empty:
        print("  [rq2a] No line_reduction_pct data — skipping.")
        return

    present_scenarios  = [s for s in SCENARIOS if s in all_strats["scenario"].values]
    present_strategies = [s for s in STRATEGIES if s in all_strats["strategy"].values]

    pivot = all_strats.pivot_table(index="scenario", columns="strategy",
                                   values="line_reduction_pct", aggfunc="mean")
    pivot = pivot.reindex(index=present_scenarios, columns=present_strategies)

    n_scen  = len(present_scenarios)
    n_strat = len(present_strategies)
    x       = np.arange(n_scen)
    width   = 0.7 / n_strat

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_WIDE, dpi=FIGURE_DPI)

    for i, strat in enumerate(present_strategies):
        if strat not in pivot.columns:
            continue
        vals   = pivot[strat].values.astype(float)
        offset = (i - n_strat / 2 + 0.5) * width
        bars   = ax.bar(x + offset, vals, width * 0.9,
                        label=STRATEGY_LABELS[strat],
                        color=PALETTE[strat], alpha=0.85)
        for bar, v in zip(bars, vals):
            if not np.isnan(v):
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.5,
                        f"{v:.1f}%",
                        ha="center", va="bottom", fontsize=FONT_SIZE_TICK - 1)

    ax.set_xticks(x)
    ax.set_xticklabels([SCENARIO_LABELS.get(s, s) for s in present_scenarios],
                       fontsize=FONT_SIZE_TICK, rotation=15, ha="right")
    ax.set_ylabel("Log-event reduction (%)", fontsize=FONT_SIZE_LABEL)
    ax.set_title(
        "RQ2a — Log-event (line) reduction per strategy",
        fontsize=FONT_SIZE_TITLE,
    )
    ax.legend(fontsize=FONT_SIZE_LEGEND)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    ax.set_ylim(0, max(pivot.max().max() * 1.25, 10))

    fig.tight_layout()
    out = FIGURES_DIR / f"rq2a_line_reduction_pct.{FIGURE_EXT}"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2a] Saved {out}")


# ---------------------------------------------------------------------------
# Table: volume reduction summary
# ---------------------------------------------------------------------------

def save_summary_table(df: pd.DataFrame):
    cols = ["strategy_label", "scenario", "input_bytes", "output_bytes",
            "reduction_pct", "log_reduction_pct", "line_reduction_pct",
            "compression_ratio", "corpus_coverage_pct", "decompression_required"]
    out_df = df[[c for c in cols if c in df.columns]].copy()

    for col in ["input_bytes", "output_bytes"]:
        if col in out_df.columns:
            out_df[col] = (out_df[col] / 1024).round(1)

    rename = {
        "strategy_label":        "Strategy",
        "scenario":              "Scenario",
        "input_bytes":           "Input (KiB)",
        "output_bytes":          "Output (KiB)",
        "reduction_pct":         "Reduction vs CSV (%)",
        "log_reduction_pct":     "Reduction vs raw log (%)",
        "line_reduction_pct":    "Line reduction (%)",
        "compression_ratio":     "Ratio (×) [vs raw log for lossless; vs CSV for lossy]",
        "corpus_coverage_pct":   "Corpus coverage (%)",
        "decompression_required": "Decompression needed",
    }
    out_df = out_df.rename(columns={k: v for k, v in rename.items() if k in out_df.columns})
    out_df["Scenario"] = out_df["Scenario"].map(lambda s: SCENARIO_LABELS.get(s, s))

    path = TABLES_DIR / "rq2a_volume_reduction_summary.csv"
    out_df.to_csv(path, index=False, float_format="%.2f")
    print(f"  [rq2a] Saved {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run():
    print("[rq2a] Loading strategy metrics...")
    df = load_all_strategy_metrics()

    if not _check_data(df, "rq2a"):
        return

    save_summary_table(df)
    plot_reduction_pct(df)
    plot_storage_bytes(df)
    plot_line_reduction(df)
    print("[rq2a] Done.")


if __name__ == "__main__":
    run()
