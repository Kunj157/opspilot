# OpsPilot on AWS (Terraform)

Everything an environment needs, created from code with no console steps:
network, EKS, PostgreSQL, Redis, container registry, buckets, secrets, DNS and
certificate, alerting, the CI deploy role, and cost controls.

```
bootstrap/                 state bucket, audit trail, GuardDuty (once per AWS account, local state)
modules/                   network, eks, rds, redis, ecr, s3, secrets, iam, dns, observability
modules/audit/             multi-region CloudTrail into a locked-down bucket; optional GuardDuty
modules/environment/       one environment composed from the modules, plus budgets and schedules
environments/<name>/       development, staging, production: separate state and settings
```

## Create an environment

Requires Terraform ≥ 1.10 and AWS credentials for the target account.

```bash
# 1. Once per account: the state bucket and the audit trail. List every
#    principal that may read or write state; everyone else is denied.
cd bootstrap
terraform init && terraform apply \
  -var state_bucket=opspilot-terraform-state-<account-id> \
  -var audit_bucket=opspilot-audit-<account-id> \
  -var 'admin_principal_arns=["arn:aws:iam::<account-id>:role/aws-reserved/sso.amazonaws.com/*/AWSReservedSSO_AdministratorAccess_*"]' \
  -var 'ci_principal_arns=["arn:aws:iam::<account-id>:role/opspilot-*-ci-deploy"]' \
  -var enable_guardduty=true

# 2. Each environment: S3 backend with S3-native locking, separate state key.
cd ../environments/development
cp ../backend.hcl.example ../backend.hcl            # bucket name and state key ARN
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

### State and audit

- The state bucket's policy denies every principal not listed in
  `admin_principal_arns` / `ci_principal_arns`, denies non-TLS requests, and
  rejects puts that ask for SSE-S3 or a key other than the state key. The
  backend therefore sets `kms_key_id` (see `backend.hcl.example`). If the
  list is wrong and locks everyone out, the account root user can still
  delete the bucket policy.
- A multi-region CloudTrail trail with log file validation records
  management events in every region, plus object-level reads and writes of
  the state bucket. Logs go to a versioned bucket that is KMS-encrypted,
  private, and TLS-only, owned by the bucket owner, and kept for 365 days.
  Its policy denies deleting log objects.
- `enable_guardduty` turns on GuardDuty with S3 data-event and EKS
  audit-log protection.

### Everything else

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

## Cost controls

- Small instances outside production: Graviton `t4g` nodes on Spot, and
  `db.t4g.micro` / `cache.t4g.micro`.
- One NAT gateway in development and staging, one per zone in production.
- Development and staging nodes scale to zero at 20:00 and back up at 07:00
  on weekdays (Europe/Berlin).
- An AWS Budget per environment alerts at 80 % of actual and 100 % of
  forecast spend.

Estimated monthly cost, from published eu-central-1 on-demand prices at the
time of writing. These are estimates, not measured bills; check them with
the AWS Pricing Calculator before applying.

| Environment | Main items | Estimate | Budget |
|---|---|---|---|
| development | EKS control plane, 2 × t4g.medium Spot in office hours, 1 NAT, db.t4g.micro, cache.t4g.micro | ≈ $160 | $250 |
| staging | as development with t4g.large nodes and db.t4g.small | ≈ $230 | $400 |
| production | EKS, 3 × m7g.large, 3 NAT, Multi-AZ db.m7g.large, Redis with a replica | ≈ $700 | $1,500 |

The EKS control plane ($0.10/h) and NAT gateways dominate small
environments. Destroy development when it is not in use.
