# CHAINBREAK Infrastructure

Terraform is the **provisioned identity plane**: roles, trust policies, permission
policies, benchmark resources and markers. Runtime STS delegation and controlled policy
mutation are the **delegation plane** and are not expressible here — see
[ARCHITECTURE §7](../../ARCHITECTURE.md#7-where-infrastructure-comes-from) for why the
distinction matters.

**This directory currently contains module *contracts* — the interface each module must
implement — not the implementations.** Implementation is milestone M9. A contract file
tells Claude Code exactly what resources, variables, and outputs are required, so the
implementation is a filling-in exercise rather than a design exercise.

---

## Layout

```
modules/
  benchmark-account/   account guardrails, namespace generation, budget alarm
  identities/          bootstrap, principal, agent-{a..f} roles and policies
  resources/           S3, DynamoDB, Lambda, SQS, markers, lifecycle rules
  delegation/          per-hop permission policies expressing intended capabilities
  observability/       optional CloudTrail and log groups (default off)
environments/
  local-development/   LocalStack-compatible; makes no real AWS calls
  aws-sandbox/         the real benchmark environment
```

Composition order is `benchmark-account → resources → identities → delegation →
observability`, because identity policies reference resource ARNs and delegation policies
reference both.

## Contract with the Python adapter

`preflight` check P5 loads Terraform outputs and aborts if any required output is missing.
The output names in [AWS_PROVIDER_SPEC §8](../../AWS_PROVIDER_SPEC.md#8-terraform-contract)
are a **stable interface**: adding one is a minor change, renaming or removing one is
breaking and requires an `infrastructure_profile` version bump in every scenario that
depends on it.

Scenarios reference infrastructure only by output *name*
(`provider_binding.terraform_output`), never by ARN. That indirection is what lets scenarios
be published without disclosing the operator's environment (T-13).

## Infrastructure profiles

`spec.requires.infrastructure_profile` in a scenario selects a Terraform workspace variant:

| Profile | Contents |
|---|---|
| `standard` | The normal chain: bootstrap, principal, agents a–f, all resources |
| `negative-control-expansion` | Adds `agent_b_expansion_role` with an inline policy granting a capability its hop does not delegate |
| `negative-control-survival` | Adds `agent_b_survival_role` retaining `function.invoke` past a hop that drops it |
| `negative-control-nonmonotone` | Adds `agent_c_nonmonotone_role` granting `keyvalue.write` no ancestor holds |

Negative-control profiles are separate variables (`enable_negative_controls = true`) rather
than separate root modules, so the defective roles live in the same account, same
namespace, and same apply as the roles they validate — a control applied to different
infrastructure proves less ([EXPERIMENT_PROTOCOL §6](../../EXPERIMENT_PROTOCOL.md#6-negative-control-protocol)).

## Safety rules for every module

1. **No `Resource: "*"`** except `sts:GetCallerIdentity`. CI enforces this with a custom
   `checkov`/`tflint` rule; it is not a review convention.
2. **Every policy is namespace-scoped**, by explicit ARN or by a condition on
   `aws:ResourceTag/Namespace`.
3. **`default_tags` on the provider** applies `Project=CHAINBREAK`, `Environment=benchmark`,
   `Namespace`, `ManagedBy=terraform`, `AutoDelete=true` to everything taggable. Cleanup
   operates by tag, so an orphan is always findable.
4. **Destroy must need zero manual steps.** S3 uses `force_destroy = true` (it only ever
   holds markers and scratch); CloudWatch log groups are managed explicitly so Lambda's
   implicit group cannot orphan.
5. **No provisioners, no `local-exec`, no external data sources that execute commands.**
   Terraform here is declarative infrastructure, not a scripting host.
6. **No secrets in variables or outputs.** The external ID is a namespace-derived value,
   not a secret; it is documented as such.

## Cost

Under $0.10 per full suite, dominated by nothing — every service used is within free tier
or fractions of a cent. See [AWS_PROVIDER_SPEC §9](../../AWS_PROVIDER_SPEC.md#9-cost-model).
The real cost risk is forgetting to destroy, which is why the `benchmark-account` module
provisions a Budgets alarm and every storage resource carries a short lifecycle rule.

## Usage

```bash
cd environments/aws-sandbox
cp terraform.tfvars.example terraform.tfvars   # set allowed account, region, salt
terraform init
terraform plan
terraform apply
# ... run experiments ...
terraform destroy
chainbreak infra verify-clean                  # confirm nothing survives, by tag
```

`terraform.tfvars` is gitignored. The example file is not.

## State

Local state is the default and is gitignored. If remote state is used it **must** be an
encrypted backend with restricted access — state contains the full resource inventory
(threat T-04). CI never touches state; the AWS experiment workflow applies and destroys
within a single job.
