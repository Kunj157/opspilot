output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "cluster_certificate_authority" {
  value = module.eks.cluster_certificate_authority
}

output "karpenter_controller_role_arn" {
  value = module.karpenter.controller_role_arn
}

output "addon_role_arns" {
  value = {
    aws_load_balancer_controller = module.addons.load_balancer_controller_role_arn
    cert_manager                 = module.addons.cert_manager_role_arn
    external_secrets             = module.addons.external_secrets_role_arn
  }
}

output "cluster_issuer" {
  value = module.addons.cluster_issuer
}

output "secret_store" {
  value = module.addons.secret_store
}

output "database_endpoint" {
  value = module.rds.endpoint
}

output "database_secret_arn" {
  value = module.rds.master_secret_arn
}

output "redis_endpoint" {
  value = module.redis.primary_endpoint
}

output "ecr_repositories" {
  value = module.ecr.repository_urls
}

output "ci_role_arn" {
  value = module.iam.ci_role_arn
}

output "name_servers" {
  value = module.dns.name_servers
}

output "certificate_arn" {
  value = module.dns.certificate_arn
}

# Annotate the chart's service accounts with these (eks.amazonaws.com/role-arn).
output "app_role_arns" {
  value = { for name, role in module.app_roles : name => role.arn }
}

output "app_secret_name" {
  value = "${local.name}/app"
}

output "redis_app_user" {
  value = module.redis.app_user_name
}

output "buckets" {
  value = { backups = module.backups.name, ml_models = module.ml_models.name }
}
