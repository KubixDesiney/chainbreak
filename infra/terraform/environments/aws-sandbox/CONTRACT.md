# Environment contract: `aws-sandbox`

The real benchmark environment. Composes every module and exposes the output set the
Python adapter's preflight check P5 requires. Implementation is milestone M9.

## Composition order

`benchmark-account` → `resources` → `identities` → `delegation` → `observability`.
Identity policies reference resource ARNs; delegation policies reference both.

## Required outputs (stable interface)

```
namespace  account_id  region  external_id  infrastructure_fingerprint
bootstrap_role_arn  principal_role_arn
agent_a_role_arn .. agent_f_role_arn
objectstore_bucket  objectstore_marker_key  objectstore_marker_sha256
keyvalue_table  keyvalue_marker_pk  keyvalue_marker_sha256
function_name  queue_url
capability_ceiling
```

Plus, when `enable_negative_controls`: `agent_b_expansion_role_arn`,
`agent_b_survival_role_arn`, `agent_c_nonmonotone_role_arn`.

Adding an output is a minor change. Renaming or removing one is breaking and requires an
`infrastructure_profile` version bump in every scenario that depends on it.

## Provider configuration

```hcl
provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "CHAINBREAK"
      Environment = "benchmark"
      Namespace   = local.namespace
      ManagedBy   = "terraform"
      AutoDelete  = "true"
    }
  }
}
```

`default_tags` is how the service-specific, fail-closed cleanup enumerators find orphans,
so it is not optional and must not be overridden per-resource.

Pin `required_version = "~> 1.7"` and `hashicorp/aws ~> 5.0` in `versions.tf`, and commit
`.terraform.lock.hcl` (the *lock* file is committed; `.terraform/` and state are not).

## Destroy contract

`terraform destroy` must succeed with zero manual steps, and a second `destroy` must be a
clean no-op. Verified by `tests/aws/test_cleanup_contract.py` in the e2e layer, followed by
`chainbreak infra verify-clean`, which fail-closed enumerates every provisioned service,
including IAM roles and policies, using exact `Project=CHAINBREAK` and namespace tags.
"Destroy succeeded" is verified, never assumed.
