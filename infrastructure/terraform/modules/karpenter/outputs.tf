output "controller_role_arn" {
  value = module.controller_role.arn
}

output "node_role_arn" {
  value = aws_iam_role.node.arn
}

output "interruption_queue" {
  value = aws_sqs_queue.interruption.name
}
