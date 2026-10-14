# PostgreSQL for OpsPilot: encrypted, backed up, SSL only, reachable only from
# the cluster, with the master password generated and rotated by RDS in
# Secrets Manager (never in Terraform state).

resource "aws_db_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.database_subnet_ids
}

resource "aws_security_group" "this" {
  name        = "${var.name}-postgres"
  description = "PostgreSQL, reachable only from the EKS cluster"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "from_cluster" {
  security_group_id            = aws_security_group.this.id
  description                  = "PostgreSQL from EKS"
  referenced_security_group_id = var.client_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_db_parameter_group" "this" {
  name   = "${var.name}-postgres17"
  family = "postgres17"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "500"
  }
}

resource "aws_db_instance" "this" {
  #checkov:skip=CKV_AWS_157: multi_az is per environment: on in production, off in development and staging to save cost
  identifier                          = var.name
  engine                              = "postgres"
  engine_version                      = "17"
  instance_class                      = var.instance_class
  allocated_storage                   = var.storage_gb
  max_allocated_storage               = var.storage_gb * 4
  storage_type                        = "gp3"
  storage_encrypted                   = true
  kms_key_id                          = var.kms_key_arn
  db_name                             = "opspilot"
  username                            = "opspilot"
  manage_master_user_password         = true
  master_user_secret_kms_key_id       = var.kms_key_arn
  db_subnet_group_name                = aws_db_subnet_group.this.name
  vpc_security_group_ids              = [aws_security_group.this.id]
  parameter_group_name                = aws_db_parameter_group.this.name
  multi_az                            = var.multi_az
  publicly_accessible                 = false
  backup_retention_period             = var.backup_retention_days
  backup_window                       = "02:00-03:00"
  maintenance_window                  = "sun:03:30-sun:04:30"
  copy_tags_to_snapshot               = true
  deletion_protection                 = var.deletion_protection
  skip_final_snapshot                 = !var.deletion_protection
  final_snapshot_identifier           = var.deletion_protection ? "${var.name}-final" : null
  auto_minor_version_upgrade          = true
  iam_database_authentication_enabled = true
  performance_insights_enabled        = true
  performance_insights_kms_key_id     = var.kms_key_arn
  monitoring_interval                 = 60
  monitoring_role_arn                 = aws_iam_role.monitoring.arn
  enabled_cloudwatch_logs_exports     = ["postgresql", "upgrade"]
}

data "aws_iam_policy_document" "monitoring_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["monitoring.rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "monitoring" {
  name               = "${var.name}-rds-monitoring"
  assume_role_policy = data.aws_iam_policy_document.monitoring_assume.json
}

resource "aws_iam_role_policy_attachment" "monitoring" {
  role       = aws_iam_role.monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}
