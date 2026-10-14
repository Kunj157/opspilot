resource "helm_release" "load_balancer_controller" {
  name       = "aws-load-balancer-controller"
  namespace  = "kube-system"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  version    = var.chart_versions.aws_load_balancer_controller
  wait       = true

  values = [yamlencode({
    clusterName  = var.cluster_name
    region       = local.region
    vpcId        = var.vpc_id
    replicaCount = var.replicas
    serviceAccount = {
      name        = "aws-load-balancer-controller"
      annotations = { "eks.amazonaws.com/role-arn" = module.load_balancer_controller_role.arn }
    }
  })]
}

resource "helm_release" "cert_manager" {
  name             = "cert-manager"
  namespace        = "cert-manager"
  create_namespace = true
  repository       = "https://charts.jetstack.io"
  chart            = "cert-manager"
  version          = var.chart_versions.cert_manager
  wait             = true

  values = [yamlencode({
    crds = { enabled = true }
    serviceAccount = {
      name        = "cert-manager"
      annotations = { "eks.amazonaws.com/role-arn" = module.cert_manager_role.arn }
    }
  })]

  # The controller mutates new Services; it must be up before charts create them.
  depends_on = [helm_release.load_balancer_controller]
}

resource "helm_release" "external_secrets" {
  name             = "external-secrets"
  namespace        = "external-secrets"
  create_namespace = true
  repository       = "https://charts.external-secrets.io"
  chart            = "external-secrets"
  version          = var.chart_versions.external_secrets
  wait             = true

  values = [yamlencode({
    installCRDs = true
    serviceAccount = {
      name        = "external-secrets"
      annotations = { "eks.amazonaws.com/role-arn" = module.external_secrets_role.arn }
    }
  })]

  depends_on = [helm_release.load_balancer_controller]
}

# ClusterIssuers and the ClusterSecretStore, from the local chart in ./chart.
resource "helm_release" "cluster_config" {
  name      = "cluster-config"
  namespace = "kube-system"
  chart     = "${path.module}/chart"

  values = [yamlencode({
    region     = local.region
    acmeEmail  = var.acme_email
    domain     = var.domain
    zoneId     = var.zone_id
    storeName  = var.secret_store_name
    issuerName = var.cluster_issuer_name
  })]

  depends_on = [helm_release.cert_manager, helm_release.external_secrets]
}
