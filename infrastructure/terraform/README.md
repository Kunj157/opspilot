# OpsPilot on AWS (Terraform)

Everything an environment needs, created from code with no console steps:
network, EKS with Karpenter, PostgreSQL, Redis, container registry, buckets,
secrets, DNS and certificate, alerting, the CI deploy role, and cost controls.

```
bootstrap/                 state bucket (once per AWS account, local state)
modules/                   network, eks, rds, redis, ecr, s3, secrets, iam, dns, observability
modules/irsa/              one IAM role for named Kubernetes service accounts
modules/karpenter/         node autoscaling: IAM, interruption queue, chart, default NodePool
modules/addons/            load balancer controller, cert-manager, External Secrets, issuers, secret store
modules/environment/       one environment composed from the modules, plus budgets and schedules
environments/<name>/       development, staging, production, loadtest: separate state and settings
```

## Create an environment

Requires Terraform ≥ 1.10, the AWS CLI (the Helm provider signs in with
`aws eks get-token`), and AWS credentials for the target account.

```bash
# 1. Once per account: the encrypted, versioned state bucket.
cd bootstrap
terraform init && terraform apply -var state_bucket=opspilot-terraform-state-<account-id>

# 2. Each environment: S3 backend with S3-native locking, separate state key.
cd ../environments/development
cp ../backend.hcl.example ../backend.hcl            # set the bucket name
cp terraform.tfvars.example terraform.tfvars        # domain, alert e-mails
terraform init -backend-config=../backend.hcl
terraform plan -out=tfplan && terraform apply tfplan
```

Check the result with `make infra-smoke ENV=development` (wraps
`scripts/infra-smoke.sh`). Through a throwaway kubeconfig, it checks that
all nodes are Ready and the add-ons have rolled out (CoreDNS, VPC CNI,
metrics-server, Karpenter, load balancer controller, cert-manager, External
Secrets). It also checks that the node class, node pool, ClusterIssuer, and
ClusterSecretStore report Ready, that the app ExternalSecret has synced
once the chart is installed, and that a pod can reach PostgreSQL.

Then delegate the environment's domain to the `name_servers` output, put the
OIDC client secret and model API key into the Secrets Manager entries
(`opspilot-<env>/...`), and point CI at the `ci_role_arn` output.

`make tf-plan ENV=<environment>` runs the init and plan steps from the repository
root, and `make tf-check` runs fmt, validate, tflint, and checkov the way CI
does.

Destroy a temporary environment with `terraform destroy`. Development and
staging have deletion protection off. Production refuses to drop its
database, takes a final snapshot, and keeps the state bucket.

## Security

Every role, its trust, and its permissions, with the reason for each, are
listed in [docs/security/iam-review.md](../../docs/security/iam-review.md).

- Every store is encrypted with a customer-managed KMS key that rotates
  yearly: state, flow logs, EKS secrets, node disks, RDS, Redis, buckets,
  secrets, and alerts.
- Nothing is public. Databases sit in isolated subnets and accept only the
  cluster's security group. The EKS API is private, or limited to listed
  CIDRs and never `0.0.0.0/0`. Nodes allow IMDSv2 only.
- No secret passes through Terraform. RDS generates and rotates its master
  password in Secrets Manager, Redis uses IAM authentication, and
  application secrets are written out of band. Outputs carry ARNs, never
  values.
- CI deploys through GitHub OIDC: no long-lived AWS keys. The role is scoped
  to this repository's allowed refs and to pushing images.

`terraform fmt`, `validate`, tflint, and checkov run in CI for every root
and module. Checkov exceptions are justified next to the resource they
apply to.

## Capacity

The managed node group is a small, fixed `system` group (on-demand) that runs
the add-ons, Karpenter included. Every other pod is placed on nodes that
Karpenter launches for it:

- One `EC2NodeClass` (private subnets, the cluster security group that the
  databases trust, IMDSv2 only, encrypted gp3 disk) and one `default`
  `NodePool` (amd64, the architecture the images are built for; current
  generation c/m/r/t families; nodes replaced every 30 days).
- Development and staging allow Spot with on-demand fallback; production is
  on-demand only. Spot interruption, rebalance, and health events reach
  Karpenter through an SQS queue, so nodes are drained before AWS reclaims
  them.
- Idle or underused nodes are consolidated after one minute, at most 10 %
  of nodes at a time. A per-environment CPU limit (8 / 16 / 48 vCPU) caps
  spend.
- The controller role (IRSA) can only launch, tag, and terminate instances
  tagged for its own cluster, and pass only the Karpenter node role.

Chart versions are pinned in `modules/karpenter/variables.tf`.

## Cluster add-ons

Installed by Terraform as Helm releases with pinned chart versions
(`modules/addons/variables.tf`). Each has its own IRSA role:

| Add-on | Chart | What it may do in AWS |
|---|---|---|
| AWS Load Balancer Controller | eks-charts `aws-load-balancer-controller` 3.6.0 | Manage ALBs, target groups, and their security groups (upstream policy, `modules/addons/lbc-policy.json`) |
| cert-manager | jetstack `cert-manager` v1.21.2 | Write `_acme-challenge` TXT records in the environment's zone only |
| External Secrets Operator | `external-secrets` 2.12.0 | Read `opspilot-<env>/*` secrets and decrypt them through Secrets Manager |

Public traffic enters through an ALB (`ingressClassName: alb`) with the
environment's ACM certificate. ingress-nginx was retired in March 2026, so
it is not used; see [ADR-005](../../docs/adr/005-ingress-with-aws-load-balancer-controller.md).
cert-manager provides the `letsencrypt` and `letsencrypt-staging`
ClusterIssuers (Route53 DNS-01) for certificates that live in the cluster.
External Secrets provides the `aws-secrets-manager` ClusterSecretStore.

## Application roles

`modules/environment/app_iam.tf` creates one IRSA role per OpsPilot
workload, each trusted only by its service account in the `opspilot`
namespace (`app_namespace`), and outputs them as `app_role_arns`:

| Role | Service account | Permissions |
|---|---|---|
| `opspilot-<env>-app-api` | `opspilot-api` | Read the `opspilot-<env>/app` secret; `elasticache:Connect` as the Redis IAM user |
| `opspilot-<env>-app-worker` | `opspilot-worker` | As the API, plus read the ML model bucket |
| `opspilot-<env>-app-backup` | `opspilot-backup` | Read the app secret; list and put objects in the backup bucket (no object reads, no delete) |

KMS use is limited to decrypting through Secrets Manager or S3. The pods
get credentials when their service account carries the
`eks.amazonaws.com/role-arn` annotation with the matching ARN. Other
outputs the chart needs: `app_secret_name`, `redis_app_user`, `buckets`.

## Temporary load-test environment

`environments/loadtest` is the smallest composition (two zones, one system
node, Spot application nodes up to 16 vCPU, micro databases, 7-day logs,
$100 budget) with no deletion protection. Every resource it creates
carries a `ttl` tag from the required `expires_at` variable:

```bash
cd environments/loadtest
terraform init -backend-config=../backend.hcl
terraform apply -var expires_at=2026-10-20T18:00:00Z   # plus domain / alert_emails
```

The **Load-test teardown** workflow (`.github/workflows/loadtest-teardown.yml`)
runs hourly and on demand. It calls `scripts/loadtest-teardown.sh`, which
reads the earliest `ttl` tag of resources tagged `environment=loadtest`.
Once that time has passed, or when the run is forced, the script:

1. forgets the Helm releases, because the runner cannot reach the private
   cluster API and the releases go with the cluster;
2. destroys the EKS cluster, which stops Karpenter and the load balancer
   controller;
3. deletes what those controllers created outside Terraform: Karpenter
   instances and instance profiles, ALBs, target groups, and security
   groups;
4. runs `terraform destroy`.

Guards:
- The script's target, state key, and environment name are constants.
  It refuses to run unless the configuration really is the loadtest
  composition, and no workflow input can change the target.
- The workflow runs only on the default branch, in the `loadtest` GitHub
  environment (protect it with required reviewers for manual runs).
- It is a no-op until that environment defines `LOADTEST_TEARDOWN_ROLE_ARN`
  (plus `TF_STATE_BUCKET`, `TF_STATE_KMS_KEY_ARN`, `LOADTEST_DOMAIN`, and
  `LOADTEST_ALERT_EMAILS` as a JSON list).
- Give that role a trust policy for
  `repo:Kunj157/opspilot:environment:loadtest` only, and permissions
  limited to resources tagged `environment=loadtest` and the
  `opspilot/loadtest/*` state key.

Run it by hand with `make loadtest-teardown ARGS=--dry-run`.

## Cost controls

- Small instances outside production: a Graviton `t4g` system node,
  Spot application nodes, and `db.t4g.micro` / `cache.t4g.micro`.
- One NAT gateway in development and staging, one per zone in production.
- Application nodes follow load: Karpenter removes empty nodes and packs
  pods onto cheaper ones. The old clock-based scale-to-zero of the node
  group (`office_hours`) is off wherever Karpenter runs, because stopping
  the system group would stop Karpenter and strand its nodes; it remains
  available for a cluster without Karpenter.
- An AWS Budget per environment alerts at 80 % of actual and 100 % of
  forecast spend.

Estimated monthly cost, from published eu-central-1 on-demand prices at the
time of writing. These are estimates, not measured bills; check them with
the AWS Pricing Calculator before applying.

| Environment | Main items | Estimate | Budget |
|---|---|---|---|
| development | EKS control plane, 1 × t4g.medium system node, ≈ 2 small Spot application nodes, 1 NAT, db.t4g.micro, cache.t4g.micro | ≈ $190 | $250 |
| staging | as development with 2 system nodes and db.t4g.small | ≈ $250 | $400 |
| production | EKS, 2 × m7g.large system nodes, ≈ 3 on-demand application nodes, 3 NAT, Multi-AZ db.m7g.large, Redis with a replica | ≈ $750 | $1,500 |

A load-test environment costs about $6 per day (control plane, NAT, system
node, micro databases) plus the Spot nodes the test asks for. The EKS
control plane ($0.10/h) and NAT gateways dominate small environments.
Destroy development when it is not in use.
