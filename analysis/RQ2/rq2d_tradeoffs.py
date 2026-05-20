"""
analysis/RQ2/rq2d_tradeoffs.py

RQ2 trade-off analysis: visualise the tension between telemetry reduction,
processing overhead, and retained system visibility.

Three views:
  1. Pareto scatter — reduction_pct vs fault_visibility_pct 
  2. Overhead scatter — cpu_s vs reduction_pct 
  3. Summary heatmap — all key metrics per strategy

Produces:
  figures/rq2d_pareto_reduction_visibility.pdf
  figures/rq2d_overhead_vs_reduction.pdf
  figures/rq2d_summary_heatmap.pdf
  tables/rq2d_tradeoff_comparison.csv
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import (
    FIGURES_DIR, TABLES_DIR, PALETTE, SCENARIO_LABELS, STRATEGY_LABELS,
    STRATEGIES, SCENARIOS,
    FIGURE_DPI, FIGURE_SIZE_SQUARE, FIGURE_SIZE_WIDE, FIGURE_SIZE_LARGE,
    FONT_SIZE_TITLE, FONT_SIZE_LABEL, FONT_SIZE_TICK, FONT_SIZE_LEGEND,
    SCENARIO_PALETTE,
)
from load_data import load_combined, load_all_strategy_metrics, load_all_visibility

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


def _pareto_front(df: pd.DataFrame, x_col: str, y_col: str) -> pd.DataFrame:
    """
    Return the subset of rows on the Pareto front (maximising both x and y).
    A point is Pareto-dominant if no other point has higher (or equal) values
    in both dimensions.
    """
    pts = df[[x_col, y_col]].dropna().values
    if len(pts) == 0:
        return pd.DataFrame()

    dominated = np.zeros(len(pts), dtype=bool)
    for i, p in enumerate(pts):
        for j, q in enumerate(pts):
            if i == j:
                continue
            if q[0] >= p[0] and q[1] >= p[1] and (q[0] > p[0] or q[1] > p[1]):
                dominated[i] = True
                break

    idx = df[[x_col, y_col]].dropna().index
    return df.loc[idx[~dominated]]


# ---------------------------------------------------------------------------
# Figure 1: Pareto scatter 
# ---------------------------------------------------------------------------

def plot_pareto_reduction_visibility(combined: pd.DataFrame):
    df = combined.dropna(subset=["reduction_pct", "fault_visibility_pct"]).copy()

    if df.empty:
        print("  [rq2d] No data for Pareto plot — skipping.")
        return

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_SQUARE, dpi=FIGURE_DPI)

    for strat in STRATEGIES:
        pts = df[df["strategy"] == strat]
        if pts.empty:
            continue
        scatter_colors = [SCENARIO_PALETTE.get(s, "#888888") for s in pts["scenario"]]
        ax.scatter(pts["reduction_pct"], pts["fault_visibility_pct"],
                   s=80, color=scatter_colors,
                   marker=_marker(strat), label=STRATEGY_LABELS[strat],
                   edgecolors=PALETTE[strat], linewidths=1.5, zorder=3)

    means = df.groupby("strategy")[["reduction_pct", "fault_visibility_pct"]].mean().reset_index()
    pareto = _pareto_front(means, "reduction_pct", "fault_visibility_pct")
    if not pareto.empty:
        pareto_sorted = pareto.sort_values("reduction_pct")
        ax.plot(pareto_sorted["reduction_pct"], pareto_sorted["fault_visibility_pct"],
                "k--", linewidth=1.2, zorder=2, label="Pareto front (mean)")
        for _, row in pareto_sorted.iterrows():
            ax.annotate(STRATEGY_LABELS[row["strategy"]],
                        (row["reduction_pct"], row["fault_visibility_pct"]),
                        textcoords="offset points", xytext=(5, 5),
                        fontsize=FONT_SIZE_TICK - 1)

    ax.set_xlabel("Storage reduction (%)", fontsize=FONT_SIZE_LABEL)
    ax.set_ylabel("Fault visibility retained (%)", fontsize=FONT_SIZE_LABEL)
    ax.set_title("RQ2d — Pareto: reduction vs. fault visibility",
                 fontsize=FONT_SIZE_TITLE)
    ax.set_xlim(-5, 105)
    ax.set_ylim(-5, 115)

    handles = [mlines.Line2D([], [], marker=_marker(s),
                             color=PALETTE[s], linestyle="None", markersize=7,
                             label=STRATEGY_LABELS[s])
               for s in STRATEGIES if s in df["strategy"].values]
    ax.legend(handles=handles, fontsize=FONT_SIZE_LEGEND, loc="lower left")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    ax.annotate("", xy=(100, 100), xytext=(80, 80),
                arrowprops=dict(arrowstyle="->", color="gray", lw=0.8))
    ax.text(82, 79, "ideal\n(top-right)", fontsize=FONT_SIZE_TICK - 1,
            color="gray", ha="left")

    fig.tight_layout()
    out = FIGURES_DIR / "rq2d_pareto_reduction_visibility.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2d] Saved {out}")


def _marker(strat: str) -> str:
    return {"logshrink": "o", "denum": "s", "salo": "^", "preprocessing": "D"}.get(strat, "o")


# ---------------------------------------------------------------------------
# Figure 2: Overhead scatter 
# ---------------------------------------------------------------------------

def plot_overhead_vs_reduction(metrics: pd.DataFrame):
    df = metrics.dropna(subset=["cpu_s", "reduction_pct"]).copy()

    if df.empty:
        print("  [rq2d] No cpu/reduction data — skipping overhead scatter.")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 4), dpi=FIGURE_DPI)

    for ax, y_col, ylabel in [
        (axes[0], "cpu_s",       "CPU time (s)"),
        (axes[1], "peak_mem_mb", "Peak memory (MiB)"),
    ]:
        sub = df.dropna(subset=[y_col])
        if sub.empty:
            continue
        for strat in STRATEGIES:
            pts = sub[sub["strategy"] == strat]
            if pts.empty:
                continue
            ax.scatter(pts["reduction_pct"], pts[y_col],
                       s=80, color=PALETTE[strat],
                       marker=_marker(strat), label=STRATEGY_LABELS[strat],
                       alpha=0.85, zorder=3)
            for _, row in pts.iterrows():
                ax.annotate(SCENARIO_LABELS.get(row["scenario"], row["scenario"])[:8],
                            (row["reduction_pct"], row[y_col]),
                            textcoords="offset points", xytext=(3, 3),
                            fontsize=FONT_SIZE_TICK - 2, alpha=0.7)

        ax.set_xlabel("Storage reduction (%)", fontsize=FONT_SIZE_LABEL)
        ax.set_ylabel(ylabel, fontsize=FONT_SIZE_LABEL)
        ax.legend(fontsize=FONT_SIZE_LEGEND - 1)
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.set_axisbelow(True)

    axes[0].set_title("RQ2d — CPU overhead vs. reduction", fontsize=FONT_SIZE_TITLE)
    axes[1].set_title("RQ2d — Memory overhead vs. reduction", fontsize=FONT_SIZE_TITLE)

    fig.tight_layout()
    out = FIGURES_DIR / "rq2d_overhead_vs_reduction.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2d] Saved {out}")


# ---------------------------------------------------------------------------
# Figure 3: Summary heatmap
# ---------------------------------------------------------------------------

def _fmt_cell(col: str, v: float) -> str:
    """Format a raw metric value for display in a heatmap cell."""
    if np.isnan(v):
        return ""
    if col.endswith("_pct") or col == "reduction_pct":
        return f"{v:.1f}%"
    if col == "compression_ratio":
        return f"{v:.1f}×"
    if col in ("cpu_s", "query_latency_s", "total_query_latency_s"):
        return f"{v:.2f}s"
    if col == "peak_mem_mb":
        return f"{v:.0f}M"
    return f"{v:.2f}"


def _normalise_col(col: str, series: pd.Series, higher_better: bool) -> pd.Series:
    """
    Normalise a metric column to [0, 1].
    """
    vals = series.replace([np.inf, -np.inf], np.nan)
    finite = vals.dropna()
    if finite.empty:
        return pd.Series(np.nan, index=series.index)

    is_pct = col.endswith("_pct") or col == "reduction_pct"
    if is_pct:
        result = vals / 100.0
    else:
        mn, mx = finite.min(), finite.max()
        if mx == mn:
            result = pd.Series(1.0, index=series.index)
        elif higher_better:
            result = (vals - mn) / (mx - mn)
        else:
            result = 1.0 - (vals - mn) / (mx - mn)

    if not higher_better and not is_pct:
        pass
    elif not higher_better and is_pct:
        result = 1.0 - result

    return result


def plot_summary_heatmap(metrics: pd.DataFrame, vis: pd.DataFrame):
    """
    One column per metric, one row per strategy (averaged across scenarios).
    """
    m_mean = metrics.groupby("strategy").mean(numeric_only=True)
    v_mean = vis.groupby("strategy").mean(numeric_only=True) if not vis.empty else pd.DataFrame()

    metric_config = [
        ("reduction_pct",              "Reduction\n(%)",              True),
        ("compression_ratio",          "Compression\nratio",          True),
        ("fault_visibility_pct",       "Fault\nvisibility (%)",       True),
        ("fault_window_retention_pct", "Fault window\nretention (%)", True),
        ("fault_line_retention_pct",   "Fault line\nretention (%)",   True),
        ("total_retention_pct",        "Total\nretention (%)",        True),
        ("novelty_retention_pct",      "Novelty\nretention (%)",      True),
        ("cpu_s",                      "CPU\ntime (s)",               False),
        ("peak_mem_mb",                "Peak\nmem (MiB)",             False),
        ("query_latency_s",            "Query\nlatency (s)",          False),
    ]

    rows = {}
    for strat in STRATEGIES:
        row = {}
        for col, _, _ in metric_config:
            if col in m_mean.columns and strat in m_mean.index:
                row[col] = float(m_mean.loc[strat, col])
            elif col in v_mean.columns and strat in v_mean.index:
                row[col] = float(v_mean.loc[strat, col])
            else:
                row[col] = np.nan
        rows[strat] = row

    raw = pd.DataFrame(rows, index=[c for c, _, _ in metric_config]).T

    normalised = raw.copy()
    for col, _, higher_better in metric_config:
        if col not in raw.columns:
            continue
        normalised[col] = _normalise_col(col, raw[col], higher_better)

    normalised = normalised.dropna(how="all")
    if normalised.empty:
        print("  [rq2d] No data for summary heatmap — skipping.")
        return

    row_labels   = [STRATEGY_LABELS.get(s, s) for s in normalised.index]
    present_cols = [c for c, _, _ in metric_config if c in normalised.columns]
    col_labels   = [lbl for c, lbl, _ in metric_config if c in present_cols]
    color_matrix = normalised[present_cols].values.astype(float)

    # String annotation matrix from raw values.
    annot_matrix = np.empty(color_matrix.shape, dtype=object)
    for j, col in enumerate(present_cols):
        for i, strat in enumerate(normalised.index):
            v = raw.loc[strat, col] if strat in raw.index else np.nan
            annot_matrix[i, j] = _fmt_cell(col, v)

    fig, ax = plt.subplots(figsize=(max(8, len(col_labels) * 1.3),
                                   max(3, len(row_labels) * 0.9)),
                           dpi=FIGURE_DPI)

    if _HAS_SEABORN:
        import seaborn as sns
        sns.heatmap(color_matrix,
                    xticklabels=col_labels,
                    yticklabels=row_labels,
                    annot=annot_matrix, fmt="",
                    cmap="RdYlGn",
                    vmin=0, vmax=1,
                    linewidths=0.5, ax=ax,
                    annot_kws={"size": FONT_SIZE_TICK - 1},
                    cbar_kws={"label": "Normalised score (green = better)"})
    else:
        im = ax.imshow(color_matrix, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
        plt.colorbar(im, ax=ax, label="Normalised score (green = better)")
        ax.set_xticks(range(len(col_labels)))
        ax.set_yticks(range(len(row_labels)))
        ax.set_xticklabels(col_labels, fontsize=FONT_SIZE_TICK, rotation=30, ha="right")
        ax.set_yticklabels(row_labels, fontsize=FONT_SIZE_TICK)
        for i in range(len(row_labels)):
            for j in range(len(col_labels)):
                txt = annot_matrix[i, j]
                if txt:
                    ax.text(j, i, txt, ha="center", va="center",
                            fontsize=FONT_SIZE_TICK - 1)

    ax.set_title("RQ2d — Strategy comparison (cell = raw value, colour = normalised)",
                 fontsize=FONT_SIZE_TITLE)

    fig.tight_layout()
    out = FIGURES_DIR / "rq2d_summary_heatmap.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq2d] Saved {out}")


# ---------------------------------------------------------------------------
# Table: trade-off comparison
# ---------------------------------------------------------------------------

def save_tradeoff_table(metrics: pd.DataFrame, vis: pd.DataFrame):
    m_mean = metrics.groupby("strategy").mean(numeric_only=True).reset_index()
    m_mean["strategy_label"] = m_mean["strategy"].map(STRATEGY_LABELS)

    if not vis.empty:
        v_mean = vis.groupby("strategy").mean(numeric_only=True).reset_index()
        merged = m_mean.merge(v_mean, on="strategy", how="outer", suffixes=("", "_vis"))
    else:
        merged = m_mean

    cols = [
        "strategy_label", "reduction_pct", "compression_ratio",
        "cpu_s", "peak_mem_mb", "query_latency_s",
        "fault_visibility_pct", "fault_window_retention_pct",
        "fault_line_retention_pct", "total_retention_pct",
        "novelty_retention_pct",
    ]
    out_df = merged[[c for c in cols if c in merged.columns]].copy()

    rename = {
        "strategy_label":              "Strategy",
        "reduction_pct":               "Storage reduction (%)",
        "compression_ratio":           "Compression ratio (×)",
        "cpu_s":                       "CPU time (s)",
        "peak_mem_mb":                 "Peak memory (MiB)",
        "query_latency_s":             "Query latency (s)",
        "fault_visibility_pct":        "Fault visibility (%)",
        "fault_window_retention_pct":  "Fault-window retention (%)",
        "fault_line_retention_pct":    "Fault line retention (%)",
        "total_retention_pct":         "Total retention (%)",
        "novelty_retention_pct":       "Novelty retention (%)",
    }
    out_df = out_df.rename(columns={k: v for k, v in rename.items() if k in out_df.columns})

    path = TABLES_DIR / "rq2d_tradeoff_comparison.csv"
    out_df.to_csv(path, index=False, float_format="%.3f")
    print(f"  [rq2d] Saved {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run():
    print("[rq2d] Loading combined metrics...")
    metrics  = load_all_strategy_metrics()
    vis      = load_all_visibility()
    combined = load_combined()

    if metrics.empty and vis.empty:
        print("  [rq2d] No data available — skipping.")
        return

    if not metrics.empty and not vis.empty:
        save_tradeoff_table(metrics, vis)
        plot_pareto_reduction_visibility(combined)
        plot_overhead_vs_reduction(metrics)
        plot_summary_heatmap(metrics, vis)
    elif not metrics.empty:
        save_tradeoff_table(metrics, pd.DataFrame())
        plot_overhead_vs_reduction(metrics)
        plot_summary_heatmap(metrics, pd.DataFrame())
    else:
        print("  [rq2d] Only visibility data available — skipping overhead plots.")

    print("[rq2d] Done.")


if __name__ == "__main__":
    run()
