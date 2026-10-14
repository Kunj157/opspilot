output "primary_endpoint" {
  value = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "app_user_id" {
  value = aws_elasticache_user.app.user_id
}
