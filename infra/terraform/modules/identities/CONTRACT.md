# Module contract: `identities`

Bootstrap, principal, and agent roles with their trust and permission policies.
Implementation is milestone M9. This is the module where a mistake has the largest blast
radius, so its rules are the strictest.

## Required inputs

| Variable | Type | Description |
|---|---|---|
| `namespace` | `string` | From `benchmark-account` |
| `external_id` | `string` | From `benchmark-account` |
| `operator_principal_arns` | `list(string)` | Who may assume `bootstrap` and `principal` |
| `agent_count` | `number` | Default `6`; roles `agent-a` .. `agent-f` |
| `resource_arns` | `object` | Bucket, table, function, queue ARNs from `resources` |
| `max_session_duration` | `number` | Default `3600` |
| `enable_negative_controls` | `bool` | Default `false` |

## Required outputs

`bootstrap_role_arn`, `principal_role_arn`, `agent_a_role_arn` … `agent_f_role_arn`, and
when `enable_negative_controls`: `agent_b_expansion_role_arn`,
`agent_b_survival_role_arn`, `agent_c_nonmonotone_role_arn`.

## Identity rules

**Bootstrap (`cb-{ns}-bootstrap`)** — may write markers, read policy state, and mutate
agent-role inline policies. It is deliberately **not a node in any authorization graph**:
an identity that can rewrite policy must never be a measurement subject, because its own
probe results would then be meaningless. Its policy is scoped by a condition on
`aws:ResourceTag/Namespace` and by explicit role-ARN lists for IAM actions.

**Principal (`cb-{ns}-principal`)** — the graph root. Holds the union of capabilities any
scenario needs. **Must not hold any `iam:*` mutation permission.**

**Agents (`cb-{ns}-agent-{a..f}`)** — the measurement subjects. Each holds the maximal
capability set its scenarios require; attenuation is applied at runtime by session policies,
not by provisioning six differently-scoped roles.

## Trust policy rules

Each agent role trusts only its designated predecessor plus `bootstrap`, with:

```
Condition:
  StringEquals: { "sts:ExternalId": "<external_id>" }
  StringLike:   { "sts:RoleSessionName": "cb-<ns>-*" }
```

The `RoleSessionName` condition makes every benchmark session identifiable in CloudTrail by
name, which is what makes provider-side corroboration possible at all.

## Hard rules

1. No `Resource: "*"` anywhere except a statement whose only action is
   `sts:GetCallerIdentity`.
2. No `iam:*` on the principal or on any agent role.
3. `bootstrap` may target only roles whose ARN matches `arn:aws:iam::<account>:role/cb-<ns>-agent-*`.
   It must **not** be able to mutate itself or the principal (SI-12 is enforced in code as
   well; this is defense in depth).
4. Negative-control roles exist only when `enable_negative_controls = true`, and their names
   contain the defect (`-expansion`, `-survival`, `-nonmonotone`) so an operator reading the
   console sees what they are.

## Verification

```
terraform plan | grep -c '"Resource": "\*"'     # only the GetCallerIdentity statement
aws iam simulate-principal-policy ...            # bootstrap cannot mutate principal
```
