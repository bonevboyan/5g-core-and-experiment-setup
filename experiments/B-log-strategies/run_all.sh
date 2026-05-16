#!/usr/bin/env bash
# B-log-strategies/run_all.sh
#
# Runs all observability experiments in sequence.
#
# Phases:
#   01 — Raw log collection (steady, bursty, 3 fault scenarios)
#   02 — LogShrink compression
#   03 — Denum compression
#   04 — SALO
#   05 — Log preprocessing
#   06 — Visibility measurement
#
# Usage:
#   bash run_all.sh                      # run all phases
#   bash run_all.sh --from 03            # skip 01-02, start from Denum
#   bash run_all.sh --faults-only        # phase 01: skip steady/bursty, run only fault scenarios
#
# Estimated runtime: ~75 minutes (collection ~55 min + strategies ~20 min)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FROM=1
COLLECT_EXTRA_ARGS=""
if [[ "${1:-}" == "--from" && -n "${2:-}" ]]; then FROM="$2"; fi
if [[ "${1:-}" == "--faults-only" ]]; then COLLECT_EXTRA_ARGS="--faults-only"; fi

run_phase() {
    local num="$1" name="$2" script="$3" extra="${4:-}"
    if [[ "$num" -lt "$FROM" ]]; then
        echo "[skip] Phase B-$num ($name)"
        return
    fi
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo " B-$num: $name"
    echo "════════════════════════════════════════════════════════════"
    bash "$script" $extra
    echo "[done] B-$num complete."
    sleep 10
}

run_phase 1 "Raw log collection"           "$SCRIPT_DIR/01-collect/run.sh"  "$COLLECT_EXTRA_ARGS"
run_phase 2 "LogShrink"                    "$SCRIPT_DIR/02-logshrink/run.sh"
run_phase 3 "Denum"                        "$SCRIPT_DIR/03-denum/run.sh"
run_phase 4 "SALO"                         "$SCRIPT_DIR/04-salo/run.sh"
run_phase 5 "Log preprocessing"            "$SCRIPT_DIR/05-preprocessing/run.sh"
run_phase 6 "Visibility measurement"       "$SCRIPT_DIR/06-visibility/run.sh"

echo ""
echo "════════════════════════════════════════════════════════════"
echo " Group B complete."
echo "════════════════════════════════════════════════════════════"
