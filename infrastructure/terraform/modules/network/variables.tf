variable "name" {
  description = "Prefix for every resource, e.g. opspilot-development"
  type        = string
}

variable "cidr" {
  description = "VPC CIDR block (a /16)"
  type        = string
}

variable "azs" {
  description = "Availability zones, pinned so the network never grows silently"
  type        = list(string)
  validation {
    condition     = length(var.azs) >= 2 && length(var.azs) <= 3
    error_message = "Use two or three availability zones."
  }
}

variable "single_nat_gateway" {
  description = "One NAT gateway for all zones (cheaper, not zone-redundant)"
  type        = bool
  default     = false
}

variable "flow_log_retention_days" {
  type    = number
  default = 365
}

variable "log_kms_key_arn" {
  description = "KMS key that encrypts the flow log group"
  type        = string
}
