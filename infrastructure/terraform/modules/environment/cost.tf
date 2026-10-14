# Cost controls: a monthly budget with alerts, and non-production node groups
# scaled to zero outside working hours.

resource "aws_budgets_budget" "monthly" {
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:environment$${var.environment}"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.alert_emails
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.alert_emails
  }
}

data "aws_autoscaling_groups" "nodes" {
  count = var.office_hours == null ? 0 : 1
  filter {
    name   = "tag:eks:cluster-name"
    values = [module.eks.cluster_name]
  }
  depends_on = [module.eks]
}

resource "aws_autoscaling_schedule" "stop" {
  for_each               = var.office_hours == null ? toset([]) : toset(data.aws_autoscaling_groups.nodes[0].names)
  scheduled_action_name  = "stop-after-hours"
  autoscaling_group_name = each.value
  recurrence             = var.office_hours.stop_cron
  time_zone              = var.office_hours.time_zone
  min_size               = 0
  max_size               = 0
  desired_capacity       = 0
}

resource "aws_autoscaling_schedule" "start" {
  for_each               = var.office_hours == null ? toset([]) : toset(data.aws_autoscaling_groups.nodes[0].names)
  scheduled_action_name  = "start-for-the-day"
  autoscaling_group_name = each.value
  recurrence             = var.office_hours.start_cron
  time_zone              = var.office_hours.time_zone
  min_size               = var.office_hours.min
  max_size               = var.office_hours.max
  desired_capacity       = var.office_hours.min
}
