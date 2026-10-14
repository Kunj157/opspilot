variable "environment" {
  type = string
  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Use development, staging, or production."
  }
}

variable "vpc_cidr" {
  type = string
}

variable "azs" {
  type = list(string)
}

variable "single_nat_gateway" {
  type    = bool
  default = true
}

variable "kubernetes_version" {
  type    = string
  default = "1.34"
}

variable "eks_public_endpoint_cidrs" {
  type    = list(string)
  default = []
}

variable "node_groups" {
  type = map(object({
    instance_types = list(string)
    capacity_type  = string
    min            = number
    max            = number
    desired        = number
  }))
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "db_backup_retention_days" {
  type    = number
  default = 7
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "redis_replicas" {
  type    = number
  default = 0
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "domain" {
  type = string
}

variable "alert_emails" {
  type = list(string)
}

variable "log_retention_days" {
  type    = number
  default = 365
}

variable "github_repository" {
  type    = string
  default = "Kunj157/opspilot"
}

variable "ci_allowed_refs" {
  type    = list(string)
  default = ["ref:refs/heads/main"]
}

variable "create_github_oidc_provider" {
  type    = bool
  default = false
}

variable "monthly_budget_usd" {
  type = number
}

variable "office_hours" {
  description = "Scale the nodes to zero outside these hours (null keeps them running)"
  type = object({
    time_zone  = string
    start_cron = string
    stop_cron  = string
    min        = number
    max        = number
  })
  default = null
}
