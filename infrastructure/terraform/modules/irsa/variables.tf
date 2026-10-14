variable "name" {
  description = "Role name"
  type        = string
}

variable "oidc_provider_arn" {
  description = "The cluster's IAM OIDC provider"
  type        = string
}

variable "service_accounts" {
  description = "Service accounts allowed to assume the role, as namespace:name"
  type        = list(string)
  validation {
    condition     = length(var.service_accounts) > 0 && alltrue([for sa in var.service_accounts : can(regex("^[a-z0-9-]+:[a-z0-9-]+$", sa))])
    error_message = "List at least one service account as namespace:name, without wildcards."
  }
}

variable "policy_json" {
  description = "Inline policy document"
  type        = string
}
