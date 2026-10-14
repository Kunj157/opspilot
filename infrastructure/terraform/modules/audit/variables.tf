variable "name" {
  description = "Trail name"
  type        = string
  default     = "opspilot-audit"
}

variable "bucket_name" {
  description = "Globally unique name of the trail bucket"
  type        = string
}

variable "retention_days" {
  description = "How long log files are kept"
  type        = number
  default     = 365
}

variable "data_event_bucket_arns" {
  description = "Buckets whose object reads and writes are recorded (e.g. Terraform state)"
  type        = list(string)
  default     = []
}

variable "enable_guardduty" {
  description = "Turn on GuardDuty (S3 and EKS audit-log protection) in this region"
  type        = bool
  default     = false
}
