# Karpenter: just-in-time nodes for application workloads. The managed node
# group stays small and runs the system add-ons (Karpenter included); every
# other pod lands on nodes Karpenter launches, right-sizes, and consolidates.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

locals {
  account   = data.aws_caller_identity.current.account_id
  region    = data.aws_region.current.region
  partition = data.aws_partition.current.partition
  cluster   = var.cluster_name
}

# Node role: what Karpenter's instances run as. Karpenter creates the
# instance profile for it from the EC2NodeClass.
data "aws_iam_policy_document" "node_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "node" {
  name               = "${var.name}-karpenter-node"
  assume_role_policy = data.aws_iam_policy_document.node_assume.json
}

resource "aws_iam_role_policy_attachment" "node" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPullOnly",
    "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
  ])
  role       = aws_iam_role.node.name
  policy_arn = each.value
}

# Lets the nodes join: the cluster uses access entries, not the aws-auth map.
resource "aws_eks_access_entry" "node" {
  cluster_name  = local.cluster
  principal_arn = aws_iam_role.node.arn
  type          = "EC2_LINUX"
}

# Spot interruptions, rebalance hints, health events, and state changes reach
# Karpenter through this queue, so it drains nodes before AWS reclaims them.
resource "aws_sqs_queue" "interruption" {
  name                      = "${var.name}-karpenter"
  message_retention_seconds = 300
  sqs_managed_sse_enabled   = true
}

data "aws_iam_policy_document" "queue" {
  statement {
    sid       = "EventBridge"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.interruption.arn]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com", "sqs.amazonaws.com"]
    }
  }
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["sqs:*"]
    resources = [aws_sqs_queue.interruption.arn]
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

resource "aws_sqs_queue_policy" "interruption" {
  queue_url = aws_sqs_queue.interruption.url
  policy    = data.aws_iam_policy_document.queue.json
}

locals {
  interruption_events = {
    health    = { source = ["aws.health"], detail-type = ["AWS Health Event"] }
    spot      = { source = ["aws.ec2"], detail-type = ["EC2 Spot Instance Interruption Warning"] }
    rebalance = { source = ["aws.ec2"], detail-type = ["EC2 Instance Rebalance Recommendation"] }
    state     = { source = ["aws.ec2"], detail-type = ["EC2 Instance State-change Notification"] }
  }
}

resource "aws_cloudwatch_event_rule" "interruption" {
  for_each      = local.interruption_events
  name          = "${var.name}-karpenter-${each.key}"
  event_pattern = jsonencode(each.value)
}

resource "aws_cloudwatch_event_target" "interruption" {
  for_each = local.interruption_events
  rule     = aws_cloudwatch_event_rule.interruption[each.key].name
  arn      = aws_sqs_queue.interruption.arn
}

# Controller role (IRSA): scoped to resources tagged for this cluster, as in
# the upstream reference policy for this Karpenter version.
module "controller_role" {
  source            = "../irsa"
  name              = "${var.name}-karpenter-controller"
  oidc_provider_arn = var.oidc_provider_arn
  service_accounts  = ["kube-system:karpenter"]
  policy_json = templatefile("${path.module}/controller-policy.json.tftpl", {
    partition      = local.partition
    region         = local.region
    account        = local.account
    cluster        = local.cluster
    node_role_arn  = aws_iam_role.node.arn
    queue_arn      = aws_sqs_queue.interruption.arn
    ebs_kms_key_id = var.kms_key_arn
  })
}
