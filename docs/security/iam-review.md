# IAM policy review

Every IAM role, trust, and resource policy that the Terraform in
`infrastructure/terraform` creates, with the reason each permission exists.
`<env>` is `development`, `staging`, `production`, or `loadtest`, and every
role name starts with `opspilot-<env>-`. Review this file whenever a policy
changes. The review is a checklist, not a substitute for IAM Access
Analyzer on the applied account.

Last reviewed: 2026-10-14, against the code as of the Phase 14 changes.

## Principles

- No IAM users or long-lived keys. People use SSO roles. CI uses GitHub
  OIDC. Pods use IRSA, whose web-identity tokens last at most an hour.
- Each workload gets its own role. IRSA trust names one exact
  `namespace:serviceaccount` (the `irsa` module rejects wildcards) and
  requires the `sts.amazonaws.com` audience.
- Write access is scoped to named resources, or to tags that only this
  cluster sets. `"*"` appears only for actions that AWS does not scope by
  resource, and each case is listed below.
- KMS use by workloads always carries `kms:ViaService`. Keys can be used
  through the owning service only, never directly.

## Roles

### Cluster and nodes

| Role | Trusted by | Permissions | Why |
|---|---|---|---|
| `eks-cluster` | `eks.amazonaws.com` | `AmazonEKSClusterPolicy` | The control plane manages ENIs, load-balancer integration, and node lifecycle. AWS-managed, the minimum EKS supports. |
| `eks-node` | `ec2.amazonaws.com` | `AmazonEKSWorkerNodePolicy`, `AmazonEC2ContainerRegistryReadOnly`, `AmazonSSMManagedInstanceCore` | Nodes join the cluster, pull images, and allow SSM Session Manager access instead of SSH. IMDSv2 with hop limit 1 keeps pods away from these credentials. |
| `karpenter-node` | `ec2.amazonaws.com` | `AmazonEKSWorkerNodePolicy`, `AmazonEC2ContainerRegistryPullOnly`, `AmazonSSMManagedInstanceCore` | As `eks-node`, for Karpenter's nodes. `PullOnly` is narrower than `ReadOnly`. It joins through an `EC2_LINUX` access entry. |
| `vpc-cni` | IRSA `kube-system:aws-node` | `AmazonEKS_CNI_Policy` | The CNI assigns pod IPs. It runs under its own role rather than the node role, so pods never inherit ENI permissions. |
| `karpenter-controller` | IRSA `kube-system:karpenter` | Upstream Karpenter 1.15 reference policy (`modules/karpenter/controller-policy.json.tftpl`) | Launches and terminates instances. `RunInstances`/`CreateFleet`/`CreateLaunchTemplate`/`CreateTags` require the request tags `kubernetes.io/cluster/<cluster>=owned`, `eks:eks-cluster-name`, and `karpenter.sh/nodepool`. Terminate and delete require the same tags on the resource, so the controller cannot touch other instances. `iam:PassRole` is limited to the Karpenter node role, passed to EC2. Instance-profile actions require cluster tags. KMS (`CreateGrant`, `Decrypt`, `GenerateDataKeyWithoutPlaintext`, `ReEncrypt*`) on the platform key only, through EC2, for encrypted disks. SQS read/delete on its own interruption queue. `eks:DescribeCluster` on its own cluster. `"*"`: `ec2:Describe*` (limited to the region), `pricing:GetProducts`, and `iam:ListInstanceProfiles`, which have no resource-level permissions. `ssm:GetParameter` is limited to public AMI parameters. |

### Cluster add-ons

| Role | Trusted by | Permissions | Why |
|---|---|---|---|
| `aws-load-balancer-controller` | IRSA `kube-system:aws-load-balancer-controller` | Upstream policy for v3.6.0, unchanged (`modules/addons/lbc-policy.json`) | Creates and manages ALBs, target groups, listeners, and their security groups. Deleting security groups, creating load balancers and target groups, and modifying load balancers are conditioned on the `elbv2.k8s.aws/cluster` tag. Kept verbatim so upgrades are a diff against upstream. Accepted breadth: see open finding 2. |
| `cert-manager` | IRSA `cert-manager:cert-manager` | `route53:GetChange` on `change/*`. `ChangeResourceRecordSets` on the environment zone only, where every record must be `TXT` and named `_acme-challenge.*`. `ListResourceRecordSets` on the zone. `ListHostedZonesByName` on `"*"` (not resource-scoped). | DNS-01 challenges. It cannot change any other record, such as the ALB alias. |
| `external-secrets` | IRSA `external-secrets:external-secrets` | `GetSecretValue`, `DescribeSecret`, `ListSecretVersionIds` on `secret:opspilot-<env>/*`. `kms:Decrypt` on the secrets key through Secrets Manager. | Syncs this environment's secrets into Kubernetes. No write and no other environment's prefix. The RDS-managed master secret is outside the prefix and stays unreadable. |

### Application

| Role | Trusted by | Permissions | Why |
|---|---|---|---|
| `app-api` | IRSA `opspilot:opspilot-api` | Read `opspilot-<env>/app` (and decrypt through Secrets Manager). `elasticache:Connect` on the replication group and the app user. | Signs in to Redis with IAM, so no Redis password exists. Reading its own secret lets it pick up rotated values without waiting for External Secrets. Drop this statement if only External Secrets reads the secret. |
| `app-worker` | IRSA `opspilot:opspilot-worker` | As `app-api`, plus `s3:ListBucket` and `GetObject`/`GetObjectVersion` on the ML model bucket, and `kms:Decrypt` through S3. | Loads detector artifacts. Read-only, so it cannot replace a model. |
| `app-backup` | IRSA `opspilot:opspilot-backup` | Read the app secret. `s3:PutObject`/`AbortMultipartUpload` on the backup bucket. `s3:ListBucket`. `kms:GenerateDataKey`/`Encrypt` through S3. | `pg_dump` needs the database URL. It can write but cannot read or delete backups. The bucket is versioned, so an overwrite never destroys an earlier backup, and a compromised job cannot exfiltrate or ransom the archive. |

The Kubernetes-side permissions of the worker (read workloads, patch
deployments in the allowed namespaces) are RBAC in the Helm chart, not IAM.

### CI and services

| Role | Trusted by | Permissions | Why |
|---|---|---|---|
| `ci-deploy` | GitHub OIDC with `aud = sts.amazonaws.com` and `sub` matching `repo:Kunj157/opspilot:<allowed ref>` (default `ref:refs/heads/main`) | Push and pull on this environment's ECR repositories. `ecr:GetAuthorizationToken` on `"*"` (not resource-scoped). | Image publishing from `main` only. No cluster or Terraform rights: deployment is GitOps, where Argo CD pulls the image tag. |
| `vpc-flow-logs` | `vpc-flow-logs.amazonaws.com` | `CreateLogStream`, `PutLogEvents`, `DescribeLogStreams` on the flow-log group | Delivers VPC flow logs. |
| `rds-monitoring` | `monitoring.rds.amazonaws.com` | `AmazonRDSEnhancedMonitoringRole` | RDS Enhanced Monitoring metrics to CloudWatch Logs. |
| Load-test teardown role (created outside this Terraform) | GitHub OIDC `repo:Kunj157/opspilot:environment:loadtest` | Must be limited to resources tagged `environment=loadtest` and the `opspilot/loadtest/*` state key | Used only by the teardown workflow. See the Terraform README. |

## Resource policies

| Resource | Policy | Why |
|---|---|---|
| Terraform state bucket | Denies every principal not in `admin_principal_arns`/`ci_principal_arns`. Denies non-TLS requests. Denies puts that request SSE-S3 or a different KMS key. | State holds endpoints and ARNs. Only Terraform operators read it. |
| CloudTrail bucket | CloudTrail may `GetBucketAcl` and `PutObject` under `AWSLogs/<account>/` (with `aws:SourceArn` of the trail). Denies non-TLS requests. Denies deleting log objects for everyone. | Tamper-evident audit log, together with log file validation. |
| Backup, model, and access-log buckets | Deny non-TLS requests. Access-log delivery from `logging.s3.amazonaws.com` limited to this account. | Access is granted only through the roles above. |
| Karpenter interruption queue | EventBridge and SQS may `SendMessage`. Denies non-TLS requests. | Delivers interruption events. |
| KMS keys (platform, secrets, state, trail) | Account root administers the key, the AWS default that delegates to IAM. CloudWatch Logs or CloudTrail may encrypt with service conditions. The platform key may be used through EC2 by account principals (`kms:ViaService` + `kms:CallerAccount`). | The EC2 statement is needed because the Auto Scaling, EC2 Fleet, and Spot service-linked roles launch instances with encrypted disks and cannot have IAM policies attached. |

## Open findings

1. **Service-role trusts without a confused-deputy guard.** The
   `vpc-flow-logs` and `rds-monitoring` trust policies do not require
   `aws:SourceAccount`. Low risk in a single account. Add the condition
   when those modules next change.
2. **The AWS Load Balancer Controller policy is broad by upstream design.**
   Some statements have no condition: `ec2:AuthorizeSecurityGroupIngress`
   and `RevokeSecurityGroupIngress` on any security group,
   `ec2:CreateSecurityGroup`, listener and rule changes, and
   `RegisterTargets` on any target group. A compromised controller could
   open ingress on any security group in the account. Accepted, because
   upstream needs these for security groups it adopts by reference. The
   mitigations: one account per project, and CloudTrail records every
   call. Re-diff the policy on every chart upgrade.
3. **Application roles can read the whole `app` secret.** Splitting it per
   workload (the API does not need the backup settings) would narrow this
   further once the secret holds more than shared connection settings.
4. **KMS key policies delegate to IAM through account root.** This is the
   AWS default and keeps administration in IAM, but key administration is
   not separated from key use. Revisit it with an AWS Organization and
   dedicated security roles.
