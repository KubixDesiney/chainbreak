# Optional provider-side corroboration. Default off. See CONTRACT.md and the
# variable descriptions above for why. Deliberately has no dependency on
# (and is not depended on by) the identities or resources modules --
# enabling or disabling observability must never change what is measured.

data "aws_caller_identity" "current" {}

# Same reasoning as modules/resources' objectstore bucket (see its own
# comment): this bucket only ever exists for one benchmark run's own
# CloudTrail delivery and is destroyed with the rest of the stack.
# (checkov only honors #checkov:skip comments placed *inside* the resource
# block, not preceding it.)
resource "aws_s3_bucket" "trail" {
  #checkov:skip=CKV2_AWS_62:No event-driven consumer exists; nothing would ever receive a notification.
  #checkov:skip=CKV_AWS_18:Access logging needs a second bucket for a bucket that lives minutes -- disproportionate to what it protects.
  #checkov:skip=CKV_AWS_144:Cross-region replication is for durability of long-lived data; force_destroy=true means this bucket is deleted by design at the end of every run.
  #checkov:skip=CKV_AWS_145:CloudTrail's own delivery contains no operator secrets (SI-1); a customer-managed KMS key adds per-request cost with no secret content to protect.
  #checkov:skip=CKV_AWS_21:Versioning would retain old trail-log generations nothing in this benchmark reads back; force_destroy already handles cleanup.
  count = var.enable_cloudtrail ? 1 : 0

  bucket        = "${var.namespace}-trail"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "trail" {
  count = var.enable_cloudtrail ? 1 : 0

  bucket = aws_s3_bucket.trail[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "trail" {
  count = var.enable_cloudtrail ? 1 : 0

  bucket = aws_s3_bucket.trail[0].id

  rule {
    id     = "expire-trail-logs"
    status = "Enabled"

    # An explicit empty prefix ("apply to every object") -- a bare filter{}
    # block is rejected by the provider (a real terraform validate finding,
    # not a style preference: "No attribute specified when one ... is
    # required").
    filter {
      prefix = ""
    }

    expiration {
      days = var.trail_retention_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_s3_bucket_policy" "trail" {
  count = var.enable_cloudtrail ? 1 : 0

  bucket = aws_s3_bucket.trail[0].id

  # The standard AWS-documented CloudTrail-to-S3 delivery policy, scoped to
  # this bucket and this account's trail only.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "CbCloudTrailAclCheck"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:GetBucketAcl"
        Resource  = aws_s3_bucket.trail[0].arn
      },
      {
        Sid       = "CbCloudTrailWrite"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.trail[0].arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"
        Condition = {
          StringEquals = { "s3:x-amz-acl" = "bucket-owner-full-control" }
        }
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "trail" {
  count = var.enable_cloudtrail ? 1 : 0

  name              = "/aws/cloudtrail/${var.namespace}"
  retention_in_days = var.trail_retention_days
}

resource "aws_iam_role" "trail_logs" {
  count = var.enable_cloudtrail ? 1 : 0

  name = "${var.namespace}-trail-logs"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudtrail.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "trail_logs" {
  count = var.enable_cloudtrail ? 1 : 0

  name = "${var.namespace}-trail-logs"
  role = aws_iam_role.trail_logs[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "CbCloudTrailLogsDelivery"
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.trail[0].arn}:*"
    }]
  })
}

resource "aws_cloudtrail" "trail" {
  count = var.enable_cloudtrail ? 1 : 0

  name                          = "${var.namespace}-trail"
  s3_bucket_name                = aws_s3_bucket.trail[0].id
  include_global_service_events = true
  is_multi_region_trail         = false
  enable_log_file_validation    = true

  cloud_watch_logs_group_arn = "${aws_cloudwatch_log_group.trail[0].arn}:*"
  cloud_watch_logs_role_arn  = aws_iam_role.trail_logs[0].arn

  dynamic "event_selector" {
    for_each = var.enable_data_events ? [1] : []
    content {
      read_write_type           = "All"
      include_management_events = true

      # Every S3 bucket in the account, not just cb-<ns>-objectstore --
      # this module's own CONTRACT.md gives it no resource_arns input to
      # scope more tightly to (unlike delegation, which does), so a
      # narrower selector is not currently expressible here. Data events
      # stay off by default specifically because of this billed-per-event,
      # broader-than-ideal surface.
      data_resource {
        type   = "AWS::S3::Object"
        values = ["arn:aws:s3:::"]
      }
    }
  }

  depends_on = [aws_s3_bucket_policy.trail, aws_iam_role_policy.trail_logs]
}
