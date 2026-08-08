# Identical variable surface to aws-sandbox except where noted -- a
# structural change that breaks the real environment breaks here first.
# See CONTRACT.md: this environment validates Terraform structure only,
# never IAM semantics (LocalStack's policy evaluation is an approximation,
# the same category of error as treating moto results as ground truth).

variable "expected_account_id" {
  type    = string
  default = "000000000000" # LocalStack's fixed default account.
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "namespace_salt" {
  type    = string
  default = "local-development"
}

variable "operator_principal_arns" {
  type    = list(string)
  default = ["arn:aws:iam::000000000000:root"]
}

variable "budget_notification_email" {
  type    = string
  default = ""
}

variable "enable_negative_controls" {
  type    = bool
  default = true
}

variable "enable_cloudtrail" {
  type    = bool
  default = false
}

variable "enable_data_events" {
  type    = bool
  default = false
}

variable "scratch_expiry_days" {
  type    = number
  default = 1
}

variable "log_retention_days" {
  type    = number
  default = 1
}

variable "localstack_endpoint" {
  description = "Base URL LocalStack listens on."
  type        = string
  default     = "http://localhost:4566"
}
