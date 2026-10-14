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
- Every canary gets its own Service (`opspilot-api-canary`,
  `opspilot-web-canary`). Right after the first weight, an `opspilot-smoke`
  analysis Job calls the canary pods only (API `/api/v1/health` and
  `/api/v1/ready`; web `/` and `/login`); a failure aborts the rollout before
  more traffic shifts. The web canary is additionally checked for
  availability every 30 s for the rest of the rollout
  (`opspilot-web-availability`, one failure tolerated).
- After every sync, an Argo CD PostSync hook Job (`opspilot-smoke`) runs the
  same smoke test against the stable Services; a failure marks the sync
  failed in Argo CD. The smoke Jobs run from the API image as a non-root user
  with a read-only root filesystem and no service account token.
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

Verified on kind: a new commit synced, the API canary paused at 10 %, 25 %,
and 50 % with a successful Prometheus analysis, and was promoted. A commit
whose API image never became ready was aborted at the progress deadline, and
the previous version kept serving.
