output "kms_key_arn" {
  value = aws_kms_key.this.arn
}

# ARNs only; never values.
output "secret_arns" {
  value = { for name, secret in aws_secretsmanager_secret.this : name => secret.arn }
}
