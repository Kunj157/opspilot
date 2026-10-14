variable "prefix" {
  description = "Bucket name prefix, e.g. opspilot-development-<account>"
  type        = string
}

variable "buckets" {
  description = "Bucket suffix → how long to keep noncurrent versions"
  type        = map(object({ noncurrent_days = number }))
}

variable "kms_key_arn" {
  type = string
}

variable "force_destroy" {
  description = "Allow destroying non-empty buckets (temporary environments only)"
  type        = bool
  default     = false
}

variable "access_log_bucket" {
  description = "Bucket that receives server access logs"
  type        = string
}
