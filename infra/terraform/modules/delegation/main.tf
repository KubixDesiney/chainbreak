# Per-hop permission policies expressing each agent's *provisioned*
# capability ceiling -- the maximum a role could ever exercise, narrowed at
# runtime by session policies the adapter synthesizes from binding metadata
# (never hand-written per scenario). See CONTRACT.md's "Purpose and
# boundary" for why provisioning already-narrow roles here would be the
# wrong layer for attenuation.
#
# Customer-managed (not inline) policies, one per role: only a managed
# policy has its own ARN, which is what this module's required
# `policy_arns` output needs.

data "aws_caller_identity" "current" {}

locals {
  # index 0 = agent-a's name .. index 5 = agent-f's (var.agent_role_names'
  # own documented ordering contract).
  agent_by_index = { for i, name in var.agent_role_names : i => name }

  # Every non-delegate capability's actual resource ARN, keyed by the
  # capability_action_map entries' resource_key.
  resource_arn_by_key = {
    objectstore_marker  = "${var.resource_arns.objectstore_bucket_arn}/${var.namespace}/markers/marker.json"
    objectstore_scratch = "${var.resource_arns.objectstore_bucket_arn}/${var.namespace}/scratch/*"
    objectstore_bucket  = var.resource_arns.objectstore_bucket_arn
    keyvalue_table      = var.resource_arns.keyvalue_table_arn
    keyvalue_scratch    = var.resource_arns.keyvalue_table_arn
    function            = var.resource_arns.function_arn
    queue               = var.resource_arns.queue_arn
    whoami              = "*"
  }

  # Every capability except identity.delegate, which is handled separately
  # below (per-role next-hop target, never a wildcard).
  non_delegate_capabilities = {
    for id, spec in var.capability_action_map : id => spec
    if id != "identity.delegate"
  }

  # One statement per non-delegate capability, common to every agent role.
  # keyvalue.write carries a second, independent confinement control beyond
  # the resource-ARN scoping already in resource_arn_by_key.
  #
  # objectstore.write does NOT get an analogous second control: an earlier
  # revision attached a `Condition` on `s3:prefix`, matching what
  # AWS_PROVIDER_SPEC section 5 asked for at the time -- but `s3:prefix` is
  # populated only on `s3:ListBucket` requests; `s3:PutObject`/`s3:GetObject`
  # never put it in the request context. A `Condition` whose key is absent
  # from the request evaluates to false, so the *entire statement* failed to
  # match on every real PutObject call, not just the condition -- confirmed
  # empirically against a real account (M8/M9 real-account verification,
  # PROJECT_STATUS.md): every agent's objectstore.write probe came back
  # DENIED_IMPLICIT ("no identity-based policy allows the s3:PutObject
  # action") despite the ceiling policy visibly granting it. The resource
  # ARN (`.../scratch/*`, already fully object-key-scoped) is the only
  # confinement control an S3 object-level action can carry; there is no S3
  # equivalent of DynamoDB's LeadingKeys for a per-object grant, since the
  # object key IS the resource, not a value inside a shared-resource request.
  ceiling_statements = [
    for id, spec in local.non_delegate_capabilities : merge(
      {
        Sid      = "CbAllow${replace(title(replace(id, ".", " ")), " ", "")}"
        Effect   = "Allow"
        Action   = spec.actions
        Resource = local.resource_arn_by_key[spec.resource_key]
      },
      id == "keyvalue.write" ? {
        Condition = {
          "ForAllValues:StringLike" = { "dynamodb:LeadingKeys" = ["cb-scratch#*"] }
        }
      } : {}
    )
  ]
}

resource "aws_iam_policy" "ceiling" {
  for_each = local.agent_by_index

  name = "${each.value}-ceiling"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [{
        Sid      = "CbAlwaysWhoami"
        Effect   = "Allow"
        Action   = ["sts:GetCallerIdentity"]
        Resource = "*"
      }],
      local.ceiling_statements,
      # identity.delegate: the specific next-hop role ARN, never a
      # wildcard over role/<ns>-agent-* -- omitted entirely for the last
      # link in the chain (agent-f), which has no further hop.
      each.key + 1 < length(var.agent_role_names) ? [{
        Sid      = "CbAllowIdentityDelegate"
        Effect   = "Allow"
        Action   = ["sts:AssumeRole"]
        Resource = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.agent_by_index[each.key + 1]}"
      }] : []
    )
  })
}

resource "aws_iam_role_policy_attachment" "ceiling" {
  for_each = local.agent_by_index

  role       = each.value
  policy_arn = aws_iam_policy.ceiling[each.key].arn
}

# ---------------------------------------------------------------------------
# Negative controls -- one additional, deliberately-defective statement each,
# attached only under enable_negative_controls. Sids name the defect.
# ---------------------------------------------------------------------------

resource "aws_iam_policy" "negative_control_expansion" {
  count = var.enable_negative_controls ? 1 : 0
  name  = "${var.namespace}-agent-b-expansion-defect"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "CbNegativeControlExpansionKeyvalueRead"
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem"]
      Resource = var.resource_arns.keyvalue_table_arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "negative_control_expansion" {
  count      = var.enable_negative_controls ? 1 : 0
  role       = "${var.namespace}-agent-b-expansion"
  policy_arn = aws_iam_policy.negative_control_expansion[0].arn
}

resource "aws_iam_policy" "negative_control_survival" {
  count = var.enable_negative_controls ? 1 : 0
  name  = "${var.namespace}-agent-b-survival-defect"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "CbNegativeControlSurvivalFunctionInvoke"
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = var.resource_arns.function_arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "negative_control_survival" {
  count      = var.enable_negative_controls ? 1 : 0
  role       = "${var.namespace}-agent-b-survival"
  policy_arn = aws_iam_policy.negative_control_survival[0].arn
}

resource "aws_iam_policy" "negative_control_nonmonotone" {
  count = var.enable_negative_controls ? 1 : 0
  name  = "${var.namespace}-agent-c-nonmonotone-defect"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "CbNegativeControlNonmonotoneKeyvalueWrite"
      Effect   = "Allow"
      Action   = ["dynamodb:PutItem"]
      Resource = var.resource_arns.keyvalue_table_arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "negative_control_nonmonotone" {
  count      = var.enable_negative_controls ? 1 : 0
  role       = "${var.namespace}-agent-c-nonmonotone"
  policy_arn = aws_iam_policy.negative_control_nonmonotone[0].arn
}
