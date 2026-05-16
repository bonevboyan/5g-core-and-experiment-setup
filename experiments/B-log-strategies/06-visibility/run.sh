#!/usr/bin/env bash
# B-log-strategies/06-visibility/run.sh
#
# Measure fault-event visibility for every strategy × scenario.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../lib/common.sh"

BASE="$DATA_DIR/B-log-strategies"

SCENARIOS=(steady bursty fault-pod-crash-amf fault-memory-pressure-upf fault-network-delay-nrf)

echo ""
echo "============================================================"
echo " B-06: Visibility measurement"
echo "============================================================"

for scenario in "${SCENARIOS[@]}"; do
    csv="$BASE/01-collect/$scenario/all_logs.csv"
    if [[ ! -f "$csv" ]]; then
        echo "[skip] $scenario — no baseline CSV"
        continue
    fi
    echo ""
    echo "--- $scenario ---"

    LS_ARG=""
    DN_ARG=""
    SA_ARG=""
    PP_ARG=""
    TL_ARG=""

    [[ -d "$BASE/02-logshrink/$scenario" ]]    && LS_ARG="--logshrink-dir     $BASE/02-logshrink/$scenario"
    [[ -d "$BASE/03-denum/$scenario" ]]         && DN_ARG="--denum-dir          $BASE/03-denum/$scenario"
    [[ -d "$BASE/04-salo/$scenario" ]]          && SA_ARG="--salo-dir           $BASE/04-salo/$scenario"
    [[ -d "$BASE/05-preprocessing/$scenario" ]] && PP_ARG="--preprocessing-dir  $BASE/05-preprocessing/$scenario"

    timeline="$BASE/01-collect/$scenario/timeline.json"
    [[ -f "$timeline" ]] && TL_ARG="--timeline $timeline"

    python3 "$SCRIPT_DIR/measure.py" \
        --original  "$csv" \
        --outdir    "$BASE/06-visibility/$scenario" \
        --scenario  "$scenario" \
        $LS_ARG $DN_ARG $SA_ARG $PP_ARG $TL_ARG
done

echo ""
echo "============================================================"
echo " B-06 Visibility complete."
echo "============================================================"
