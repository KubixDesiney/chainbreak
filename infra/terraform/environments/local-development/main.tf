# LocalStack-compatible variant validating Terraform *structure* only --
# module composition, output shapes, variable wiring. Never IAM semantics
# (LocalStack's policy evaluation is an approximation). See CONTRACT.md.
#
# Identical composition order to aws-sandbox: benchmark-account -> resources
# -> identities -> delegation -> observability.

locals {
  endpoints = {
    sts            = var.localstack_endpoint
    iam            = var.localstack_endpoint
    s3             = var.localstack_endpoint
    dynamodb       = var.localstack_endpoint
    lambda         = var.localstack_endpoint
    sqs            = var.localstack_endpoint
    cloudwatch     = var.localstack_endpoint
    cloudwatchlogs = var.localstack_endpoint
    cloudtrail     = var.localstack_endpoint
  }

  # Same formula as modules/benchmark-account and aws-sandbox's own root
  # module -- see aws-sandbox/main.tf's comment for why the provider's
  # default_tags cannot simply reference module.benchmark_account.namespace.
  namespace = "cb-${substr(sha1("${var.expected_account_id}${terraform.workspace}${var.namespace_salt}"), 0, 8)}"
}

provider "aws" {
  region                      = var.region
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  default_tags {
    tags = {
      Project     = "CHAINBREAK"
      Environment = "benchmark"
      Namespace   = local.namespace
      ManagedBy   = "terraform"
      AutoDelete  = "true"
    }
  }

  endpoints {
    sts            = local.endpoints.sts
    iam            = local.endpoints.iam
    s3             = local.endpoints.s3
    dynamodb       = local.endpoints.dynamodb
    lambda         = local.endpoints.lambda
    sqs            = local.endpoints.sqs
    cloudwatch     = local.endpoints.cloudwatch
    cloudwatchlogs = local.endpoints.cloudwatchlogs
    cloudtrail     = local.endpoints.cloudtrail
  }
}

module "benchmark_account" {
  source = "../../modules/benchmark-account"

  expected_account_id       = var.expected_account_id
  namespace_salt            = var.namespace_salt
  budget_notification_email = var.budget_notification_email
  enable_negative_controls  = var.enable_negative_controls
  # Budgets is unsupported (and meaningless) against LocalStack.
  enable_budget_alarm = false
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

  depends_on = [module.identities]
}

module "observability" {
  source = "../../modules/observability"

  namespace          = module.benchmark_account.namespace
  enable_cloudtrail  = var.enable_cloudtrail
  enable_data_events = var.enable_data_events
}
