# Bootstrap, principal, and agent roles with their trust and permission
# policies. See CONTRACT.md -- this is the module where a mistake has the
# largest blast radius, so its rules are the strictest: no Resource:"*"
# anywhere except the sts:GetCallerIdentity control-capability statement, no
# iam:* on principal or any agent role, and bootstrap can target only
# agent-* roles, never itself or principal (SI-12, defense in depth on top
# of the code-level enforcement in providers/aws/mutation.py).

locals {
  # sts:GetCallerIdentity is the one action every role gets on Resource:"*"
  # -- it is never denied by IAM and names no specific resource to scope to
  # (the control capability, AWS_PROVIDER_SPEC section 6.2).
  whoami_statement = {
    Sid      = "CbAlwaysWhoami"
    Effect   = "Allow"
    Action   = ["sts:GetCallerIdentity"]
    Resource = "*"
  }

  operator_principals = { AWS = var.operator_principal_arns }

  trust_policy_operator = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = local.operator_principals
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "sts:ExternalId" = var.external_id }
      }
    }]
  })
}

# ---------------------------------------------------------------------------
# Bootstrap -- deliberately not a node in any authorization graph
# ---------------------------------------------------------------------------

resource "aws_iam_role" "bootstrap" {
  name                 = "${var.namespace}-bootstrap"
  assume_role_policy   = local.trust_policy_operator
  max_session_duration = var.max_session_duration
}

resource "aws_iam_role_policy" "bootstrap" {
  name = "${var.namespace}-bootstrap"
  role = aws_iam_role.bootstrap.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      local.whoami_statement,
      {
        Sid      = "CbBootstrapMarkers"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${var.resource_arns.objectstore_bucket_arn}/*"
      },
      {
        Sid      = "CbBootstrapKeyvalueMarker"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
        Resource = var.resource_arns.keyvalue_table_arn
      },
      {
        Sid      = "CbBootstrapFunctionAlive"
        Effect   = "Allow"
        Action   = ["lambda:GetFunction"]
        Resource = var.resource_arns.function_arn
      },
      {
        Sid      = "CbBootstrapQueuePresent"
        Effect   = "Allow"
        Action   = ["sqs:GetQueueAttributes"]
        Resource = var.resource_arns.queue_arn
      },
      {
        # Explicit list of the six agent role ARNs, not a wildcard pattern
        # -- the stricter of the two scoping descriptions CONTRACT.md gives
        # for bootstrap ("explicit role-ARN lists" vs. a "cb-<ns>-agent-*"
        # pattern), and it structurally cannot ever match bootstrap's own
        # ARN or principal's, which the wildcard pattern alone would not
        # rule out as robustly.
        Sid    = "CbBootstrapMutatesAgentPolicyOnly"
        Effect = "Allow"
        Action = [
          "iam:GetRole",
          "iam:GetRolePolicy",
          "iam:ListRolePolicies",
          "iam:PutRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:UpdateAssumeRolePolicy",
        ]
        Resource = concat(
          [
            aws_iam_role.agent_a.arn,
            aws_iam_role.agent_b.arn,
            aws_iam_role.agent_c.arn,
            aws_iam_role.agent_d.arn,
            aws_iam_role.agent_e.arn,
            aws_iam_role.agent_f.arn,
          ],
          var.enable_negative_controls ? [aws_iam_role.agent_c_stale[0].arn] : []
        )
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# Principal -- the graph root. No iam:* permission anywhere.
# ---------------------------------------------------------------------------

resource "aws_iam_role" "principal" {
  name                 = "${var.namespace}-principal"
  assume_role_policy   = local.trust_policy_operator
  max_session_duration = var.max_session_duration
}

resource "aws_iam_role_policy" "principal" {
  name = "${var.namespace}-principal"
  role = aws_iam_role.principal.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      local.whoami_statement,
      {
        # The graph root's own baseline: reach agent-a. Deeper reach and
        # every other capability an agent needs are the delegation module's
        # per-hop ceiling policies, attached to the agent roles themselves
        # -- provisioning that ceiling directly on principal instead would
        # blur "what the graph root can do" with "what a scenario measures",
        # which is exactly the mistake delegation/CONTRACT.md warns against.
        Sid      = "CbPrincipalDelegateToAgentA"
        Effect   = "Allow"
        Action   = ["sts:AssumeRole"]
        Resource = aws_iam_role.agent_a.arn
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# Agents -- the measurement subjects
# ---------------------------------------------------------------------------

resource "aws_iam_role" "agent_a" {
  name                 = "${var.namespace}-agent-a"
  max_session_duration = var.max_session_duration
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = [aws_iam_role.principal.arn, aws_iam_role.bootstrap.arn] }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "sts:ExternalId" = var.external_id }
        StringLike   = { "sts:RoleSessionName" = "${var.namespace}-*" }
      }
    }]
  })
}

resource "aws_iam_role" "agent_b" {
  name                 = "${var.namespace}-agent-b"
  max_session_duration = var.max_session_duration
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = [aws_iam_role.agent_a.arn, aws_iam_role.bootstrap.arn] }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "sts:ExternalId" = var.external_id }
        StringLike   = { "sts:RoleSessionName" = "${var.namespace}-*" }
      }
    }]
  })
}

resource "aws_iam_role" "agent_c" {
  name                 = "${var.namespace}-agent-c"
  max_session_duration = var.max_session_duration
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = [aws_iam_role.agent_b.arn, aws_iam_role.bootstrap.arn] }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "sts:ExternalId" = var.external_id }
        StringLike   = { "sts:RoleSessionName" = "${var.namespace}-*" }
      }
    }]
  })
}

resource "aws_iam_role" "agent_d" {
  name                 = "${var.namespace}-agent-d"
  max_session_duration = var.max_session_duration
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = [aws_iam_role.agent_c.arn, aws_iam_role.bootstrap.arn] }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "sts:ExternalId" = var.external_id }
        StringLike   = { "sts:RoleSessionName" = "${var.namespace}-*" }
      }
    }]
  })
}

resource "aws_iam_role" "agent_e" {
  name                 = "${var.namespace}-agent-e"
  max_session_duration = var.max_session_duration
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = [aws_iam_role.agent_d.arn, aws_iam_role.bootstrap.arn] }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "sts:ExternalId" = var.external_id }
        StringLike   = { "sts:RoleSessionName" = "${var.namespace}-*" }
      }
    }]
  })
}

resource "aws_iam_role" "agent_f" {
  name                 = "${var.namespace}-agent-f"
  max_session_duration = var.max_session_duration
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = [aws_iam_role.agent_e.arn, aws_iam_role.bootstrap.arn] }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "sts:ExternalId" = var.external_id }
        StringLike   = { "sts:RoleSessionName" = "${var.namespace}-*" }
      }
    }]
  })
}

# Dedicated stale-authority control role. Its baseline objectstore grant is
# an inline policy that the REMOVE_INLINE_POLICY mutation can delete. The
# ordinary agent-c role must retain its Terraform ceiling for the positive
# scenarios, so reusing it would make the AWS stale-session premise invalid.
resource "aws_iam_role" "agent_c_stale" {
  count                = var.enable_negative_controls ? 1 : 0
  name                 = "${var.namespace}-agent-c-stale"
  max_session_duration = var.max_session_duration
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = [aws_iam_role.agent_b.arn, aws_iam_role.bootstrap.arn] }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "sts:ExternalId" = var.external_id }
        StringLike   = { "sts:RoleSessionName" = "${var.namespace}-*" }
      }
    }]
  })
}

# ---------------------------------------------------------------------------
# Negative-control roles -- trust policies only. Their defective capability
# grants are attached by the delegation module (delegation/CONTRACT.md).
# Names carry the defect so an operator reading the console sees what they
# are.
# ---------------------------------------------------------------------------

resource "aws_iam_role" "agent_b_expansion" {
  count                = var.enable_negative_controls ? 1 : 0
  name                 = "${var.namespace}-agent-b-expansion"
  max_session_duration = var.max_session_duration
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = [aws_iam_role.agent_a.arn, aws_iam_role.bootstrap.arn] }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "sts:ExternalId" = var.external_id }
        StringLike   = { "sts:RoleSessionName" = "${var.namespace}-*" }
      }
    }]
  })
}

resource "aws_iam_role" "agent_b_survival" {
  count                = var.enable_negative_controls ? 1 : 0
  name                 = "${var.namespace}-agent-b-survival"
  max_session_duration = var.max_session_duration
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = [aws_iam_role.agent_a.arn, aws_iam_role.bootstrap.arn] }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "sts:ExternalId" = var.external_id }
        StringLike   = { "sts:RoleSessionName" = "${var.namespace}-*" }
      }
    }]
  })
}

resource "aws_iam_role" "agent_c_nonmonotone" {
  count                = var.enable_negative_controls ? 1 : 0
  name                 = "${var.namespace}-agent-c-nonmonotone"
  max_session_duration = var.max_session_duration
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = [aws_iam_role.agent_b.arn, aws_iam_role.bootstrap.arn] }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "sts:ExternalId" = var.external_id }
        StringLike   = { "sts:RoleSessionName" = "${var.namespace}-*" }
      }
    }]
  })
}
