variable "name" {
  type = string
}

variable "kubernetes_version" {
  type    = string
  default = "1.34"
}

variable "vpc_id" {
  type = string
}

variable "vpc_cidr" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "public_endpoint_cidrs" {
  description = "CIDRs allowed to reach the public API endpoint; empty for a private-only endpoint"
  type        = list(string)
  default     = []
  validation {
    condition     = !contains(var.public_endpoint_cidrs, "0.0.0.0/0")
    error_message = "The API endpoint must not be open to the whole internet."
  }
}

variable "kms_key_arn" {
  description = "Key for Kubernetes secrets, node disks, and control-plane logs"
  type        = string
}

variable "log_retention_days" {
  type    = number
  default = 365
}

variable "node_disk_gb" {
  type    = number
  default = 40
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
