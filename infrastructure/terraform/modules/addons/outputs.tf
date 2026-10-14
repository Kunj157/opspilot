output "load_balancer_controller_role_arn" {
  value = module.load_balancer_controller_role.arn
}

output "cert_manager_role_arn" {
  value = module.cert_manager_role.arn
}

output "external_secrets_role_arn" {
  value = module.external_secrets_role.arn
}

output "cluster_issuer" {
  value = var.cluster_issuer_name
}

output "secret_store" {
  value = var.secret_store_name
}
