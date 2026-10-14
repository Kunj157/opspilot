output "primary_endpoint" {
  value = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "app_user_id" {
  value = aws_elasticache_user.app.user_id
}

output "replication_group_arn" {
  value = aws_elasticache_replication_group.this.arn
}

output "app_user_arn" {
  value = aws_elasticache_user.app.arn
}

output "app_user_name" {
  value = aws_elasticache_user.app.user_name
}
