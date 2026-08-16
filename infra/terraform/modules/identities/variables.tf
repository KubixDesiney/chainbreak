# See CONTRACT.md for the full specification this module implements.

variable "namespace" {
  description = "From benchmark-account. Already carries its own \"cb-\" prefix -- every role name below builds on it directly."
  type        = string
}

variable "external_id" {
  description = "From benchmark-account. Bound into every trust-policy condition."
  type        = string
}

variable "operator_principal_arns" {
  description = "Who may assume bootstrap and principal. Prefer an SSO permission-set role or a CI OIDC role over an IAM user."
  type        = list(string)

  validation {
    condition     = length(var.operator_principal_arns) > 0
    error_message = "operator_principal_arns must not be empty -- nothing could ever assume bootstrap or principal otherwise."
  }
}

# Contract-only compatibility input; the fixed six-role contract is validated
# but the roles remain explicit for stable output names.
# tflint-ignore: terraform_unused_declarations
variable "agent_count" {
  description = "Documented for the module's variable surface; this implementation always provisions exactly six agent roles (agent-a..agent-f), matching AWS_PROVIDER_SPEC section 3's fixed six-role design (\"so scenarios up to depth 6 need no re-apply\") and this module's own unconditional agent_a_role_arn..agent_f_role_arn output list."
  type        = number
  default     = 6

  validation {
    condition     = var.agent_count == 6
    error_message = "This implementation always provisions exactly six agent roles; agent_count exists for the module's documented variable surface but must currently be 6."
  }
}

variable "resource_arns" {
  description = "Bucket, table, function, queue ARNs from the resources module (its resource_arns output, passed straight through)."
  type = object({
    objectstore_bucket_arn = string
    keyvalue_table_arn     = string
    function_arn           = string
    queue_arn              = string
  })
}

variable "max_session_duration" {
  description = "Max session duration (seconds) each role's trust relationship permits. STS further caps chained AssumeRole at 3600s regardless of this value (AWS_PROVIDER_SPEC section 4)."
  type        = number
  default     = 3600
}

variable "enable_negative_controls" {
  description = "Provisions the three deliberately-defective roles (trust policies only -- their defective capability grants are attached by the delegation module)."
  type        = bool
  default     = false
}
