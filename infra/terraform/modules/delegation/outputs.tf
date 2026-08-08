output "policy_arns" {
  description = "Map of agent role name -> its ceiling policy ARN."
  value       = { for i, name in var.agent_role_names : name => aws_iam_policy.ceiling[i].arn }
}

output "capability_ceiling" {
  description = "Map of agent role name -> the capability ids provisioned as its ceiling. Consumed by `chainbreak validate` to cross-check against what scenarios assume."
  value = {
    for i, name in var.agent_role_names : name => concat(
      ["identity.whoami"],
      keys(local.non_delegate_capabilities),
      i + 1 < length(var.agent_role_names) ? ["identity.delegate"] : []
    )
  }
}
