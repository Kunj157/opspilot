output "alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "application_log_group" {
  value = aws_cloudwatch_log_group.application.name
}
