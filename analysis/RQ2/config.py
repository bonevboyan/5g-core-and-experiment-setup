"""
analysis/RQ2/config.py

Central configuration: paths, constants, plot styling 
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT   = Path(__file__).parent.parent.parent
DATA_ROOT   = REPO_ROOT / "data" / "experiments" / "B-log-strategies"
FIGURES_DIR = Path(__file__).parent / "figures"
TABLES_DIR  = Path(__file__).parent / "tables"

FIGURES_DIR.mkdir(parents=True, exist_ok=True)
TABLES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Experiment layout
# ---------------------------------------------------------------------------
STRATEGIES = ["logshrink", "denum", "salo", "preprocessing"]

STRATEGY_DIRS = {
    "logshrink":     DATA_ROOT / "02-logshrink",
    "denum":         DATA_ROOT / "03-denum",
    "salo":          DATA_ROOT / "05-sidecar" / "run-salo"    / "salo-stream",
    "preprocessing": DATA_ROOT / "05-sidecar" / "run-preproc" / "preproc-stream",
}

VISIBILITY_DIR = DATA_ROOT / "04-visibility"

VISIBILITY_KEYS = {
    "logshrink":     "logshrink",
    "denum":         "denum",
    "salo":          "salo-stream",
    "preprocessing": "preproc-stream",
}

STRATEGY_FROM_VIS_KEY = {v: k for k, v in VISIBILITY_KEYS.items()}

SCENARIOS = [
    "steady",
    "bursty",
    "fault-pod-crash-amf",
    "fault-memory-pressure-upf",
    "fault-network-delay-nrf",
]

FAULT_SCENARIOS = [
    "fault-pod-crash-amf",
    "fault-memory-pressure-upf",
    "fault-network-delay-nrf",
]

SCENARIO_LABELS = {
    "steady":                    "Steady-state",
    "bursty":                    "Bursty",
    "fault-pod-crash-amf":       "Fault: pod crash (AMF)",
    "fault-memory-pressure-upf": "Fault: mem pressure (UPF)",
    "fault-network-delay-nrf":   "Fault: net delay (NRF)",
}

STRATEGY_LABELS = {
    "logshrink":     "LogShrink",
    "denum":         "Denum",
    "salo":          "SALO",
    "preprocessing": "Log Preprocessing",
}
LOSSLESS_STRATEGIES  = {"logshrink", "denum"}
LOSSY_STRATEGIES     = {"salo", "preprocessing"}

# ---------------------------------------------------------------------------
# Plot styling
# ---------------------------------------------------------------------------
PALETTE = {
    "logshrink":     "#1565C0",   
    "denum":         "#E65100",   
    "salo":          "#2E7D32", 
    "preprocessing": "#6A1B9A",   
}

SCENARIO_PALETTE = {
    "steady":                    "#2196F3",
    "bursty":                    "#FF9800",
    "fault-pod-crash-amf":       "#F44336",
    "fault-memory-pressure-upf": "#9C27B0",
    "fault-network-delay-nrf":   "#009688",
}

FIGURE_EXT         = "png"
FIGURE_DPI         = 150
FIGURE_SIZE_SINGLE = (7, 4)
FIGURE_SIZE_WIDE   = (10, 4)
FIGURE_SIZE_TALL   = (7, 8)
FIGURE_SIZE_SQUARE = (6, 6)
FIGURE_SIZE_LARGE  = (12, 5)

FONT_SIZE_TITLE  = 11
FONT_SIZE_LABEL  = 10
FONT_SIZE_TICK   = 9
FONT_SIZE_LEGEND = 9
