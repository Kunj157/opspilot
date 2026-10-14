# Cluster add-ons, each with its own IRSA role:
# - AWS Load Balancer Controller: one internet-facing ALB per Ingress group,
#   TLS with the environment's ACM certificate (see docs/adr/005).
# - cert-manager: Let's Encrypt certificates for in-cluster TLS, solved with
#   Route53 DNS-01 in this environment's zone only.
# - External Secrets Operator: syncs this environment's Secrets Manager
#   entries into Kubernetes Secrets.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account = data.aws_caller_identity.current.account_id
  region  = data.aws_region.current.region
}

module "load_balancer_controller_role" {
  source            = "../irsa"
  name              = "${var.name}-aws-load-balancer-controller"
  oidc_provider_arn = var.oidc_provider_arn
  service_accounts  = ["kube-system:aws-load-balancer-controller"]
  # Upstream policy for this controller version, unchanged.
  policy_json = file("${path.module}/lbc-policy.json")
}

data "aws_iam_policy_document" "cert_manager" {
  statement {
    sid       = "ReadChangeStatus"
    actions   = ["route53:GetChange"]
    resources = ["arn:aws:route53:::change/*"]
  }
  # Only TXT records under _acme-challenge in this environment's zone.
  statement {
    sid       = "WriteChallengeRecords"
    actions   = ["route53:ChangeResourceRecordSets"]
    resources = ["arn:aws:route53:::hostedzone/${var.zone_id}"]
    condition {
      test     = "ForAllValues:StringEquals"
      variable = "route53:ChangeResourceRecordSetsRecordTypes"
      values   = ["TXT"]
    }
    condition {
      test     = "ForAllValues:StringLike"
      variable = "route53:ChangeResourceRecordSetsNormalizedRecordNames"
      values   = ["_acme-challenge.*"]
    }
  }
  statement {
    sid       = "ListZoneRecords"
    actions   = ["route53:ListResourceRecordSets"]
    resources = ["arn:aws:route53:::hostedzone/${var.zone_id}"]
  }
  statement {
    sid       = "FindZone"
    actions   = ["route53:ListHostedZonesByName"]
    resources = ["*"] # no resource-level permissions for this action
  }
}

module "cert_manager_role" {
  source            = "../irsa"
  name              = "${var.name}-cert-manager"
  oidc_provider_arn = var.oidc_provider_arn
  service_accounts  = ["cert-manager:cert-manager"]
  policy_json       = data.aws_iam_policy_document.cert_manager.json
}

data "aws_iam_policy_document" "external_secrets" {
  statement {
    sid = "ReadEnvironmentSecrets"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
      "secretsmanager:ListSecretVersionIds",
    ]
    resources = ["arn:aws:secretsmanager:${local.region}:${local.account}:secret:${var.name}/*"]
  }
  statement {
    sid       = "DecryptThroughSecretsManager"
    actions   = ["kms:Decrypt"]
    resources = [var.secrets_kms_key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["secretsmanager.${local.region}.amazonaws.com"]
    }
  }
}

module "external_secrets_role" {
  source            = "../irsa"
  name              = "${var.name}-external-secrets"
  oidc_provider_arn = var.oidc_provider_arn
  service_accounts  = ["external-secrets:external-secrets"]
  policy_json       = data.aws_iam_policy_document.external_secrets.json
}
