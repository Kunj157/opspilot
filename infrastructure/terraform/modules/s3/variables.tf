variable "name" {
  description = "Globally unique bucket name"
  type        = string
}

variable "noncurrent_days" {
  description = "How long to keep noncurrent object versions"
  type        = number
}

variable "kms_key_arn" {
  type = string
}

variable "access_log_bucket" {
  description = "Bucket that receives server access logs"
  type        = string
}

variable "force_destroy" {
  description = "Allow destroying a non-empty bucket (temporary environments only)"
  type        = bool
  default     = false
}
