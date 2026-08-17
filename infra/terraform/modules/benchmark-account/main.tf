# Account-level guardrails and the namespace every other module depends on.
# See CONTRACT.md. This module creates nothing an experiment probes; it
# creates the conditions under which probing is safe -- no IAM identities,
# no data resources, guardrails only.

data "aws_caller_identity" "current" {
  # Read at plan time (data sources have no apply-time deferral), so this
  # postcondition is what makes an account mismatch a PLAN failure, not an
  # apply-time surprise -- the single most important check in the project
  # (AWS_PROVIDER_SPEC section 2, P2).
  lifecycle {
    postcondition {
      condition     = self.account_id == var.expected_account_id
      error_message = "Resolved account ${self.account_id} does not match expected_account_id ${var.expected_account_id}. Refusing to plan against the wrong account."
    }
  }
}

data "aws_region" "current" {}

locals {
  # "cb-" + substr(sha1(account_id + workspace + salt), 0, 8) -- stable
  # across applies within a workspace (account id, workspace name and salt
  # are all apply-time-stable inputs), distinct across workspaces.
  namespace = "cb-${substr(sha1("${data.aws_caller_identity.current.account_id}${terraform.workspace}${var.namespace_salt}"), 0, 8)}"

  # Every trust-policy condition compares against this. Literal per
  # CONTRACT.md's own formula ("cb-" + namespace); namespace already carries
  # its own "cb-" prefix, so this value is doubly-prefixed by construction
  # ("cb-cb-xxxxxxxx"-shaped) -- harmless, since external_id is only ever
  # compared for string equality between this output and the trust policies
  # `identities` writes, never independently reconstructed by a third party.
  external_id = "cb-${local.namespace}"

  # sha256 over the sorted output map -- jsonencode() sorts object keys
  # alphabetically, which is what "sorted" means here without a second,
  # separate sort step.
  infrastructure_fingerprint = "sha256:${sha256(jsonencode({
    account_id  = data.aws_caller_identity.current.account_id
    external_id = local.external_id
    namespace   = local.namespace
    region      = data.aws_region.current.name
  }))}"
}

resource "aws_sns_topic" "budget_alerts" {
  count = var.enable_budget_alarm ? 1 : 0

  name = "${local.namespace}-budget-alerts"

  tags = {
    Project   = "CHAINBREAK"
    Namespace = local.namespace
  }
}

resource "aws_sns_topic_policy" "budget_alerts" {
  count = var.enable_budget_alarm ? 1 : 0

  arn = aws_sns_topic.budget_alerts[0].arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowBudgetsPublish"
      Effect    = "Allow"
      Principal = { Service = "budgets.amazonaws.com" }
      Action    = "sns:Publish"
      Resource  = aws_sns_topic.budget_alerts[0].arn
    }]
  })
}

resource "aws_budgets_budget" "guardrail" {
  count = var.enable_budget_alarm ? 1 : 0

  depends_on = [aws_sns_topic_policy.budget_alerts]

  name              = "${local.namespace}-budget"
  budget_type       = "COST"
  limit_amount      = tostring(var.budget_limit_usd)
  limit_unit        = "USD"
  time_unit         = "MONTHLY"
  time_period_start = "2024-01-01_00:00"

  tags = {
    Project   = "CHAINBREAK"
    Namespace = local.namespace
  }

  # Keep this block unconditional whenever the budget exists. The SNS topic is
  # the durable guard subscriber; the operator email is an additional
  # subscriber when configured. A conditional dynamic block previously allowed
  # the budget to be created without any notification in AWS.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.budget_notification_email != "" ? [var.budget_notification_email] : []
    subscriber_sns_topic_arns  = [aws_sns_topic.budget_alerts[0].arn]
  }
}
