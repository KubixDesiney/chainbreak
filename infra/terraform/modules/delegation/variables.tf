# See CONTRACT.md for the full specification this module implements.

variable "namespace" {
  description = "From benchmark-account. Already carries its own \"cb-\" prefix."
  type        = string
}

variable "agent_role_names" {
  description = "The six agent role NAMES (not ARNs), in chain order a..f -- index 0 is agent-a's name, index 5 is agent-f's. Order matters: it is how this module derives each role's next-hop target for identity.delegate, since agent-f (the last link) gets no delegate statement at all."
  type        = list(string)

  validation {
    condition     = length(var.agent_role_names) == 6
    error_message = "agent_role_names must list exactly six role names, in chain order a..f."
  }
}

variable "resource_arns" {
  description = "Bucket, table, function, queue ARNs from the resources module."
  type = object({
    objectstore_bucket_arn = string
    keyvalue_table_arn     = string
    function_arn           = string
    queue_arn              = string
  })
}

variable "capability_action_map" {
  description = "The capability -> action/resource-kind mapping. Mirrors providers/aws/bindings.py::_ACTIONS in the Python adapter exactly, so Terraform's provisioned ceiling and the Python bindings the adapter uses at runtime cannot drift silently -- see delegation/CONTRACT.md's own stated purpose for this variable. No automated check currently cross-verifies the two stay in sync (a known gap, not a design decision); a future milestone should add one."
  type = map(object({
    actions      = list(string)
    resource_key = string
  }))
  default = {
    "objectstore.read" = {
      actions      = ["s3:GetObject"]
      resource_key = "objectstore_marker"
    }
    "objectstore.write" = {
      # s3:GetObject is also required here: the write probe confirms its
      # own write via HeadObject, which -- like GetObject -- has no
      # separate s3:HeadObject IAM action (providers/aws/bindings.py's own
      # comment records this same divergence on the Python side).
      actions      = ["s3:PutObject", "s3:GetObject"]
      resource_key = "objectstore_scratch"
    }
    "objectstore.list" = {
      actions      = ["s3:ListBucket"]
      resource_key = "objectstore_bucket"
    }
    "keyvalue.read" = {
      actions      = ["dynamodb:GetItem"]
      resource_key = "keyvalue_table"
    }
    "keyvalue.write" = {
      actions      = ["dynamodb:PutItem", "dynamodb:GetItem"]
      resource_key = "keyvalue_scratch"
    }
    "function.invoke" = {
      actions      = ["lambda:InvokeFunction"]
      resource_key = "function"
    }
    "queue.send" = {
      actions      = ["sqs:SendMessage"]
      resource_key = "queue"
    }
    "queue.receive" = {
      actions      = ["sqs:ReceiveMessage"]
      resource_key = "queue"
    }
    "identity.whoami" = {
      actions      = ["sts:GetCallerIdentity"]
      resource_key = "whoami"
    }
    # identity.delegate is handled separately (per-role next-hop target,
    # never a wildcard over role/cb-<ns>-agent-*) -- listed here only so
    # every catalog capability has an entry.
    "identity.delegate" = {
      actions      = ["sts:AssumeRole"]
      resource_key = "delegate"
    }
  }
}

variable "enable_negative_controls" {
  description = "Attaches the three deliberately-defective capability grants to the negative-control roles identities provisions under the same flag."
  type        = bool
  default     = false
}
