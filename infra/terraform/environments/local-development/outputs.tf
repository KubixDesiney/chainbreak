# The stable interface AWS_PROVIDER_SPEC section 8 and this environment's
# own CONTRACT.md require. Adding an output is a minor change; renaming or
# removing one is breaking and requires an infrastructure_profile version
# bump in every scenario that depends on it.

output "namespace" {
  value = module.benchmark_account.namespace
}

output "account_id" {
  value = module.benchmark_account.account_id
}

output "region" {
  value = module.benchmark_account.region
}

output "external_id" {
  value = module.benchmark_account.external_id
}

output "infrastructure_fingerprint" {
  value = module.benchmark_account.infrastructure_fingerprint
}

output "bootstrap_role_arn" {
  value = module.identities.bootstrap_role_arn
}

output "principal_role_arn" {
  value = module.identities.principal_role_arn
}

output "agent_a_role_arn" {
  value = module.identities.agent_a_role_arn
}

output "agent_b_role_arn" {
  value = module.identities.agent_b_role_arn
}

output "agent_c_role_arn" {
  value = module.identities.agent_c_role_arn
}

output "agent_d_role_arn" {
  value = module.identities.agent_d_role_arn
}

output "agent_e_role_arn" {
  value = module.identities.agent_e_role_arn
}

output "agent_f_role_arn" {
  value = module.identities.agent_f_role_arn
}

output "agent_b_expansion_role_arn" {
  description = "Only set when enable_negative_controls = true."
  value       = module.identities.agent_b_expansion_role_arn
}

output "agent_b_survival_role_arn" {
  description = "Only set when enable_negative_controls = true."
  value       = module.identities.agent_b_survival_role_arn
}

output "agent_c_nonmonotone_role_arn" {
  description = "Only set when enable_negative_controls = true."
  value       = module.identities.agent_c_nonmonotone_role_arn
}

output "objectstore_bucket" {
  value = module.resources.objectstore_bucket
}

output "objectstore_marker_key" {
  value = module.resources.objectstore_marker_key
}

output "objectstore_marker_sha256" {
  value = module.resources.objectstore_marker_sha256
}

output "keyvalue_table" {
  value = module.resources.keyvalue_table
}

output "keyvalue_marker_pk" {
  value = module.resources.keyvalue_marker_pk
}

output "keyvalue_marker_sha256" {
  value = module.resources.keyvalue_marker_sha256
}

output "function_name" {
  value = module.resources.function_name
}

output "queue_url" {
  value = module.resources.queue_url
}

output "capability_ceiling" {
  value = module.delegation.capability_ceiling
}
