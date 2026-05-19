#!/usr/bin/env bash
# B-log-strategies/01-collect/run.sh
#
# Collect raw Open5GS logs for each of five scenarios:
#   steady               — 10 min, 50 UEs, no fault injection   (live Loki query)
#   bursty               — 10 min, UE scale up/down cycles       (live Loki query)
#   fault-pod-crash-amf  — from data/C-fault-detection/03-pod-crash-amf
#   fault-memory-upf     — from data/C-fault-detection/02-memory-pressure-upf
#   fault-network-nrf    — from data/C-fault-detection/09-network-delay-nrf
#
# Fault scenarios reuse the ready-collected C-phase data
#
# Output:
#   $DATA_DIR/B-log-strategies/01-collect/<scenario>/

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../lib/common.sh"

FAULTS_ONLY=false
if [[ "${1:-}" == "--faults-only" ]]; then FAULTS_ONLY=true; fi

B_LIB="$SCRIPT_DIR/../lib"
OUT_BASE="$DATA_DIR/B-log-strategies/01-collect"
UE_COUNT=50
STEADY_DURATION=600    # 10 min
BURSTY_DURATION=600    # 10 min

# ──────────────────────────────────────────────────────────────────────────────
# Helper: collect raw Loki logs and write all_logs.csv to out_dir
# ──────────────────────────────────────────────────────────────────────────────
collect_raw() {
    local start="$1" end="$2" out_dir="$3"
    mkdir -p "$out_dir"
    start_portforward monitoring svc/loki 3100 3100
    python3 "$B_LIB/collect_raw_loki.py" \
        --url   "$LOKI_URL" \
        --start "$start" \
        --end   "$end" \
        --out   "$out_dir"
}

if [[ "$FAULTS_ONLY" == false ]]; then
    check_cluster_ready
    ensure_portforward_loki
fi

echo ""
echo "============================================================"
echo " B-01: Raw log collection"
echo "============================================================"

if [[ "$FAULTS_ONLY" == false ]]; then
# ──────────────────────────────────────────────────────────────────────────────
# Steady-state
# ──────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- Steady-state (${STEADY_DURATION}s, ${UE_COUNT} UEs) ---"
reset_experiment_state "B-collect-steady" "$UE_COUNT"
scale_ues "$UE_COUNT"
wait_for_pods_stable open5gs 120

T0=$(now_ts)
sleep_with_progress "$STEADY_DURATION" "steady collection"
T1=$(now_ts)

collect_raw "$T0" "$T1" "$OUT_BASE/steady"

# ──────────────────────────────────────────────────────────────────────────────
# Bursty
# ──────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- Bursty (${BURSTY_DURATION}s, UE scale cycles) ---"
reset_experiment_state "B-collect-bursty" "$UE_COUNT"
scale_ues "$UE_COUNT"

T0=$(now_ts)
BURSTY_END=$(( T0 + BURSTY_DURATION ))
(
    while [[ $(date +%s) -lt $BURSTY_END ]]; do
        scale_ues "$UE_COUNT" 2>/dev/null || true
        sleep 30
        scale_ues 5 2>/dev/null || true
        sleep 30
    done
) &
BURST_PID=$!

sleep_with_progress "$BURSTY_DURATION" "bursty collection"
T1=$(now_ts)
wait "$BURST_PID" 2>/dev/null || true

collect_raw "$T0" "$T1" "$OUT_BASE/bursty"

else
    echo "[skip] Steady and bursty scenarios (--faults-only)"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Use pre-collected C-fault-detection data 
# ──────────────────────────────────────────────────────────────────────────────
use_ready_fault_data() {
    local fault_name="$1" c_fault_dir="$2"
    local src="$REPO_ROOT/data/C-fault-detection/$c_fault_dir"
    local out_dir="$OUT_BASE/$fault_name"

    echo ""
    echo "--- Fault scenario: $fault_name (from ready data: $c_fault_dir) ---"

    if [[ ! -d "$src" ]]; then
        echo "[warn] C-fault-detection source not found: $src — skipping $fault_name"
        return
    fi

    mkdir -p "$out_dir"

    cp "$src/timeline.json" "$out_dir/timeline.json"
    echo "  [copy] timeline.json"

    # Merge pre + during + post Loki CSVs into a single all_logs.csv.
    python3 - "$src" "$out_dir/all_logs.csv" <<'PYEOF'
import csv, sys
from pathlib import Path

src  = Path(sys.argv[1])
dest = Path(sys.argv[2])

phases = ["pre", "during", "post"]
rows = []
for phase in phases:
    p = src / "loki" / phase / "all.csv"
    if not p.exists():
        print(f"  [warn] missing {p}", flush=True)
        continue
    with open(p, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

rows.sort(key=lambda r: int(r["timestamp_ns"]))

fieldnames = ["timestamp_ns", "pod", "container", "app", "line"]
with open(dest, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"  [merge] {len(rows)} rows → {dest}", flush=True)
PYEOF
}

use_ready_fault_data "fault-pod-crash-amf"       "03-pod-crash-amf"
use_ready_fault_data "fault-memory-pressure-upf"  "02-memory-pressure-upf"
use_ready_fault_data "fault-network-delay-nrf"    "09-network-delay-nrf"

echo ""
echo "============================================================"
echo " B-01 collection complete. Data in: $OUT_BASE"
echo "============================================================"
