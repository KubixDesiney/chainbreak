# See CONTRACT.md for the full specification this module implements.

variable "expected_account_id" {
  description = "The AWS account this configuration is allowed to apply to. The plan fails if the caller's resolved account differs -- an operator pointed at the wrong account must never reach a diff that looks appliable."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be a 12-digit AWS account id."
  }
}

variable "namespace_salt" {
  description = "Operator-chosen salt included in the namespace hash so two workspaces (or two operators) in one account cannot collide on resource names."
  type        = string

  validation {
    condition     = length(var.namespace_salt) > 0
    error_message = "namespace_salt must not be empty."
  }
}

variable "budget_limit_usd" {
  description = "Monthly AWS Budgets alarm threshold in USD. Not a hard cap -- Budgets alerts, it does not block spend. The hard bound is the preflight cost estimate (SI-8) plus the run duration ceiling (SI-7)."
  type        = number
  default     = 5
}

variable "budget_notification_email" {
  description = "Email address for the budget alarm notification. Empty string disables the notification only -- the budget itself is always created."
  type        = string
  default     = ""
}

# Contract-only compatibility input; negative-control resources are created by
# the identities and delegation modules.
# tflint-ignore: terraform_unused_declarations
variable "enable_negative_controls" {
  description = "Whether the deliberately-defective negative-control roles will be provisioned elsewhere. Not used directly by this module (it creates no identities), but threaded through so every module's variable surface is consistent and the same tfvars file drives all of them."
  type        = bool
  default     = false
}

variable "enable_budget_alarm" {
  description = "Whether to provision the aws_budgets_budget resource at all. AWS Budgets is unsupported (and meaningless) against LocalStack, so the local-development environment sets this to false; every real environment must leave it true."
  type        = bool
  default     = true
}
