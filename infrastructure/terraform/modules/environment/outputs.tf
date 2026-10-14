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
