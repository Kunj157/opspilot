# One-time bootstrap: the encrypted, versioned bucket that holds every
# environment's Terraform state. Applied once per AWS account with local state;
# environments then use it as their S3 backend (with S3-native locking).

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { project = "opspilot", managed-by = "terraform", component = "state" }
  }
}

variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "state_bucket" {
  description = "Globally unique name of the state bucket"
  type        = string
}

variable "admin_principal_arns" {
  description = "IAM role/user ARNs (wildcards allowed, e.g. an SSO role path) that administer Terraform state"
  type        = list(string)
  validation {
    condition     = length(var.admin_principal_arns) > 0 && !contains(var.admin_principal_arns, "*")
    error_message = "Name at least one administrator principal, and not \"*\": everyone else is denied."
  }
}

variable "ci_principal_arns" {
  description = "CI role ARNs that run terraform plan/apply (e.g. the GitHub OIDC role)"
  type        = list(string)
  default     = []
}

variable "audit_bucket" {
  description = "Globally unique name of the CloudTrail bucket"
  type        = string
}

variable "enable_guardduty" {
  type    = bool
  default = false
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "kms" {
  #checkov:skip=CKV_AWS_356: in a key policy "*" means this key only (the AWS default key policy)
  #checkov:skip=CKV_AWS_109: account administrators manage the key, as in the AWS default key policy
  #checkov:skip=CKV_AWS_111: account administrators manage the key, as in the AWS default key policy
  statement {
    sid       = "AccountAdministration"
    actions   = ["kms:*"]
    resources = ["*"] # a key policy always refers to its own key
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
}

resource "aws_kms_key" "state" {
  description             = "OpsPilot Terraform state"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.kms.json
}

resource "aws_s3_bucket" "state" {
  #checkov:skip=CKV_AWS_18: the bootstrap bucket is written only by Terraform; the audit trail records its object-level access
  #checkov:skip=CKV_AWS_144: state is versioned; cross-region replication is not worth its cost for this project
  #checkov:skip=CKV2_AWS_62: nothing consumes state bucket events
  bucket = var.state_bucket
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.state.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "state" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

locals {
  state_principals = concat(var.admin_principal_arns, var.ci_principal_arns)
  state_resources  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
}

data "aws_iam_policy_document" "state_access" {
  source_policy_documents = [data.aws_iam_policy_document.state.json]

  # Only the named principals may touch state at all (this also covers the
  # AWS services: none of them needs this bucket).
  statement {
    sid       = "DenyUnlistedPrincipals"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = local.state_resources
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "StringNotLike"
      variable = "aws:PrincipalArn"
      values   = local.state_principals
    }
  }

  # Objects are encrypted with the state key: a put may omit the header (the
  # bucket default applies) but may not ask for SSE-S3 or another key.
  statement {
    sid       = "DenyUnencryptedPuts"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.state.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "StringNotEqualsIfExists"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms"]
    }
  }
  statement {
    sid       = "DenyOtherKeys"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.state.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "StringNotEqualsIfExists"
      variable = "s3:x-amz-server-side-encryption-aws-kms-key-id"
      values   = [aws_kms_key.state.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state_access.json
}

module "audit" {
  source                 = "../modules/audit"
  bucket_name            = var.audit_bucket
  data_event_bucket_arns = [aws_s3_bucket.state.arn]
  enable_guardduty       = var.enable_guardduty
}

output "state_bucket" {
  value = aws_s3_bucket.state.id
}

output "state_kms_key_arn" {
  value = aws_kms_key.state.arn
}

output "audit_trail_arn" {
  value = module.audit.trail_arn
}

output "audit_bucket" {
  value = module.audit.bucket
}
