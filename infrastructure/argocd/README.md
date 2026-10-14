# GitOps delivery

```
merge to main → CI builds, scans, signs, and pushes images tagged with the commit SHA
             → CI moves the git tag env/development to that commit
             → Argo CD syncs the development environment at the tag
             → Argo Rollouts canary: 10% → 25% → 50% → 100%, analysed against Prometheus
             → promoted, or aborted and left on the stable version
```

- `bootstrap/` pins Argo CD (v3.5.5), Argo Rollouts (v1.10.1), and, for
  kind, metrics-server. Install them with `make gitops-up`.
- `applications/opspilot-development.yaml` follows the git tag
  `env/development` and passes the synced commit SHA as the image tag
  (`$ARGOCD_APP_REVISION`), so every running pod traces back to a reviewed,
  merged commit. Sync history in Argo CD and the git log are the audit trail.

## Deploy only what was built

Following `main` directly races CI: Argo CD can sync a merge commit minutes
before its images are pushed, and the canary pods would sit in
`ImagePullBackOff`. Instead, the last job of `.github/workflows/images.yml`
(`promote`) runs only after every image of the commit was built, scanned
(Trivy), pushed, and signed (cosign keyless, with an SBOM attestation), and
then force-moves the tag `env/development` to that commit with the
workflow's `GITHUB_TOKEN`. It pushes a tag ref only — no commits are made on
anyone's behalf.

- The tag only moves forward: if it already points to a commit that is not
  an ancestor of the run's commit (an old run re-triggered), it is left alone.
- A failed build, scan, or signature leaves the tag — and development — on
  the previous good commit.
- `git ls-remote origin refs/tags/env/development` shows what development
  should be running; Argo CD shows the same SHA as its synced revision.
- Roll development back by moving the tag:
  `git push -f origin <good-sha>:refs/tags/env/development` (the next main
  build moves it forward again).
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

## Releases: staging and production

```
tag vX.Y.Z on main → release.yml: images for that commit exist, signatures and SBOM attestations verify
                   → every pull-request check reruns on the tag (agent evals and e2e included)
                   → digests, SBOMs, and release-metadata.json are attached to the GitHub release
                   → environment "staging": env/staging moves to the commit → Argo CD syncs staging
                   → environment "production" (required reviewer): approve → env/production moves
```

- No image is rebuilt for a release: staging and production run the exact
  digests that main built, signed, and development already ran.
- `applications/opspilot-staging.yaml` and `opspilot-production.yaml` are
  applied to each environment's own cluster (one Argo CD per cluster) and use
  `environments/staging|production/values.yaml`: managed databases through
  the `opspilot` Secret, slower canaries in production (5 minute pauses).
- The GitHub environments `staging` and `production` accept only `v*` tags;
  `production` waits for an approval in the Actions run.
- Create the release (notes) by hand as usual; the workflow waits up to ten
  minutes for it and then uploads `release-metadata.json` (version, commit,
  signer identity, image digests) and `sbom-api.spdx.json` /
  `sbom-web.spdx.json`.

### Rollback

- **During a canary**: the analysis aborts it on its own; by hand,
  `kubectl argo rollouts abort opspilot-api -n opspilot` (and `opspilot-web`)
  returns all traffic to the stable version.
- **After promotion**: move the environment tag back to the previous release,
  then Argo CD rolls that version out as a canary:
  `git push -f origin vPREV^{commit}:refs/tags/env/production`, or re-run
  the "Promote to production" job of the previous release's workflow run.
  `kubectl argo rollouts undo` alone is reverted by Argo CD's self-heal,
  because git still names the newer version.
- Rolling back does not downgrade the database: migrations have to stay
  compatible with the previous release (expand now, contract in a later
  release) so the older version runs against the newer schema.

## Admission-time signature verification

`bootstrap/kyverno` pins Kyverno (v1.19.1); install it on each environment
cluster before the Application
(`kubectl apply --server-side -k infrastructure/argocd/bootstrap/kyverno`).
The chart's `imageVerification` values then add the ClusterPolicy
`opspilot-verify-images`: a Pod using `ghcr.io/kunj157/opspilot-api*` or
`-web*` must carry a keyless signature whose certificate was issued by
`token.actions.githubusercontent.com` to
`https://github.com/Kunj157/opspilot/.github/workflows/images.yml@refs/heads/main`
(checked against the Rekor transparency log).

| Environment | Mode | Effect |
|---|---|---|
| development | Audit | violations land in PolicyReports, nothing is blocked |
| staging, production | Enforce | unsigned or foreign-signed Pods are rejected; images are pinned to the verified digest |

- cosign v3 in `images.yml` stores signatures as Sigstore bundles (OCI
  referrers), so the policy uses `type: SigstoreBundle`; if signing moves to
  the legacy `.sig` tags, switch it to `type: Cosign`.
- The policy applies to Pods only (`autogen-controllers: none`): mutating
  Deployment or Rollout templates would show up as drift in Argo CD.
- `kubectl get policyreports -A` shows the audit results.
- On kind, `scripts/gitops-local.sh` disables the policy: local images are
  unsigned and the cluster has no Kyverno.

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
