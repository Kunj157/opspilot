# The CRDs come from their own chart so upgrades update them too (Helm never
# upgrades a chart's crds/ directory). Default capacity is described by the
# local chart in ./chart: one EC2NodeClass and one NodePool.

resource "helm_release" "crds" {
  name       = "karpenter-crd"
  namespace  = "kube-system"
  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter-crd"
  version    = var.chart_version
}

resource "helm_release" "karpenter" {
  name       = "karpenter"
  namespace  = "kube-system"
  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter"
  version    = var.chart_version
  skip_crds  = true
  wait       = true

  values = [yamlencode({
    replicas = var.controller_replicas
    serviceAccount = {
      annotations = { "eks.amazonaws.com/role-arn" = module.controller_role.arn }
    }
    settings = {
      clusterName       = local.cluster
      clusterEndpoint   = var.cluster_endpoint
      interruptionQueue = aws_sqs_queue.interruption.name
    }
    controller = {
      resources = {
        requests = { cpu = "250m", memory = "512Mi" }
        limits   = { memory = "512Mi" }
      }
    }
  })]

  depends_on = [helm_release.crds, aws_eks_access_entry.node]
}

resource "helm_release" "capacity" {
  name      = "karpenter-capacity"
  namespace = "kube-system"
  chart     = "${path.module}/chart"

  values = [yamlencode({
    nodeRole          = aws_iam_role.node.name
    clusterName       = local.cluster
    amiAlias          = var.ami_alias
    subnetIds         = var.subnet_ids
    securityGroupIds  = var.security_group_ids
    kmsKeyId          = var.kms_key_arn
    diskGi            = var.node_disk_gb
    architectures     = var.architectures
    capacityTypes     = var.capacity_types
    instanceFamilies  = var.instance_categories
    cpuLimit          = var.cpu_limit
    consolidateAfter  = var.consolidate_after
    expireAfter       = var.expire_after
    disruptionBudgets = [for b in var.disruption_budgets : { for k, v in b : k => v if v != null }]
  })]

  depends_on = [helm_release.karpenter]
}
