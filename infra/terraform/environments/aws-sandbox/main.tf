# The real benchmark environment. Composes every module in the order
# identity policies and delegation policies require: benchmark-account ->
# resources -> identities -> delegation -> observability. See CONTRACT.md.

# ---------------------------------------------------------------------------
# Provider default_tags needs the namespace, but the namespace needs a data
# source read through this same provider -- a genuine circularity
# CONTRACT.md's own example snippet doesn't resolve. Broken here with a
# second, alias-only provider configuration carrying no default_tags of its
# own, used solely for the caller-identity lookup that feeds local.namespace.
# Every module below uses the default (unaliased, tagged) provider.
# ---------------------------------------------------------------------------

provider "aws" {
  alias  = "bootstrap"
  region = var.region
}

data "aws_caller_identity" "current" {
  provider = aws.bootstrap
}

locals {
  # Duplicates modules/benchmark-account's own formula exactly, for the one
  # purpose that formula's own module output cannot serve: tagging the
  # provider itself, before any module (including benchmark-account) has
  # been evaluated. module.benchmark_account.namespace -- computed
  # independently, via the now-fully-configured default provider -- is used
  # everywhere else below and is guaranteed to equal this value, since both
  # use the same account id, workspace and salt.
  namespace = "cb-${substr(sha1("${data.aws_caller_identity.current.account_id}${terraform.workspace}${var.namespace_salt}"), 0, 8)}"
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "CHAINBREAK"
      Environment = "benchmark"
      Namespace   = local.namespace
      ManagedBy   = "terraform"
      AutoDelete  = "true"
    }
  }
}

module "benchmark_account" {
  source = "../../modules/benchmark-account"

  expected_account_id       = var.expected_account_id
  namespace_salt            = var.namespace_salt
  budget_limit_usd          = var.budget_limit_usd
  budget_notification_email = var.budget_notification_email
  enable_negative_controls  = var.enable_negative_controls
  enable_budget_alarm       = true
}

module "resources" {
  source = "../../modules/resources"

  namespace           = module.benchmark_account.namespace
  scratch_expiry_days = var.scratch_expiry_days
  log_retention_days  = var.log_retention_days
}

module "identities" {
  source = "../../modules/identities"

  namespace                = module.benchmark_account.namespace
  external_id              = module.benchmark_account.external_id
  operator_principal_arns  = var.operator_principal_arns
  resource_arns            = module.resources.resource_arns
  enable_negative_controls = var.enable_negative_controls
}

module "delegation" {
  source = "../../modules/delegation"

  namespace = module.benchmark_account.namespace
  agent_role_names = [
    for letter in ["a", "b", "c", "d", "e", "f"] :
    "${module.benchmark_account.namespace}-agent-${letter}"
  ]
  resource_arns            = module.resources.resource_arns
  enable_negative_controls = var.enable_negative_controls

  # module.identities must exist (the roles this module attaches policies
  # to) before delegation runs, even though delegation references the role
  # NAMES it derives itself rather than an identities output directly.
  depends_on = [module.identities]
}

module "observability" {
  source = "../../modules/observability"

  namespace          = module.benchmark_account.namespace
  enable_cloudtrail  = var.enable_cloudtrail
  enable_data_events = var.enable_data_events
}
