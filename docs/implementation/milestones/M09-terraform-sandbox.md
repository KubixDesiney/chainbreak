# M9 — Terraform AWS sandbox

## Purpose
Implement the five Terraform modules and two environments to their contracts, and wire the
`chainbreak infra` commands.

## Dependencies
M8. **Requires an operator-owned AWS account.**

## Existing work to preserve
`infra/terraform/README.md`, `modules/*/CONTRACT.md`, `environments/*/CONTRACT.md`,
`environments/aws-sandbox/terraform.tfvars.example`. These are the specification — implement
to them; do not restate or replace them.

## Required components
Each module's `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`; both environments;
`cli/infra.py` wrapping plan/apply/destroy/status/verify-clean.

## Files expected
```
infra/terraform/modules/{benchmark-account,identities,resources,delegation,observability}/{main,variables,outputs,versions}.tf
infra/terraform/environments/{aws-sandbox,local-development}/{main,variables,outputs,versions}.tf
src/chainbreak/cli/infra.py
tests/aws/{test_terraform_outputs,test_cleanup_contract}.py
```

## Functional requirements
- F1 Every module implements its CONTRACT.md exactly, including the full output set.
- F2 `benchmark-account` fails at **plan** time on an account mismatch, not apply time.
- F3 Namespace generation is deterministic across applies within a workspace.
- F4 `chainbreak infra apply` runs Terraform, captures outputs, and writes an
  `infrastructure_fingerprint` the adapter reads at preflight P5.
- F5 `chainbreak infra verify-clean` fail-closed enumerates every provisioned service,
  including IAM roles and policies, and requires exact `Project=CHAINBREAK` plus the
  Terraform namespace; unknown or failed enumeration is unsafe.
- F6 `enable_negative_controls` provisions the three deliberately-defective roles.
- F7 `terraform destroy` succeeds with zero manual steps; a second destroy is a clean no-op.

## Non-functional requirements
Apply under 3 minutes; destroy under 2. Cost per suite under $0.10.

## Security requirements
- S1 No `Resource: "*"` except a statement whose only action is `sts:GetCallerIdentity`,
  enforced by a `checkov`/`tflint` custom rule in CI.
- S2 Bootstrap cannot mutate itself or the principal — verified with
  `iam:SimulatePrincipalPolicy` in a test.
- S3 No provisioners, no `local-exec`, no command-executing data sources.
- S4 `default_tags` applied at the provider so native service enumerators can verify exact
  cleanup tags, including on IAM roles and customer-managed policies.
- S5 State gitignored; remote state, if used, encrypted with restricted access.

## Tests
`test_terraform_outputs.py` asserts every documented output exists and matches its expected
shape (namespace regex, ARN shape, digest format). `test_cleanup_contract.py` (marker `e2e`)
applies, destroys, destroys again, then runs `verify-clean`.

## Negative controls
`terraform plan -var expected_account_id=000000000000` must fail at plan. Apply, then delete
the S3 marker out of band and run `chainbreak validate` — precondition P8 must fail with a
clear message. Apply twice; the second must be a no-op (`0 to add, 0 to change, 0 to destroy`).

## Acceptance criteria
1. `terraform validate` and `fmt -check` clean for every module and environment.
2. `checkov`/`tflint` clean, including the no-wildcard rule.
3. Apply → all preflight checks pass → destroy → `verify-clean` reports nothing remaining.
4. `enable_negative_controls = true` provisions the three defective roles and the
   corresponding outputs appear.
5. Second apply is a no-op; second destroy is a no-op.

## Verification commands
```bash
terraform -chdir=infra/terraform/environments/aws-sandbox fmt -check -recursive
terraform -chdir=infra/terraform/environments/aws-sandbox validate
tflint --chdir infra/terraform && checkov -d infra/terraform
chainbreak infra plan aws-sandbox && chainbreak infra apply aws-sandbox
chainbreak validate                       # preflight P1-P11
chainbreak infra destroy aws-sandbox && chainbreak infra verify-clean --namespace cb-<namespace>
```

## Definition of done
Acceptance criteria met **with real output pasted**, including a `verify-clean` run showing
zero remaining resources; `PROJECT_STATUS.md` records the apply/destroy cycle actually
performed.

## Out of scope
Running experiments (M17). Multi-account. Remote state backends beyond documentation.

## Risks
A destroy that fails on a non-empty bucket or an orphaned Lambda log group — both are
explicitly handled in the contracts (`force_destroy`, explicit log group) and both must be
tested by actually destroying, not by reading the plan.
