output "endpoint" {
  value = aws_db_instance.this.address
}

# The ARN of the RDS-managed secret holding the password, never the password.
output "master_secret_arn" {
  value = aws_db_instance.this.master_user_secret[0].secret_arn
}
