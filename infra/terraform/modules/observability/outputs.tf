output "trail_name" {
  description = "Null when enable_cloudtrail = false."
  value       = var.enable_cloudtrail ? aws_cloudtrail.trail[0].name : null
}

output "trail_bucket" {
  description = "Null when enable_cloudtrail = false."
  value       = var.enable_cloudtrail ? aws_s3_bucket.trail[0].id : null
}

output "log_group_names" {
  description = "Empty when enable_cloudtrail = false."
  value       = var.enable_cloudtrail ? [aws_cloudwatch_log_group.trail[0].name] : []
}
