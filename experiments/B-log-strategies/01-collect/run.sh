#!/usr/bin/env bash
# B-log-strategies/01-collect/run.sh
#
# Collect raw Open5GS logs for each of five scenarios:
#   steady               — 10 min, 50 UEs, no fault injection
#   bursty               — 10 min, UE scale up/down cycles
#   fault-pod-crash-amf  — Chaos Mesh 03 (2 min pre + 5 min fault + 2 min post)
#   fault-memory-upf     — Chaos Mesh 02
#   fault-network-nrf    — Chaos Mesh 09
#
# Output:
#   $DATA_DIR/B-log-strategies/01-collect/<scenario>/
#
# Estimated runtime: ~55 minutes 

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
PRE_DURATION=120       # 2 min pre-fault baseline
FAULT_DURATION=300     # 5 min active fault window
POST_DURATION=120      # 2 min post-fault recovery

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

check_cluster_ready
ensure_portforward_loki

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
# run_fault.sh  + raw Loki overlay
# ──────────────────────────────────────────────────────────────────────────────
run_fault_scenario() {
    local fault_name="$1" manifest_file="$2"
    local out_dir="$OUT_BASE/$fault_name"

    echo ""
    echo "--- Fault scenario: $fault_name ---"
    reset_experiment_state "B-collect-$fault_name" "$UE_COUNT"
    scale_ues "$UE_COUNT"
    wait_for_pods_stable open5gs 120

    bash "$LIB_DIR/run_fault.sh" \
        --name           "$fault_name" \
        --manifest       "$CHAOS_DIR/$manifest_file" \
        --out            "$out_dir" \
        --pre-duration   "$PRE_DURATION" \
        --fault-duration "$FAULT_DURATION" \
        --post-duration  "$POST_DURATION" \
        --step           "5s"

    local timeline="$out_dir/timeline.json"
    if [[ -f "$timeline" ]]; then
        FULL_START=$(python3 -c \
            "import json; d=json.load(open('$timeline')); print(d['pre']['start'])")
        FULL_END=$(python3 -c \
            "import json; d=json.load(open('$timeline')); print(d['post']['end'])")
        collect_raw "$FULL_START" "$FULL_END" "$out_dir"
    else
        echo "[warn] timeline.json not found — skipping raw collection for $fault_name"
    fi
}

run_fault_scenario "fault-pod-crash-amf"       "03-pod-crash-amf.yaml"
run_fault_scenario "fault-memory-pressure-upf"  "02-memory-pressure-upf.yaml"
run_fault_scenario "fault-network-delay-nrf"    "09-network-delay-nrf.yaml"

echo ""
echo "============================================================"
echo " B-01 collection complete. Data in: $OUT_BASE"
echo "============================================================"
