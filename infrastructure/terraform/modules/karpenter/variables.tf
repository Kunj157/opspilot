variable "name" {
  description = "Prefix, e.g. opspilot-development"
  type        = string
}

variable "cluster_name" {
  type = string
}

variable "cluster_endpoint" {
  type = string
}

variable "oidc_provider_arn" {
  type = string
}

variable "subnet_ids" {
  description = "Private subnets for Karpenter nodes"
  type        = list(string)
}

variable "security_group_ids" {
  description = "Node security groups (the cluster security group, which the databases trust)"
  type        = list(string)
}

variable "kms_key_arn" {
  description = "Key for node disks"
  type        = string
}

variable "chart_version" {
  description = "Karpenter and karpenter-crd chart version"
  type        = string
  default     = "1.15.0"
}

variable "controller_replicas" {
  type    = number
  default = 2
}

variable "ami_alias" {
  description = "EKS-optimised AMI family and version, e.g. al2023@v20260901; @latest follows new releases"
  type        = string
  default     = "al2023@latest"
}

variable "node_disk_gb" {
  type    = number
  default = 40
}

variable "architectures" {
  description = "CPU architectures the application images are built for"
  type        = list(string)
  default     = ["amd64"]
}

variable "capacity_types" {
  description = "spot and/or on-demand; Karpenter prefers spot when both are allowed"
  type        = list(string)
  default     = ["on-demand"]
  validation {
    condition     = length(var.capacity_types) > 0 && alltrue([for t in var.capacity_types : contains(["spot", "on-demand"], t)])
    error_message = "Use spot and/or on-demand."
  }
}

variable "instance_categories" {
  type    = list(string)
  default = ["c", "m", "r", "t"]
}

variable "cpu_limit" {
  description = "Total vCPUs Karpenter may run in this pool"
  type        = number
  default     = 16
}

variable "consolidate_after" {
  description = "How long a node must be empty or underused before Karpenter removes or replaces it"
  type        = string
  default     = "1m"
}

variable "expire_after" {
  type    = string
  default = "720h"
}

variable "disruption_budgets" {
  description = "Karpenter disruption budgets (at most this many nodes disrupted at once, optionally on a schedule)"
  type = list(object({
    nodes    = string
    schedule = optional(string)
    duration = optional(string)
  }))
  default = [{ nodes = "10%" }]
}
