# One OpsPilot environment: network, cluster, data stores, registry, storage,
# secrets, DNS, alerting, CI access, and cost controls.

data "aws_caller_identity" "current" {}

locals {
  name = "opspilot-${var.environment}"
}

resource "aws_kms_key" "platform" {
  description             = "${local.name} platform data"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.kms.json
}

resource "aws_kms_alias" "platform" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.platform.key_id
}

data "aws_region" "current" {}

data "aws_iam_policy_document" "kms" {
  #checkov:skip=CKV_AWS_356: in a key policy "*" means this key only
  #checkov:skip=CKV_AWS_109: account administrators manage the key, as in the AWS default key policy
  #checkov:skip=CKV_AWS_111: account administrators manage the key, as in the AWS default key policy
  statement {
    sid       = "AccountAdministration"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
  statement {
    sid       = "CloudWatchLogs"
    actions   = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["logs.${data.aws_region.current.region}.amazonaws.com"]
    }
  }
  # Encrypted node disks: EC2 (and the Auto Scaling / Spot service-linked roles
  # acting for the node group and Karpenter) may use the key only through EC2
  # in this account.
  statement {
    sid       = "NodeVolumesThroughEc2"
    actions   = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:CreateGrant", "kms:DescribeKey"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
    condition {
      test     = "StringEquals"
      variable = "kms:CallerAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ec2.${data.aws_region.current.region}.amazonaws.com"]
    }
  }
}

module "network" {
  source                  = "../network"
  name                    = local.name
  cidr                    = var.vpc_cidr
  azs                     = var.azs
  single_nat_gateway      = var.single_nat_gateway
  log_kms_key_arn         = aws_kms_key.platform.arn
  flow_log_retention_days = var.log_retention_days
}

module "eks" {
  source                = "../eks"
  name                  = local.name
  kubernetes_version    = var.kubernetes_version
  vpc_id                = module.network.vpc_id
  vpc_cidr              = module.network.vpc_cidr
  private_subnet_ids    = module.network.private_subnet_ids
  public_endpoint_cidrs = var.eks_public_endpoint_cidrs
  kms_key_arn           = aws_kms_key.platform.arn
  log_retention_days    = var.log_retention_days
  node_groups           = var.node_groups
}

module "karpenter" {
  source              = "../karpenter"
  name                = local.name
  cluster_name        = module.eks.cluster_name
  cluster_endpoint    = module.eks.cluster_endpoint
  oidc_provider_arn   = module.eks.oidc_provider_arn
  subnet_ids          = module.network.private_subnet_ids
  security_group_ids  = [module.eks.cluster_security_group_id]
  kms_key_arn         = aws_kms_key.platform.arn
  controller_replicas = var.karpenter.controller_replicas
  capacity_types      = var.karpenter.capacity_types
  cpu_limit           = var.karpenter.cpu_limit
}

module "rds" {
  source                   = "../rds"
  name                     = local.name
  vpc_id                   = module.network.vpc_id
  database_subnet_ids      = module.network.database_subnet_ids
  client_security_group_id = module.eks.cluster_security_group_id
  kms_key_arn              = aws_kms_key.platform.arn
  instance_class           = var.db_instance_class
  multi_az                 = var.db_multi_az
  backup_retention_days    = var.db_backup_retention_days
  deletion_protection      = var.deletion_protection
}

module "redis" {
  source                   = "../redis"
  name                     = local.name
  vpc_id                   = module.network.vpc_id
  subnet_ids               = module.network.database_subnet_ids
  client_security_group_id = module.eks.cluster_security_group_id
  kms_key_arn              = aws_kms_key.platform.arn
  node_type                = var.redis_node_type
  replicas                 = var.redis_replicas
}

module "ecr" {
  source       = "../ecr"
  prefix       = local.name
  repositories = ["api", "web", "worker", "demo-shop"]
  kms_key_arn  = aws_kms_key.platform.arn
}

module "backups" {
  source            = "../s3"
  name              = "${local.name}-${data.aws_caller_identity.current.account_id}-backups"
  noncurrent_days   = 35
  kms_key_arn       = aws_kms_key.platform.arn
  access_log_bucket = aws_s3_bucket.access_logs.id
  force_destroy     = !var.deletion_protection
}

module "ml_models" {
  source            = "../s3"
  name              = "${local.name}-${data.aws_caller_identity.current.account_id}-ml-models"
  noncurrent_days   = 365
  kms_key_arn       = aws_kms_key.platform.arn
  access_log_bucket = aws_s3_bucket.access_logs.id
  force_destroy     = !var.deletion_protection
}

module "secrets" {
  source  = "../secrets"
  name    = local.name
  secrets = ["app", "oidc-client-secret", "llm-api-key", "session-secret"]
}

module "dns" {
  source = "../dns"
  domain = var.domain
}

module "observability" {
  source             = "../observability"
  name               = local.name
  kms_key_arn        = aws_kms_key.platform.arn
  alert_emails       = var.alert_emails
  log_retention_days = var.log_retention_days
  rds_instance_id    = local.name
}

module "addons" {
  source              = "../addons"
  name                = local.name
  cluster_name        = module.eks.cluster_name
  oidc_provider_arn   = module.eks.oidc_provider_arn
  vpc_id              = module.network.vpc_id
  domain              = var.domain
  zone_id             = module.dns.zone_id
  acme_email          = var.alert_emails[0]
  secrets_kms_key_arn = module.secrets.kms_key_arn
  replicas            = var.karpenter.controller_replicas
}

module "iam" {
  source                      = "../iam"
  name                        = local.name
  github_repository           = var.github_repository
  allowed_refs                = var.ci_allowed_refs
  ecr_repository_arns         = module.ecr.repository_arns
  create_github_oidc_provider = var.create_github_oidc_provider
}
