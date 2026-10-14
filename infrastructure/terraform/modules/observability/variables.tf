variable "name" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "alert_emails" {
  type    = list(string)
  default = []
}

variable "log_retention_days" {
  type    = number
  default = 365
}

variable "rds_instance_id" {
  type    = string
  default = null
}
