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
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.0"
    }
  }
  # Partial configuration: `terraform init -backend-config=../backend.hcl`
  # supplies the bucket created by ../../bootstrap.
  backend "s3" {
    key          = "opspilot/development/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { project = "opspilot", environment = "development", managed-by = "terraform" }
  }
}

# Cluster add-ons are Helm releases; the token comes from the caller's AWS
# credentials, so nothing long-lived is stored.
provider "helm" {
  kubernetes = {
    host                   = module.environment.cluster_endpoint
    cluster_ca_certificate = base64decode(module.environment.cluster_certificate_authority)
    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.environment.cluster_name, "--region", var.region]
    }
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
  environment                 = "development"
  vpc_cidr                    = "10.10.0.0/16"
  azs                         = ["${var.region}a", "${var.region}b", "${var.region}c"]
  single_nat_gateway          = true
  eks_public_endpoint_cidrs   = var.eks_public_endpoint_cidrs
  node_groups                 = { system = { instance_types = ["t4g.medium"], capacity_type = "ON_DEMAND", min = 1, max = 2, desired = 1 } }
  karpenter                   = { capacity_types = ["spot", "on-demand"], cpu_limit = 8, controller_replicas = 1 }
  db_instance_class           = "db.t4g.micro"
  db_multi_az                 = false
  db_backup_retention_days    = 3
  redis_replicas              = 0
  deletion_protection         = false
  domain                      = var.domain
  alert_emails                = var.alert_emails
  log_retention_days          = 30
  create_github_oidc_provider = true
  monthly_budget_usd          = 250
  office_hours                = null
}

output "environment" {
  value = module.environment
}
