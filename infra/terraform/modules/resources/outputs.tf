output "objectstore_bucket" {
  description = "The S3 bucket name."
  value       = aws_s3_bucket.objectstore.id
}

output "objectstore_marker_key" {
  description = "Object key of the read-probe marker."
  value       = aws_s3_object.marker.key
}

output "objectstore_marker_sha256" {
  description = "sha256:<hex> digest of the marker body. A read probe is ALLOWED only if the returned content matches this."
  value       = "sha256:${sha256(var.marker_payload)}"
}

output "keyvalue_table" {
  description = "The DynamoDB table name."
  value       = aws_dynamodb_table.keyvalue.name
}

output "keyvalue_marker_pk" {
  description = "Partition key of the read-probe marker item."
  value       = "cb-marker"
}

output "keyvalue_marker_sha256" {
  description = "sha256:<hex> digest stored in the marker item's own digest attribute."
  value       = "sha256:${sha256(var.marker_payload)}"
}

output "function_name" {
  description = "The Lambda function name."
  value       = aws_lambda_function.noop.function_name
}

output "function_arn" {
  description = "The Lambda function ARN."
  value       = aws_lambda_function.noop.arn
}

output "queue_url" {
  description = "The SQS queue URL."
  value       = aws_sqs_queue.queue.url
}

output "queue_arn" {
  description = "The SQS queue ARN."
  value       = aws_sqs_queue.queue.arn
}

output "resource_arns" {
  description = "The ARN set `identities` consumes to scope its permission policies."
  value = {
    objectstore_bucket_arn = aws_s3_bucket.objectstore.arn
    keyvalue_table_arn     = aws_dynamodb_table.keyvalue.arn
    function_arn           = aws_lambda_function.noop.arn
    queue_arn              = aws_sqs_queue.queue.arn
  }
}
