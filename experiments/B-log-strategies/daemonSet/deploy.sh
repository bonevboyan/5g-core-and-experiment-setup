#!/usr/bin/env bash
# B-log-strategies/daemonSet/deploy.sh
#
# Build, load, and deploy the streaming log-filter-agent DaemonSet(s).
#
# Usage:
#   bash daemonSet/deploy.sh                         
#   bash daemonSet/deploy.sh --strategy preproc
#   bash daemonSet/deploy.sh --strategy both         # deploy salo + preproc simultaneously
#   bash daemonSet/deploy.sh --data-dir <path>       # also re-export pre-trained data first
#   bash daemonSet/deploy.sh --teardown              # remove all DaemonSets
#
# When --strategy both is used, two DaemonSets are created:
#   log-filter-agent-salo   
#   log-filter-agent-preproc 
# Each pushes to Loki under its own job label so their output is queryable
# independently with collect.py.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../lib/common.sh"

# ──────────────────────────────────────────────────────────────────────────────
# Defaults / argument parsing
# ──────────────────────────────────────────────────────────────────────────────

STRATEGY="salo"
TEARDOWN=false
DATA_DIR_ARG=""
KIND_CLUSTER=""
NAMESPACE="open5gs"
IMAGE="log-filter-agent:latest"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --strategy)   STRATEGY="$2";      shift 2 ;;
        --data-dir)   DATA_DIR_ARG="$2";  shift 2 ;;
        --cluster)    KIND_CLUSTER="$2";  shift 2 ;;
        --namespace)  NAMESPACE="$2";     shift 2 ;;
        --teardown)   TEARDOWN=true;      shift   ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

PRETRAINED_DIR="$SCRIPT_DIR/pretrained"

# ──────────────────────────────────────────────────────────────────────────────
# Teardown
# ──────────────────────────────────────────────────────────────────────────────

if $TEARDOWN; then
    echo "[daemonSet] Removing all log-filter-agent DaemonSets ..."
    kubectl delete daemonset  log-filter-agent         -n "$NAMESPACE" --ignore-not-found
    kubectl delete daemonset  log-filter-agent-salo    -n "$NAMESPACE" --ignore-not-found
    kubectl delete daemonset  log-filter-agent-preproc -n "$NAMESPACE" --ignore-not-found
    kubectl delete configmap  log-filter-pretrained    -n "$NAMESPACE" --ignore-not-found
    echo "[daemonSet] Removed."
    exit 0
fi

# ──────────────────────────────────────────────────────────────────────────────
# Preflight
# ──────────────────────────────────────────────────────────────────────────────

if [[ "$STRATEGY" != "salo" && "$STRATEGY" != "preproc" && "$STRATEGY" != "both" ]]; then
    echo "ERROR: --strategy must be 'salo', 'preproc', or 'both'"
    exit 1
fi

echo "[preflight] checking dependencies..."
for cmd in docker kind kubectl python3; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "  MISSING: $cmd"
        exit 1
    fi
done

if [[ -z "$KIND_CLUSTER" ]]; then
    KIND_CLUSTER="$(kind get clusters 2>/dev/null | head -1 || true)"
    if [[ -z "$KIND_CLUSTER" ]]; then
        echo "ERROR: no running kind cluster found — start one first"
        exit 1
    fi
fi

echo "[preflight] cluster=$KIND_CLUSTER  strategy=$STRATEGY  namespace=$NAMESPACE"
echo "[preflight] all OK"

# ──────────────────────────────────────────────────────────────────────────────
# Step 1 — Export pre-trained data 
# ──────────────────────────────────────────────────────────────────────────────

if [[ -n "$DATA_DIR_ARG" ]]; then
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo " Step 1: Export pre-trained data from offline runs"
    echo "════════════════════════════════════════════════════════════"
    python3 "$SCRIPT_DIR/export_pretrained.py" \
        --data-dir "$DATA_DIR_ARG" \
        --out-dir  "$PRETRAINED_DIR"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Step 2 — Build Docker image
# ──────────────────────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════"
echo " Step 2: Build Docker image ($IMAGE)"
echo "════════════════════════════════════════════════════════════"
docker build -t "$IMAGE" "$SCRIPT_DIR"

# ──────────────────────────────────────────────────────────────────────────────
# Step 3 — Load into kind
# ──────────────────────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════"
echo " Step 3: Load image into kind cluster '$KIND_CLUSTER'"
echo "════════════════════════════════════════════════════════════"
kind load docker-image "$IMAGE" --name "$KIND_CLUSTER"

# ──────────────────────────────────────────────────────────────────────────────
# Step 4 — Create/update pre-trained ConfigMap
# ──────────────────────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════"
echo " Step 4: ConfigMap log-filter-pretrained"
echo "════════════════════════════════════════════════════════════"

RARE_FILE="$PRETRAINED_DIR/rare_templates.json"
RULES_FILE="$PRETRAINED_DIR/static_rules.json"

CM_ARGS=()
[[ -f "$RARE_FILE"  ]] && CM_ARGS+=(--from-file=rare_templates.json="$RARE_FILE")
[[ -f "$RULES_FILE" ]] && CM_ARGS+=(--from-file=static_rules.json="$RULES_FILE")

if [[ ${#CM_ARGS[@]} -gt 0 ]]; then
    kubectl create configmap log-filter-pretrained \
        "${CM_ARGS[@]}" -n "$NAMESPACE" \
        --dry-run=client -o yaml | kubectl apply -f -
    echo "  loaded: ${CM_ARGS[*]}"
else
    kubectl create configmap log-filter-pretrained \
        -n "$NAMESPACE" \
        --dry-run=client -o yaml | kubectl apply -f -
    echo "  (no pretrained files — agent will run without them)"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Step 5 — Deploy DaemonSet(s)
# ──────────────────────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════"
echo " Step 5: Apply DaemonSet(s) (strategy=$STRATEGY)"
echo "════════════════════════════════════════════════════════════"

deploy_one() {
    local strat="$1"        # salo | preproc
    local ds_name="log-filter-agent-${strat}"

    local env_pretrained=""
    if [[ "$strat" == "salo"   && -f "$RARE_FILE"  ]]; then
        env_pretrained=$'\n            - name: RARE_TEMPLATES_JSON\n              value: /pretrained/rare_templates.json'
    fi
    if [[ "$strat" == "preproc" && -f "$RULES_FILE" ]]; then
        env_pretrained=$'\n            - name: STATIC_RULES_JSON\n              value: /pretrained/static_rules.json'
    fi

    kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: ${ds_name}
  namespace: ${NAMESPACE}
  labels:
    app: log-filter-agent
    filter-strategy: "${strat}"
spec:
  selector:
    matchLabels:
      app: log-filter-agent
      filter-strategy: "${strat}"
  updateStrategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: log-filter-agent
        filter-strategy: "${strat}"
    spec:
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          effect: NoSchedule
      containers:
        - name: filter-agent
          image: ${IMAGE}
          imagePullPolicy: Never
          env:
            - name: FILTER_STRATEGY
              value: "${strat}"
            - name: LOKI_URL
              value: "http://loki.monitoring.svc.cluster.local:3100"
            - name: NAMESPACE
              value: "${NAMESPACE}"
            - name: BATCH_INTERVAL_S
              value: "1.0"
            - name: BATCH_LINES
              value: "200"
            - name: POLL_INTERVAL_S
              value: "0.25"${env_pretrained}
          volumeMounts:
            - name: podlogs
              mountPath: /var/log/pods
              readOnly: true
            - name: pretrained
              mountPath: /pretrained
              readOnly: true
            - name: output
              mountPath: /data
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "256Mi"
      volumes:
        - name: podlogs
          hostPath:
            path: /var/log/pods
            type: Directory
        - name: pretrained
          configMap:
            name: log-filter-pretrained
        - name: output
          emptyDir: {}
      terminationGracePeriodSeconds: 5
EOF
    echo "  [deploy] $ds_name applied"
}

if [[ "$STRATEGY" == "both" ]]; then
    deploy_one salo
    deploy_one preproc
else
    deploy_one "$STRATEGY"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Step 6 — Wait for rollout
# ──────────────────────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════"
echo " Step 6: Waiting for rollout ..."
echo "════════════════════════════════════════════════════════════"

rollout_wait() {
    local ds_name="$1"
    if kubectl get daemonset "$ds_name" -n "$NAMESPACE" >/dev/null 2>&1; then
        kubectl rollout status daemonset/"$ds_name" -n "$NAMESPACE" --timeout=120s
    fi
}

if [[ "$STRATEGY" == "both" ]]; then
    rollout_wait log-filter-agent-salo
    rollout_wait log-filter-agent-preproc
else
    rollout_wait "log-filter-agent-${STRATEGY}"
fi

echo ""
kubectl get pods -n "$NAMESPACE" -l app=log-filter-agent -o wide

echo ""
echo "════════════════════════════════════════════════════════════"
echo " log-filter-agent deployed  (strategy=$STRATEGY)"
echo ""
echo " Tail logs:  kubectl logs -n $NAMESPACE -l app=log-filter-agent -f"
echo " Status:     kubectl get pods -n $NAMESPACE -l app=log-filter-agent"
echo " Teardown:   bash daemonSet/deploy.sh --teardown"
echo "════════════════════════════════════════════════════════════"
