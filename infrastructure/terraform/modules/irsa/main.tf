# One IAM role for Kubernetes service accounts (IRSA): only the listed
# service accounts of this cluster can assume it, and it carries one inline
# least-privilege policy.

locals {
  oidc_issuer = element(split("oidc-provider/", var.oidc_provider_arn), 1)
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_issuer}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_issuer}:sub"
      values   = [for sa in var.service_accounts : "system:serviceaccount:${sa}"]
    }
  }
}

resource "aws_iam_role" "this" {
  name                 = var.name
  assume_role_policy   = data.aws_iam_policy_document.assume.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "this" {
  name   = "least-privilege"
  role   = aws_iam_role.this.id
  policy = var.policy_json
}
