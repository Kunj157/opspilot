variable "name" {
  description = "Prefix, e.g. opspilot-development (also the Secrets Manager prefix)"
  type        = string
}

variable "cluster_name" {
  type = string
}

variable "oidc_provider_arn" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "domain" {
  description = "Environment domain; cert-manager solves challenges only in its zone"
  type        = string
}

variable "zone_id" {
  type = string
}

variable "acme_email" {
  description = "Let's Encrypt account contact (expiry notices)"
  type        = string
}

variable "secrets_kms_key_arn" {
  description = "Key that encrypts the environment's Secrets Manager entries"
  type        = string
}

variable "replicas" {
  description = "Controller replicas for the load balancer controller"
  type        = number
  default     = 2
}

variable "secret_store_name" {
  type    = string
  default = "aws-secrets-manager"
}

variable "cluster_issuer_name" {
  type    = string
  default = "letsencrypt"
}

variable "chart_versions" {
  type = object({
    aws_load_balancer_controller = string
    cert_manager                 = string
    external_secrets             = string
  })
  default = {
    aws_load_balancer_controller = "3.6.0"
    cert_manager                 = "v1.21.2"
    external_secrets             = "2.12.0"
  }
}
