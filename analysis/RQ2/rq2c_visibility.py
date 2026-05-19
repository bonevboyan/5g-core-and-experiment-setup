"""
analysis/RQ2/rq2c_visibility.py

RQ2 sub-question 2 (retained visibility): How well does each strategy
preserve fault signals after reduction?

Four visibility metrics:
  fault_visibility_pct        — fraction of fault-related log templates retained
  fault_line_retention_pct    — fraction of keyword-matched fault lines retained
  novelty_retention_pct       — fraction of novelty (new-template) anomalies retained
  fault_window_retention_pct  — fraction of lines from the fault injection window retained

Produces:
  figures/rq2c_fault_visibility_heatmap.pdf     — heatmap: strategy x scenario
  figures/rq2c_fault_visibility_bar.pdf         — grouped bar: fault_visibility_pct
  figures/rq2c_fault_window_retention.pdf       — bar: fault-window retention (fault scenarios)
  figures/rq2c_novelty_retention.pdf            — novelty anomaly retention
  tables/rq2c_visibility_summary.csv            — full table
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
    STRATEGIES, SCENARIOS, FAULT_SCENARIOS,
    FIGURE_DPI, FIGURE_SIZE_WIDE, FIGURE_SIZE_LARGE, FIGURE_SIZE_SQUARE,
    FONT_SIZE_TITLE, FONT_SIZE_LABEL, FONT_SIZE_TICK, FONT_SIZE_LEGEND,
)
from load_data import load_all_visibility

try:
    import seaborn as sns
    _HAS_SEABORN = True
except ImportError:
    _HAS_SEABORN = False


def _check_data(df: pd.DataFrame, label: str) -> bool:
    if df.empty:
        print(f"  [{label}] No data available — skipping.")
        return False
    return True


# ---------------------------------------------------------------------------
# Figure 1: Heatmap
# ---------------------------------------------------------------------------

def plot_visibility_heatmap(df: pd.DataFrame):
    pivot = df.pivot_table(index="strategy", columns="scenario",
                           values="fault_visibility_pct", aggfunc="mean")
    pivot = pivot.reindex(index=STRATEGIES, columns=SCENARIOS)

    pivot_present = pivot.dropna(how="all").dropna(axis=1, how="all")
    if pivot_present.empty:
        print("  [rq2c] No fault_visibility_pct data — skipping heatmap.")
        return

    row_labels = [STRATEGY_LABELS.get(s, s) for s in pivot_present.index]
    col_labels = [SCENARIO_LABELS.get(s, s) for s in pivot_present.columns]

    fig, ax = plt.subplots(figsize=(max(6, len(col_labels) * 1.5),
                                   max(3, len(row_labels) * 0.9)),
                           dpi=FIGURE_DPI)

    if _HAS_SEABORN:
        import seaborn as sns
        sns.heatmap(pivot_present.values,
                    xticklabels=col_labels,
                    yticklabels=row_labels,
                    annot=True, fmt=".1f", cmap="YlOrRd_r",
                    vmin=0, vmax=100,
                    linewidths=0.5, ax=ax,
                    cbar_kws={"label": "Fault visibility (%)"})
    else:
        im = ax.imshow(pivot_present.values.astype(float),
                       cmap="YlOrRd_r", vmin=0, vmax=100, aspect="auto")
        plt.colorbar(im, ax=ax, label="Fault visibility (%)")
        ax.set_xticks(range(len(col_labels)))
        ax.set_yticks(range(len(row_labels)))
        ax.set_xticklabels(col_labels, fontsize=FONT_SIZE_TICK, rotation=30, ha="right")
        ax.set_yticklabels(row_labels, fontsize=FONT_SIZE_TICK)
        for i in range(len(row_labels)):
            for j in range(len(col_labels)):
                v = pivot_present.values[i, j]
                if not np.isnan(v):
                    ax.text(j, i, f"{v:.1f}", ha="center", va="center",
                            fontsize=FONT_SIZE_TICK - 1)

    ax.set_title("RQ2c — Fault visibility retained after reduction (%)",
                 fontsize=FONT_SIZE_TITLE)
    ax.set_xlabel("Scenario", fontsize=FONT_SIZE_LABEL)
    ax.set_ylabel("Strategy", fontsize=FONT_SIZE_LABEL)

    fig.tight_layout()
    out = FIGURES_DIR / "rq2c_fault_visibility_heatmap.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2c] Saved {out}")


# ---------------------------------------------------------------------------
# Figure 2: Grouped bar — fault_visibility_pct + fault_line_retention_pct
# ---------------------------------------------------------------------------

def plot_fault_visibility_bar(df: pd.DataFrame):
    fault_df = df[df["scenario"].isin(FAULT_SCENARIOS)].copy()
    if fault_df.empty:
        fault_df = df.copy()
        title_note = "(all scenarios)"
    else:
        title_note = "(fault scenarios)"

    pivot_vis  = fault_df.pivot_table(index="scenario", columns="strategy",
                                      values="fault_visibility_pct", aggfunc="mean")
    pivot_line = fault_df.pivot_table(index="scenario", columns="strategy",
                                      values="fault_line_retention_pct", aggfunc="mean")
    pivot_vis  = pivot_vis.reindex(columns=STRATEGIES)
    pivot_line = pivot_line.reindex(columns=STRATEGIES)

    present_scenarios = [s for s in FAULT_SCENARIOS
                         if s in pivot_vis.index or s in pivot_line.index]
    if not present_scenarios:
        present_scenarios = fault_df["scenario"].unique().tolist()

    if not present_scenarios:
        print("  [rq2c] No data for fault visibility bar — skipping.")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 4), dpi=FIGURE_DPI)

    for ax, pivot, title, ylabel in [
        (axes[0], pivot_vis,  "Fault template visibility",  "Fault visibility (%)"),
        (axes[1], pivot_line, "Fault line retention",       "Fault line retention (%)"),
    ]:
        n_scen  = len(present_scenarios)
        n_strat = len(STRATEGIES)
        x       = np.arange(n_scen)
        width   = 0.7 / n_strat

        for i, strat in enumerate(STRATEGIES):
            if strat not in pivot.columns:
                continue
            vals = [float(pivot.loc[s, strat]) if s in pivot.index else np.nan
                    for s in present_scenarios]
            offset = (i - n_strat / 2 + 0.5) * width
            ax.bar(x + offset, vals, width * 0.9,
                   label=STRATEGY_LABELS[strat],
                   color=PALETTE[strat], alpha=0.85)

        ax.set_xticks(x)
        ax.set_xticklabels([SCENARIO_LABELS.get(s, s) for s in present_scenarios],
                           fontsize=FONT_SIZE_TICK, rotation=20, ha="right")
        ax.set_ylabel(ylabel, fontsize=FONT_SIZE_LABEL)
        ax.set_title(f"RQ2c — {title} {title_note}", fontsize=FONT_SIZE_TITLE)
        ax.legend(fontsize=FONT_SIZE_LEGEND - 1)
        ax.yaxis.grid(True, linestyle="--", alpha=0.5)
        ax.set_axisbelow(True)
        ax.set_ylim(0, 115)

    fig.tight_layout()
    out = FIGURES_DIR / "rq2c_fault_visibility_bar.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2c] Saved {out}")


# ---------------------------------------------------------------------------
# Figure 3: Fault-window retention 
# ---------------------------------------------------------------------------

def plot_fault_window_retention(df: pd.DataFrame):
    fault_df = df[df["scenario"].isin(FAULT_SCENARIOS)].dropna(
        subset=["fault_window_retention_pct"])

    if fault_df.empty:
        print("  [rq2c] No fault_window_retention_pct data — skipping.")
        return

    pivot = fault_df.pivot_table(index="scenario", columns="strategy",
                                 values="fault_window_retention_pct", aggfunc="mean")
    pivot = pivot.reindex(columns=STRATEGIES)
    present_scenarios = [s for s in FAULT_SCENARIOS if s in pivot.index]
    pivot = pivot.loc[present_scenarios]

    if pivot.empty:
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
        bars = ax.bar(x + offset, vals, width * 0.9,
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
    ax.set_ylabel("Lines retained from fault window (%)", fontsize=FONT_SIZE_LABEL)
    ax.set_title("RQ2c — Retention of log lines during fault injection window",
                 fontsize=FONT_SIZE_TITLE)
    ax.legend(fontsize=FONT_SIZE_LEGEND)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 115)

    fig.tight_layout()
    out = FIGURES_DIR / "rq2c_fault_window_retention.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2c] Saved {out}")


# ---------------------------------------------------------------------------
# Figure 4: Novelty anomaly retention 
# ---------------------------------------------------------------------------

def plot_novelty_retention(df: pd.DataFrame):
    nov_df = df.dropna(subset=["novelty_retention_pct"]).copy()
    if nov_df.empty:
        print("  [rq2c] No novelty_retention_pct data — skipping.")
        return

    pivot = nov_df.pivot_table(index="scenario", columns="strategy",
                               values="novelty_retention_pct", aggfunc="mean")
    pivot = pivot.reindex(columns=STRATEGIES)
    present_scenarios = [s for s in SCENARIOS if s in pivot.index]
    pivot = pivot.loc[present_scenarios]

    if pivot.empty:
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
    ax.set_ylabel("Novelty anomaly retention (%)", fontsize=FONT_SIZE_LABEL)
    ax.set_title("RQ2c — Retention of novelty (new-template) anomalies after reduction",
                 fontsize=FONT_SIZE_TITLE)
    ax.legend(fontsize=FONT_SIZE_LEGEND)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 115)

    fig.tight_layout()
    out = FIGURES_DIR / "rq2c_novelty_retention.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2c] Saved {out}")


# ---------------------------------------------------------------------------
# Table: visibility summary
# ---------------------------------------------------------------------------

def save_summary_table(df: pd.DataFrame):
    cols = [
        "strategy_label", "scenario",
        "total_retention_pct", "fault_line_retention_pct",
        "fault_visibility_pct", "novelty_retention_pct",
        "novelty_false_negative_pct", "fault_window_retention_pct",
        "input_fault_lines", "output_fault_lines",
    ]
    out_df = df[[c for c in cols if c in df.columns]].copy()

    rename = {
        "strategy_label":              "Strategy",
        "scenario":                    "Scenario",
        "total_retention_pct":         "Total retention (%)",
        "fault_line_retention_pct":    "Fault line retention (%)",
        "fault_visibility_pct":        "Fault visibility (%)",
        "novelty_retention_pct":       "Novelty retention (%)",
        "novelty_false_negative_pct":  "Novelty false-negative (%)",
        "fault_window_retention_pct":  "Fault window retention (%)",
        "input_fault_lines":           "Input fault lines",
        "output_fault_lines":          "Output fault lines",
    }
    out_df = out_df.rename(columns={k: v for k, v in rename.items() if k in out_df.columns})
    out_df["Scenario"] = out_df["Scenario"].map(lambda s: SCENARIO_LABELS.get(s, s))

    path = TABLES_DIR / "rq2c_visibility_summary.csv"
    out_df.to_csv(path, index=False, float_format="%.2f")
    print(f"  [rq2c] Saved {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run():
    print("[rq2c] Loading visibility metrics...")
    df = load_all_visibility()

    if not _check_data(df, "rq2c"):
        return

    save_summary_table(df)
    plot_visibility_heatmap(df)
    plot_fault_visibility_bar(df)
    plot_fault_window_retention(df)
    plot_novelty_retention(df)
    print("[rq2c] Done.")


if __name__ == "__main__":
    run()
