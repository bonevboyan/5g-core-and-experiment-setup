#!/usr/bin/env bash
# B-log-strategies/05-preprocessing/run.sh
#
# Apply 3-step log preprocessing to each collected scenario.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../lib/common.sh"

IN_BASE="$DATA_DIR/B-log-strategies/01-collect"
OUT_BASE="$DATA_DIR/B-log-strategies/05-preprocessing"

SCENARIOS=(steady bursty fault-pod-crash-amf fault-memory-pressure-upf fault-network-delay-nrf)

echo ""
echo "============================================================"
echo " B-05: Log Preprocessing"
echo "============================================================"

for scenario in "${SCENARIOS[@]}"; do
    csv="$IN_BASE/$scenario/all_logs.csv"
    if [[ ! -f "$csv" ]]; then
        echo "[skip] $scenario — no CSV found"
        continue
    fi
    echo ""
    echo "--- $scenario ---"
    python3 "$SCRIPT_DIR/preprocess.py" \
        --csv      "$csv" \
        --outdir   "$OUT_BASE/$scenario" \
        --scenario "$scenario"
done

echo ""
echo "============================================================"
echo " B-05 Preprocessing complete."
echo "============================================================"
