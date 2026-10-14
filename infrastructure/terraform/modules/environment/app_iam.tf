# Application roles (IRSA) for the OpsPilot chart's service accounts. Each
# role gets only what its workload uses:
#   api     app secret, Redis IAM sign-in
#   worker  app secret, Redis IAM sign-in, read model artifacts
#   backup  app secret (database credentials), write backups (no delete)

locals {
  app_secret_arn = module.secrets.secret_arns["app"]
  app_sa         = "${var.app_namespace}:opspilot"
  via_s3         = "s3.${data.aws_region.current.region}.amazonaws.com"
}

data "aws_iam_policy_document" "read_app_secret" {
  statement {
    sid       = "ReadAppSecret"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [local.app_secret_arn]
  }
  statement {
    sid       = "DecryptAppSecret"
    actions   = ["kms:Decrypt"]
    resources = [module.secrets.kms_key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["secretsmanager.${data.aws_region.current.region}.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "redis_connect" {
  statement {
    sid       = "RedisIamAuth"
    actions   = ["elasticache:Connect"]
    resources = [module.redis.replication_group_arn, module.redis.app_user_arn]
  }
}

data "aws_iam_policy_document" "read_models" {
  statement {
    sid       = "ListModels"
    actions   = ["s3:ListBucket"]
    resources = [module.ml_models.arn]
  }
  statement {
    sid       = "ReadModels"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${module.ml_models.arn}/*"]
  }
  statement {
    sid       = "DecryptModels"
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.platform.arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = [local.via_s3]
    }
  }
}

data "aws_iam_policy_document" "write_backups" {
  statement {
    sid       = "WriteBackups"
    actions   = ["s3:PutObject", "s3:AbortMultipartUpload"]
    resources = ["${module.backups.arn}/*"]
  }
  statement {
    sid       = "ListBackups"
    actions   = ["s3:ListBucket"]
    resources = [module.backups.arn]
  }
  statement {
    sid       = "EncryptBackups"
    actions   = ["kms:GenerateDataKey", "kms:Encrypt"]
    resources = [aws_kms_key.platform.arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = [local.via_s3]
    }
  }
}

data "aws_iam_policy_document" "api" {
  source_policy_documents = [
    data.aws_iam_policy_document.read_app_secret.json,
    data.aws_iam_policy_document.redis_connect.json,
  ]
}

data "aws_iam_policy_document" "worker" {
  source_policy_documents = [
    data.aws_iam_policy_document.read_app_secret.json,
    data.aws_iam_policy_document.redis_connect.json,
    data.aws_iam_policy_document.read_models.json,
  ]
}

data "aws_iam_policy_document" "backup" {
  source_policy_documents = [
    data.aws_iam_policy_document.read_app_secret.json,
    data.aws_iam_policy_document.write_backups.json,
  ]
}

module "app_roles" {
  source = "../irsa"
  for_each = {
    api    = data.aws_iam_policy_document.api.json
    worker = data.aws_iam_policy_document.worker.json
    backup = data.aws_iam_policy_document.backup.json
  }
  name              = "${local.name}-app-${each.key}"
  oidc_provider_arn = module.eks.oidc_provider_arn
  service_accounts  = ["${local.app_sa}-${each.key}"]
  policy_json       = each.value
}
