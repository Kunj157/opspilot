terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
  # Partial configuration: `terraform init -backend-config=../backend.hcl`
  # supplies the bucket created by ../../bootstrap.
  backend "s3" {
    key          = "opspilot/staging/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { project = "opspilot", environment = "staging", managed-by = "terraform" }
  }
}

variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "domain" {
  type = string
}

variable "alert_emails" {
  type = list(string)
}

variable "eks_public_endpoint_cidrs" {
  description = "Office or VPN CIDRs allowed to reach the cluster API"
  type        = list(string)
  default     = []
}

module "environment" {
  source                      = "../../modules/environment"
  environment                 = "staging"
  vpc_cidr                    = "10.20.0.0/16"
  azs                         = ["${var.region}a", "${var.region}b", "${var.region}c"]
  single_nat_gateway          = true
  eks_public_endpoint_cidrs   = var.eks_public_endpoint_cidrs
  node_groups                 = { default = { instance_types = ["t4g.large"], capacity_type = "SPOT", min = 2, max = 4, desired = 2 } }
  db_instance_class           = "db.t4g.small"
  db_multi_az                 = false
  db_backup_retention_days    = 7
  redis_replicas              = 0
  deletion_protection         = false
  domain                      = var.domain
  alert_emails                = var.alert_emails
  log_retention_days          = 90
  create_github_oidc_provider = false
  monthly_budget_usd          = 400
  office_hours = {
    time_zone  = "Europe/Berlin"
    start_cron = "0 7 * * MON-FRI"
    stop_cron  = "0 20 * * MON-FRI"
    min        = 2
    max        = 4
  }
}

output "environment" {
  value = module.environment
}
