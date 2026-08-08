# See CONTRACT.md for the full specification this module implements.
# Default off: CHAINBREAK's measurements are client-side (a probe outcome is
# observed directly, never inferred from a log). CloudTrail is corroboration
# only -- delivery latency is minutes, orders of magnitude coarser than the
# sub-second intervals the revocation family measures.

variable "namespace" {
  description = "From benchmark-account. Already carries its own \"cb-\" prefix."
  type        = string
}

variable "enable_cloudtrail" {
  description = "Provisions a CloudTrail trail plus its log bucket. Off by default."
  type        = bool
  default     = false
}

variable "trail_retention_days" {
  description = "Lifecycle expiry, in days, for the trail's S3 log bucket."
  type        = number
  default     = 7
}

variable "enable_data_events" {
  description = "Adds S3/DynamoDB data-event logging to the trail. Off by default: the first management-events trail per account is free, but data events are billed per event, and a probe-heavy run generates many."
  type        = bool
  default     = false
}
