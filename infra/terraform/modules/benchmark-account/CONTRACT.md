# Module contract: `benchmark-account`

Account-level guardrails and the namespace that every other module depends on.
Implementation is milestone M9.

## Purpose

Generate the benchmark namespace, verify the account is the intended one, and bound cost.
This module creates nothing an experiment probes; it creates the conditions under which
probing is safe.

## Required inputs

| Variable | Type | Description |
|---|---|---|
| `expected_account_id` | `string` | Must match the caller's account, else fail the plan |
| `namespace_salt` | `string` | Operator-chosen salt so two workspaces cannot collide |
| `budget_limit_usd` | `number` | Default `5`. Budgets alarm threshold |
| `budget_notification_email` | `string` | Where the alarm goes; `""` disables notification only, never the budget |
| `enable_negative_controls` | `bool` | Default `false` |

## Required outputs

| Output | Description |
|---|---|
| `namespace` | `"cb-" + substr(sha1(account_id + workspace + salt), 0, 8)` — stable across applies within a workspace, distinct across workspaces |
| `account_id` | From `aws_caller_identity` |
| `region` | From `aws_region` |
| `external_id` | `"cb-" + namespace`; used in every trust-policy condition |
| `infrastructure_fingerprint` | `"sha256:" + sha256` over the sorted output map, recorded in every evidence bundle — same `sha256:<64 hex chars>` shape as the two marker digests, since `providers/aws/preflight.py::_validate_output_shapes` (P5/P6) checks all three against the same regex |

## Required resources

- `data.aws_caller_identity` + `data.aws_region`.
- A `check` block (or `lifecycle.precondition`) asserting
  `data.aws_caller_identity.current.account_id == var.expected_account_id`. **This must fail
  at plan time, not apply time** — an operator pointed at the wrong account should never
  reach a diff that looks appliable.
- `aws_budgets_budget` with a monthly limit and an 80% forecast alarm.

## Behavioral requirements

- Namespace generation must be deterministic. If it changed between applies, every scenario
  would need recompilation and existing markers would be orphaned.
- The module must not create IAM identities or data resources. Keeping guardrails separate
  from the things they guard means the guardrails can be applied first and reviewed alone.

## Verification

```
terraform plan -var expected_account_id=000000000000   # must FAIL
terraform output namespace                              # must match ^cb-[0-9a-f]{8}$
terraform apply && terraform apply                      # second apply must be a no-op
```
