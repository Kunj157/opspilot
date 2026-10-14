# Redis for caching and rate limits: encrypted at rest and in transit, with
# IAM authentication (no password exists, so none can leak through state),
# reachable only from the cluster.

resource "aws_elasticache_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "this" {
  name        = "${var.name}-redis"
  description = "Redis, reachable only from the EKS cluster"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "from_cluster" {
  security_group_id            = aws_security_group.this.id
  description                  = "Redis from EKS"
  referenced_security_group_id = var.client_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
}

# The built-in default user is switched off; the application signs in with IAM.
resource "aws_elasticache_user" "default" {
  user_id       = "${var.name}-default"
  user_name     = "default"
  engine        = "redis"
  access_string = "off ~* -@all"
  authentication_mode {
    type = "no-password-required"
  }
}

resource "aws_elasticache_user" "app" {
  user_id       = "${var.name}-app"
  user_name     = "${var.name}-app"
  engine        = "redis"
  access_string = "on ~* +@all -@dangerous"
  authentication_mode {
    type = "iam"
  }
}

resource "aws_elasticache_user_group" "this" {
  engine        = "redis"
  user_group_id = var.name
  user_ids      = [aws_elasticache_user.default.user_id, aws_elasticache_user.app.user_id]
}

resource "aws_elasticache_replication_group" "this" {
  #checkov:skip=CKV2_AWS_50: failover follows the replica count: on in production, a single node elsewhere to save cost
  replication_group_id       = var.name
  description                = "OpsPilot ${var.name}"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = var.node_type
  num_cache_clusters         = var.replicas + 1
  automatic_failover_enabled = var.replicas > 0
  multi_az_enabled           = var.replicas > 0
  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [aws_security_group.this.id]
  at_rest_encryption_enabled = true
  kms_key_id                 = var.kms_key_arn
  transit_encryption_enabled = true
  user_group_ids             = [aws_elasticache_user_group.this.user_group_id]
  snapshot_retention_limit   = var.snapshot_retention_days
  auto_minor_version_upgrade = true
}
