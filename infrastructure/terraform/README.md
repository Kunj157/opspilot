# OpsPilot on AWS (Terraform)

Everything an environment needs, created from code with no console steps:
network, EKS with Karpenter, PostgreSQL, Redis, container registry, buckets,
secrets, DNS and certificate, alerting, the CI deploy role, and cost controls.

```
bootstrap/                 state bucket (once per AWS account, local state)
modules/                   network, eks, rds, redis, ecr, s3, secrets, iam, dns, observability
modules/irsa/              one IAM role for named Kubernetes service accounts
modules/karpenter/         node autoscaling: IAM, interruption queue, chart, default NodePool
modules/environment/       one environment composed from the modules, plus budgets and schedules
environments/<name>/       development, staging, production: separate state and settings
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

Then delegate the environment's domain to the `name_servers` output, put the
OIDC client secret and model API key into the Secrets Manager entries
(`opspilot-<env>/...`), and point CI at the `ci_role_arn` output.

Destroy a temporary environment with `terraform destroy`. Development and
staging have deletion protection off. Production refuses to drop its
database, takes a final snapshot, and keeps the state bucket.

## Security

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

The EKS control plane ($0.10/h) and NAT gateways dominate small
environments. Destroy development when it is not in use.
