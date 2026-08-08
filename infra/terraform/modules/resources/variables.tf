# See CONTRACT.md for the full specification this module implements.

variable "namespace" {
  description = "The benchmark namespace from benchmark-account. Already carries its own \"cb-\" prefix (^cb-[0-9a-f]{8}$) -- every name below builds on it directly, with no second, literal \"cb-\"."
  type        = string
}

variable "marker_payload" {
  description = "Fixed content for both markers (S3 object body and the DynamoDB item's stored value). Its sha256 becomes objectstore_marker_sha256/keyvalue_marker_sha256 -- probes.py accepts a probe as ALLOWED only if the returned content matches this digest."
  type        = string
  default     = "{\"marker\":true}"
}

variable "scratch_expiry_days" {
  description = "Lifecycle expiry, in days, for objects under the run-scoped scratch/ prefix. Kept short: this is what bounds cost on an orphaned bucket if a destroy is ever missed."
  type        = number
  default     = 1
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the noop function's log group, managed explicitly so Lambda's implicit group cannot orphan with no expiry."
  type        = number
  default     = 1
}
