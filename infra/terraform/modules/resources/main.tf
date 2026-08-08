# The benign resources probes act on, plus the markers that make probe
# results interpretable. See CONTRACT.md, especially "the marker digests
# are load-bearing" -- content verification, not "no exception raised", is
# what makes a read probe's ALLOWED classification meaningful.

# ---------------------------------------------------------------------------
# Object storage
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "objectstore" {
  bucket = "${var.namespace}-objectstore"
  # Only ever holds markers and run-scoped scratch objects -- safe to force.
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "objectstore" {
  bucket = aws_s3_bucket.objectstore.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "objectstore" {
  bucket = aws_s3_bucket.objectstore.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "objectstore" {
  bucket = aws_s3_bucket.objectstore.id

  rule {
    id     = "expire-scratch"
    status = "Enabled"

    filter {
      prefix = "${var.namespace}/scratch/"
    }

    expiration {
      days = var.scratch_expiry_days
    }
  }
}

resource "aws_s3_object" "marker" {
  bucket       = aws_s3_bucket.objectstore.id
  key          = "${var.namespace}/markers/marker.json"
  content      = var.marker_payload
  content_type = "application/json"
}

# ---------------------------------------------------------------------------
# Key/value
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table" "keyvalue" {
  name         = "${var.namespace}-keyvalue"
  billing_mode = "PAY_PER_REQUEST" # provisioned capacity is the likeliest way to accidentally spend
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}

resource "aws_dynamodb_table_item" "marker" {
  table_name = aws_dynamodb_table.keyvalue.name
  hash_key   = aws_dynamodb_table.keyvalue.hash_key

  item = jsonencode({
    pk     = { S = "cb-marker" }
    value  = { S = var.marker_payload }
    digest = { S = "sha256:${sha256(var.marker_payload)}" }
  })
}

# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------

data "archive_file" "noop" {
  type        = "zip"
  source_dir  = "${path.module}/lambda-src"
  output_path = "${path.module}/.build/noop.zip"
}

resource "aws_cloudwatch_log_group" "noop" {
  # Managed explicitly so Lambda's implicit group (unbounded retention)
  # cannot orphan.
  name              = "/aws/lambda/${var.namespace}-noop"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "noop_exec" {
  name = "${var.namespace}-noop-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "noop_exec_logs" {
  name = "${var.namespace}-noop-exec-logs"
  role = aws_iam_role.noop_exec.id

  # Scoped to this function's own log group only -- the AWS-managed
  # AWSLambdaBasicExecutionRole policy uses Resource:"*" for logs actions,
  # which every module's own "no Resource:*" rule (except
  # sts:GetCallerIdentity) forbids.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
      ]
      Resource = "${aws_cloudwatch_log_group.noop.arn}:*"
    }]
  })
}

resource "aws_lambda_function" "noop" {
  function_name = "${var.namespace}-noop"
  role          = aws_iam_role.noop_exec.arn
  handler       = "lambda_function.handler"
  runtime       = "python3.12"
  memory_size   = 128
  timeout       = 3

  filename         = data.archive_file.noop.output_path
  source_code_hash = data.archive_file.noop.output_base64sha256

  environment {
    variables = {
      NAMESPACE = var.namespace
    }
  }

  depends_on = [aws_cloudwatch_log_group.noop, aws_iam_role_policy.noop_exec_logs]
}

# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "queue" {
  name                       = "${var.namespace}-queue"
  visibility_timeout_seconds = 0 # receive probes stay effectively non-destructive
}
