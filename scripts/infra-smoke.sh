#!/usr/bin/env bash
# Smoke test for an AWS environment right after `terraform apply`:
#
#   scripts/infra-smoke.sh <development|staging|production|loadtest>
#
# Checks that nodes are Ready, the add-ons are rolled out and healthy,
# Karpenter's node class and pool are ready, a pod can reach PostgreSQL, and
# External Secrets can read Secrets Manager (and has synced the app secret if
# the chart is installed). Uses a throwaway kubeconfig, so your current
# context is never changed. Needs terraform, the aws CLI, and kubectl, with
# credentials that have cluster access.
set -uo pipefail

environment="${1:-}"
case "$environment" in
  development | staging | production | loadtest) ;;
  *) echo "usage: $0 <development|staging|production|loadtest>" >&2; exit 2 ;;
esac

root="$(cd "$(dirname "$0")/.." && pwd)/infrastructure/terraform/environments/${environment}"
app_namespace="${APP_NAMESPACE:-opspilot}"
timeout="${SMOKE_TIMEOUT:-180s}"
failures=0

pass() { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; failures=$((failures + 1)); }
check() { # check <description> <command...>
  local description="$1"; shift
  if "$@" >/dev/null 2>&1; then pass "$description"; else fail "$description"; fi
}

outputs="$(terraform -chdir="$root" output -json environment)" || { echo "no terraform outputs for ${environment}; apply it first" >&2; exit 1; }
field() { python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1" <<<"$outputs"; }
cluster="$(field cluster_name)"
db_host="$(field database_endpoint)"
issuer="$(field cluster_issuer)"
store="$(field secret_store)"

KUBECONFIG="$(mktemp)"
export KUBECONFIG
trap 'rm -f "$KUBECONFIG"' EXIT
aws eks update-kubeconfig --name "$cluster" --kubeconfig "$KUBECONFIG" >/dev/null || { echo "cannot reach cluster ${cluster}" >&2; exit 1; }
k() { kubectl --request-timeout=20s "$@"; }

echo "Nodes"
nodes="$(k get nodes --no-headers 2>/dev/null)"
if [ -n "$nodes" ] && ! awk '$2 !~ /^Ready/ {bad=1} END {exit !bad}' <<<"$nodes"; then
  pass "$(wc -l <<<"$nodes" | tr -d ' ') node(s), all Ready"
else
  fail "nodes Ready"; printf '%s\n' "$nodes" | sed 's/^/        /'
fi

echo "Add-ons"
for deployment in \
  kube-system/coredns \
  kube-system/karpenter \
  kube-system/aws-load-balancer-controller \
  kube-system/metrics-server \
  cert-manager/cert-manager \
  cert-manager/cert-manager-webhook \
  cert-manager/cert-manager-cainjector \
  external-secrets/external-secrets \
  external-secrets/external-secrets-webhook \
  external-secrets/external-secrets-cert-controller; do
  check "${deployment} rolled out" k -n "${deployment%%/*}" rollout status "deployment/${deployment#*/}" --timeout="$timeout"
done
check "aws-node (VPC CNI) rolled out" k -n kube-system rollout status daemonset/aws-node --timeout="$timeout"

# shellcheck disable=SC2329 # invoked through check
ready() { # ready <kind/name> [namespace]
  k ${2:+-n "$2"} wait --for=condition=Ready "$1" --timeout="$timeout"
}
check "EC2NodeClass default Ready" ready ec2nodeclass/default
check "NodePool default Ready" ready nodepool/default
check "ClusterIssuer ${issuer} Ready" ready "clusterissuer/${issuer}"
check "ClusterSecretStore ${store} Ready (Secrets Manager reachable with IRSA)" ready "clustersecretstore/${store}"

echo "Secrets"
if k -n "$app_namespace" get externalsecret opspilot >/dev/null 2>&1; then
  check "ExternalSecret ${app_namespace}/opspilot synced" ready externalsecret/opspilot "$app_namespace"
  check "Secret ${app_namespace}/opspilot exists" k -n "$app_namespace" get secret opspilot
else
  pass "chart not installed yet: no ExternalSecret to check (store checked above)"
fi

echo "Database"
pod="infra-smoke-$(date +%s)"
overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":70,"seccompProfile":{"type":"RuntimeDefault"}},
  "containers":[{"name":"probe","image":"postgres:17-alpine","command":["pg_isready","-h","'"$db_host"'","-p","5432","-t","10"],
  "securityContext":{"allowPrivilegeEscalation":false,"readOnlyRootFilesystem":true,"capabilities":{"drop":["ALL"]}}}]}}'
if k run "$pod" -n default --rm -i --restart=Never --quiet --image=postgres:17-alpine \
  --overrides="$overrides" --pod-running-timeout="$timeout" >/dev/null 2>&1; then
  pass "PostgreSQL ${db_host}:5432 accepts connections from a pod"
else
  fail "PostgreSQL ${db_host}:5432 reachable from a pod"
  k -n default delete pod "$pod" --ignore-not-found >/dev/null 2>&1
fi

echo
if [ "$failures" -eq 0 ]; then echo "infra smoke: all checks passed"; else echo "infra smoke: ${failures} check(s) failed"; fi
exit $((failures > 0))
