# GitOps delivery

```
merge to main → CI builds, scans, signs, and pushes images tagged with the commit SHA
             → Argo CD syncs the development environment at that commit
             → Argo Rollouts canary: 10% → 25% → 50% → 100%, analysed against Prometheus
             → promoted, or aborted and left on the stable version
```

- `bootstrap/` pins Argo CD (v3.5.5), Argo Rollouts (v1.10.1), and, for
  kind, metrics-server. Install them with `make gitops-up`.
- `applications/opspilot-development.yaml` follows `main` and passes the
  synced revision as the image tag (`$ARGOCD_APP_REVISION`), so every
  running pod traces back to a reviewed, merged commit. Sync history in Argo
  CD and the git log are the audit trail.
- The chart's canary analysis aborts on a 5xx rate above 5 % or a p95 above
  500 ms. A canary that never becomes ready is aborted at its progress
  deadline (3 minutes). In both cases the stable version keeps serving.
- Migrations run as a Job per image between the databases and the workloads
  (sync waves).

## On the local kind cluster

There is no registry or CI on a laptop, so `scripts/gitops-local.sh [branch]`
builds the images for the branch's pushed commit, loads them into kind, and
registers the development Application for that branch with local images.
Push a commit, run the script again, and Argo CD rolls it out as a canary.

```bash
kubectl --context kind-opspilot -n opspilot get rollouts -w
kubectl --context kind-opspilot -n argocd get application opspilot-development
```
