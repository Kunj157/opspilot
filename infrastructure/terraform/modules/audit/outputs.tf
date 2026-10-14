output "trail_arn" {
  value = aws_cloudtrail.this.arn
}

output "bucket" {
  value = aws_s3_bucket.trail.id
}

output "guardduty_detector_id" {
  value = var.enable_guardduty ? aws_guardduty_detector.this[0].id : null
}
