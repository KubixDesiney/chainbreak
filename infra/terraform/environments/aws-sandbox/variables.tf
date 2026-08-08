# See terraform.tfvars.example for operator-facing documentation of every
# variable below; descriptions here are kept short deliberately.

variable "expected_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be a 12-digit AWS account id."
  }
}

variable "region" {
  type = string
}

variable "namespace_salt" {
  type = string
}

variable "operator_principal_arns" {
  type = list(string)
}

variable "budget_limit_usd" {
  type    = number
  default = 5
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
