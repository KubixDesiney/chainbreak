output "namespace" {
  description = "The benchmark namespace, matching ^cb-[0-9a-f]{8}$."
  value       = local.namespace
}

output "account_id" {
  description = "The resolved caller account id, already verified to match expected_account_id."
  value       = data.aws_caller_identity.current.account_id
}

output "region" {
  description = "The provider's configured region."
  value       = data.aws_region.current.name
}

output "external_id" {
  description = "Used in every trust-policy condition. Not a secret -- a namespace-derived value."
  value       = local.external_id
}

output "infrastructure_fingerprint" {
  description = "sha256 over this module's sorted output map. Recorded in every evidence bundle."
  value       = local.infrastructure_fingerprint
}
