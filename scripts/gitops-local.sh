#!/usr/bin/env bash
# GitOps on the local kind cluster: build the images for a commit, load them,
# and let Argo CD deploy that commit (the same SHA-to-image mapping CI uses
# with GHCR on main).
#   scripts/gitops-local.sh [revision]   (default: the current branch, pushed)
set -euo pipefail

revision="${1:-$(git rev-parse --abbrev-ref HEAD)}"
sha="$(git rev-parse "origin/$revision" 2>/dev/null || git rev-parse "$revision")"
kubectl="kubectl --context kind-opspilot"

docker build -q -f apps/api/Dockerfile -t "opspilot-api:$sha" .
docker build -q -f apps/web/Dockerfile -t "opspilot-web:$sha" .
kind load docker-image "opspilot-api:$sha" "opspilot-web:$sha" --name opspilot

# The development Application, pointed at local images and this revision.
sed -e "s|targetRevision: main|targetRevision: $revision|" \
  infrastructure/argocd/applications/opspilot-development.yaml \
  | $kubectl apply -f -
$kubectl -n argocd patch application opspilot-development --type merge -p '{
  "spec": {"source": {"helm": {"parameters": [
    {"name": "image.api.tag", "value": "$ARGOCD_APP_REVISION"},
    {"name": "image.web.tag", "value": "$ARGOCD_APP_REVISION"},
    {"name": "image.api.repository", "value": "opspilot-api"},
    {"name": "image.web.repository", "value": "opspilot-web"},
    {"name": "image.pullPolicy", "value": "Never"}]}}}}'
echo "deploying $revision at $sha"
