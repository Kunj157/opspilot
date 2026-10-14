variable "prefix" {
  type    = string
  default = "opspilot"
}

variable "repositories" {
  description = "Image names, e.g. api, web, worker, demo-shop"
  type        = list(string)
}

variable "keep_images" {
  type    = number
  default = 50
}

variable "kms_key_arn" {
  type = string
}

variable "force_delete" {
  description = "Delete repositories that still hold images (temporary environments only)"
  type        = bool
  default     = false
}
