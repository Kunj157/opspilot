variable "name" {
  description = "Prefix, e.g. opspilot-development"
  type        = string
}

variable "secrets" {
  description = "Secret names, e.g. oidc-client-secret, llm-api-key"
  type        = list(string)
}

variable "recovery_window_in_days" {
  type    = number
  default = 30
}
