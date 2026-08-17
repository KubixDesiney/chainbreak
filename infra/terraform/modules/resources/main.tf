# The benign resources probes act on, plus the markers that make probe
# results interpretable. See CONTRACT.md, especially "the marker digests
# are load-bearing" -- content verification, not "no exception raised", is
# what makes a read probe's ALLOWED classification meaningful.

# ---------------------------------------------------------------------------
# Object storage
# ---------------------------------------------------------------------------

# checkov's production-hardening defaults assume a long-lived bucket; this
# one holds nothing but markers and scratch objects for the duration of one
# benchmark run (minutes) and is destroyed with the rest of the stack --
# each skip below is a check that either contradicts that lifetime directly
# or adds cost/complexity the $0.10-per-suite cost model (AWS_PROVIDER_SPEC
# section 9) does not budget for. (checkov only honors #checkov:skip
# comments placed *inside* the resource block, not preceding it.)
resource "aws_s3_bucket" "objectstore" {
  #checkov:skip=CKV2_AWS_62:No event-driven consumer exists; nothing would ever receive a notification.
  #checkov:skip=CKV_AWS_18:Access logging needs a second bucket for a bucket that lives minutes -- disproportionate to what it protects.
  #checkov:skip=CKV_AWS_144:Cross-region replication is for durability of long-lived data; force_destroy=true means this bucket is deleted by design at the end of every run.
  #checkov:skip=CKV_AWS_145:Already SSE-encrypted (AES256, below); a customer-managed KMS key adds per-request cost with no secret content to protect (SI-1 -- Terraform never handles secrets).
  #checkov:skip=CKV_AWS_21:Versioning would retain old marker generations the marker precondition check (P8) does not read; force_destroy already handles cleanup.
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

  # S3 can briefly report a newly created bucket as absent to the lifecycle
  # endpoint. The marker PUT is a completed bucket data-plane operation, so
  # sequencing this configuration after it removes that apply-time race.
  depends_on = [aws_s3_object.marker]

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

  # A separate, bucket-wide rule (empty filter) rather than folded into
  # "expire-scratch" above -- checkov's CKV_AWS_300 only credits an
  # abort_incomplete_multipart_upload block on a rule with no scoping
  # filter, so a prefix-scoped rule carrying it does not satisfy the check.
  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"

    filter {
      prefix = ""
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
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
  #checkov:skip=CKV_AWS_119:Encrypted at rest by default with an AWS-owned key already; a customer-managed CMK adds per-request KMS cost for a table holding only a non-secret marker digest (SI-1), destroyed within minutes.
  #checkov:skip=CKV_AWS_28:Point-in-time recovery protects against accidental deletion -- the literal outcome `terraform destroy` intentionally produces at the end of every run.
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
  #checkov:skip=CKV_AWS_158:No secrets ever reach this log group (SI-1 -- Terraform never handles secrets); a CMK adds cost with nothing sensitive to protect.
  #checkov:skip=CKV_AWS_338:A 1-year retention is for logs that outlive their infrastructure; this group is destroyed with the rest of the stack within minutes (var.log_retention_days is the short, deliberate retention already set below).
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
  #checkov:skip=CKV_AWS_117:A VPC adds a NAT gateway (real hourly cost) this $0.10-per-suite benchmark (AWS_PROVIDER_SPEC section 9) cannot absorb; the function calls no VPC-only resource.
  #checkov:skip=CKV_AWS_173:NAMESPACE below is a non-secret identifier (SI-1); nothing in this function's environment needs KMS.
  #checkov:skip=CKV_AWS_272:Code-signing is a supply-chain control for a deployment pipeline; this function's own source is the two-line probe target in lambda-src/, applied by this same Terraform run.
  #checkov:skip=CKV_AWS_116:function.invoke's probe (providers/aws/probes.py) always invokes synchronously (InvocationType=RequestResponse); a DLQ only ever fires for async invocations, which this benchmark never makes.
  #checkov:skip=CKV_AWS_50:X-Ray tracing is an observability aid for production request tracing; this function's entire behavior is a fixed, already-known payload (resources/CONTRACT.md).
  #checkov:skip=CKV_AWS_115:A reserved concurrency limit exists to protect other functions sharing an account's pool; a benchmark run's own probe volume is far below any default limit, and throttling it would corrupt probe results rather than protect anything.
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
  sqs_managed_sse_enabled    = true
}
