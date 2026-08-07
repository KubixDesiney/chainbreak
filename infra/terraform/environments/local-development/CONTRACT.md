# Environment contract: `local-development`

A LocalStack-compatible variant that makes **no real AWS calls**, so contributors can
exercise `terraform plan`, module wiring and output shapes without an account.
Implementation is milestone M9.

## Purpose and honest limits

This environment exists to validate *Terraform structure*: that modules compose, that every
required output is produced, that variable types line up. It does **not** validate IAM
semantics.

LocalStack's IAM policy evaluation is an approximation. Treating a LocalStack result as
evidence about authorization behavior would be a serious methodological error — the same
error as treating `moto` results as ground truth in the test suite. Every file in this
directory carries that warning, and the CHAINBREAK adapter refuses to run a scenario against
a LocalStack endpoint unless `--provider fake` is also set, which stamps the resulting
report as non-measurement output.

For offline work that *does* validate authorization logic, use the deterministic fake
provider (`chainbreak run --provider fake`), which has a real policy-evaluation model and
known ground truth. That is the supported offline path; this environment is only for
Terraform mechanics.

## Requirements

- Identical module composition and identical output names to `aws-sandbox`, so a structural
  change that breaks the real environment breaks here first.
- `endpoints {}` block pointing at LocalStack; `skip_credentials_validation`,
  `skip_metadata_api_check`, `skip_requesting_account_id` all `true`.
- `expected_account_id` defaults to LocalStack's `000000000000`.
- No Budgets resource (unsupported and meaningless locally).
