#!/usr/bin/env bash
# B-log-strategies/run_all.sh
#
# Five-pass experiment runner - each pass is an independent scenario execution with its own ground truth.
#
#   Pass 1 — Raw collection → LogShrink + Denum
#             CPU measured via getrusage during each apply.py run.
#
#   Pass 2 — SALO sidecar
#             CPU measured via Prometheus container_cpu_usage_seconds_total
#             while the DaemonSet processes live pod logs.
#
#   Pass 3 — Preprocessing sidecar
#             Same as Pass 2.
#
#   Pass 4 — Drain sidecar (online log-cluster dedup via Drain3)
#             Same as Pass 2.
#
#   Pass 5 — Visibility + storage comparison across all strategies
#             using each strategy's own ground truth.
#
# Output:
#   $DATA_DIR/B-log-strategies/
#     01-collect/<scenario>/          pass-1
#     02-logshrink/<scenario>/        LogShrink compressed output + metrics.json
#     03-denum/<scenario>/            Denum compressed output + metrics.json
#     05-daemonSet/
#       run-salo/<scenario>/          pass-2
#         raw/all_logs.csv
#         salo-stream/filtered.csv    metrics.json
#       run-preproc/<scenario>/       pass-3
#         raw/all_logs.csv
#         preproc-stream/filtered.csv
#       run-drain/<scenario>/         pass-4
#         raw/all_logs.csv
#         drain-stream/filtered.csv
#     04-visibility/<scenario>/visibility_metrics.json   merged comparison
#
# Usage:
#   bash run_all.sh                      # full run (~4h 30m)
#   bash run_all.sh --from 2             # skip Pass 1, resume from SALO pass
#   bash run_all.sh --from 5             # skip to visibility pass only
#   bash run_all.sh --faults-only        # skip steady/bursty in all passes
#   bash run_all.sh --base-faults-only   # faults only in Pass 1; Passes 2-4 run all scenarios

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

FROM=1
FAULTS_ONLY=false
BASE_FAULTS_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --from)             FROM="$2"; shift 2 ;;
        --faults-only)      FAULTS_ONLY=true; shift ;;
        --base-faults-only) BASE_FAULTS_ONLY=true; shift ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

preflight() {
    local ok=1
    echo "[preflight] checking dependencies..."
    for pkg in pandas numpy pyppmd regex; do
        if ! python3 -c "import $pkg" 2>/dev/null; then
            echo "  MISSING python package: $pkg  →  pip install $pkg"
            ok=0
        fi
    done
    if ! command -v g++ >/dev/null 2>&1; then
        echo "  MISSING g++  →  sudo apt install build-essential"
        ok=0
    fi
    if [[ "$ok" -eq 0 ]]; then
        echo "[preflight] fix the above and re-run."
        exit 1
    fi
    echo "[preflight] all OK"
}

preflight

git -C "$SCRIPT_DIR" submodule update --init --recursive

BASE="$DATA_DIR/B-log-strategies"
INTER_PASS_SLEEP=120  

COLLECT_ARGS=""
SIDECAR_ARGS=""
if $FAULTS_ONLY; then
    COLLECT_ARGS="--faults-only"
    SIDECAR_ARGS="--faults-only"
elif $BASE_FAULTS_ONLY; then
    COLLECT_ARGS="--faults-only"
fi

run_pass() {
    local num="$1" name="$2"
    if [[ $num -lt $FROM ]]; then
        echo "[skip] Pass $num — $name"
        return 1
    fi
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo " Pass $num — $name"
    echo "════════════════════════════════════════════════════════════"
    return 0
}

# ──────────────────────────────────────────────────────────────────────────────
# Pass 1 — Raw collection + LogShrink + Denum
# ──────────────────────────────────────────────────────────────────────────────

if run_pass 1 "Raw collection + LogShrink + Denum"; then
    bash "$SCRIPT_DIR/01-collect/run.sh"   $COLLECT_ARGS
    bash "$SCRIPT_DIR/02-logshrink/run.sh"
    bash "$SCRIPT_DIR/03-denum/run.sh"
    echo ""
    echo "[done] Pass 1 complete. Cooling down ${INTER_PASS_SLEEP}s ..."
    sleep "$INTER_PASS_SLEEP"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Pass 2 — SALO
# ──────────────────────────────────────────────────────────────────────────────

if run_pass 2 "SALO → $BASE/05-daemonSet/run-salo/"; then
    bash "$SCRIPT_DIR/daemonSet/run.sh" \
        --strategy       salo \
        --run-tag        run-salo \
        --skip-visibility \
        $SIDECAR_ARGS
    echo ""
    echo "[done] Pass 2 complete. Cooling down ${INTER_PASS_SLEEP}s ..."
    sleep "$INTER_PASS_SLEEP"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Pass 3 — Preprocessing
# ──────────────────────────────────────────────────────────────────────────────

if run_pass 3 "Preprocessing → $BASE/05-daemonSet/run-preproc/"; then
    bash "$SCRIPT_DIR/daemonSet/run.sh" \
        --strategy       preproc \
        --run-tag        run-preproc \
        --skip-visibility \
        $SIDECAR_ARGS
    echo ""
    echo "[done] Pass 3 complete. Cooling down ${INTER_PASS_SLEEP}s ..."
    sleep "$INTER_PASS_SLEEP"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Pass 4 — Drain
# ──────────────────────────────────────────────────────────────────────────────

if run_pass 4 "Drain → $BASE/05-daemonSet/run-drain/"; then
    bash "$SCRIPT_DIR/daemonSet/run.sh" \
        --strategy       drain \
        --run-tag        run-drain \
        --skip-visibility \
        $SIDECAR_ARGS
    echo ""
    echo "[done] Pass 4 complete. Cooling down ${INTER_PASS_SLEEP}s ..."
    sleep "$INTER_PASS_SLEEP"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Pass 5 — Visibility comparison
# ──────────────────────────────────────────────────────────────────────────────

if run_pass 5 "Visibility comparison"; then
    bash "$SCRIPT_DIR/04-visibility/run.sh" \
        --raw-base            "$BASE/01-collect" \
        --salo-raw-base       "$BASE/05-daemonSet/run-salo/raw" \
        --preproc-raw-base    "$BASE/05-daemonSet/run-preproc/raw" \
        --drain-raw-base      "$BASE/05-daemonSet/run-drain/raw" \
        --logshrink-base      "$BASE/02-logshrink" \
        --denum-base          "$BASE/03-denum" \
        --salo-stream-base    "$BASE/05-daemonSet/run-salo/salo-stream" \
        --preproc-stream-base "$BASE/05-daemonSet/run-preproc/preproc-stream" \
        --drain-stream-base   "$BASE/05-daemonSet/run-drain/drain-stream"
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo " Group B complete."
echo "════════════════════════════════════════════════════════════"
