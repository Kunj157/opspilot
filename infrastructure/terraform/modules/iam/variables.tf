variable "name" {
  type = string
}

variable "github_repository" {
  description = "owner/name of the application repository"
  type        = string
}

variable "allowed_refs" {
  description = "Git refs allowed to assume the deploy role, e.g. ref:refs/heads/main"
  type        = list(string)
  default     = ["ref:refs/heads/main"]
}

variable "ecr_repository_arns" {
  type = list(string)
}

variable "create_github_oidc_provider" {
  description = "Create the account-wide GitHub OIDC provider (only in one environment)"
  type        = bool
  default     = false
}
