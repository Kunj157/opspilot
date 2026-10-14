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
    key          = "opspilot/production/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { project = "opspilot", environment = "production", managed-by = "terraform" }
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
  environment                 = "production"
  vpc_cidr                    = "10.30.0.0/16"
  azs                         = ["${var.region}a", "${var.region}b", "${var.region}c"]
  single_nat_gateway          = false
  eks_public_endpoint_cidrs   = var.eks_public_endpoint_cidrs
  node_groups                 = { default = { instance_types = ["m7g.large"], capacity_type = "ON_DEMAND", min = 3, max = 6, desired = 3 } }
  db_instance_class           = "db.m7g.large"
  db_multi_az                 = true
  db_backup_retention_days    = 30
  redis_replicas              = 1
  deletion_protection         = true
  domain                      = var.domain
  alert_emails                = var.alert_emails
  log_retention_days          = 365
  create_github_oidc_provider = false
  monthly_budget_usd          = 1500
  office_hours                = null
}

output "environment" {
  value = module.environment
}
