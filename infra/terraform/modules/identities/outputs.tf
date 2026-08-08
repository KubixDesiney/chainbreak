output "bootstrap_role_arn" {
  value = aws_iam_role.bootstrap.arn
}

output "principal_role_arn" {
  value = aws_iam_role.principal.arn
}

output "agent_a_role_arn" {
  value = aws_iam_role.agent_a.arn
}

output "agent_b_role_arn" {
  value = aws_iam_role.agent_b.arn
}

output "agent_c_role_arn" {
  value = aws_iam_role.agent_c.arn
}

output "agent_d_role_arn" {
  value = aws_iam_role.agent_d.arn
}

output "agent_e_role_arn" {
  value = aws_iam_role.agent_e.arn
}

output "agent_f_role_arn" {
  value = aws_iam_role.agent_f.arn
}

output "agent_b_expansion_role_arn" {
  description = "Only set when enable_negative_controls = true."
  value       = var.enable_negative_controls ? aws_iam_role.agent_b_expansion[0].arn : null
}

output "agent_b_survival_role_arn" {
  description = "Only set when enable_negative_controls = true."
  value       = var.enable_negative_controls ? aws_iam_role.agent_b_survival[0].arn : null
}

output "agent_c_nonmonotone_role_arn" {
  description = "Only set when enable_negative_controls = true."
  value       = var.enable_negative_controls ? aws_iam_role.agent_c_nonmonotone[0].arn : null
}
