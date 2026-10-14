variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "client_security_group_id" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "replicas" {
  type    = number
  default = 0
}

variable "snapshot_retention_days" {
  type    = number
  default = 1
}
