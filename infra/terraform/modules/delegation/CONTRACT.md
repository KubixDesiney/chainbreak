# Module contract: `delegation`

Per-hop permission policies expressing each agent's *provisioned* capability ceiling.
Implementation is milestone M9.

## Purpose and boundary

This module provisions what each agent role *can* do at most. Runtime session policies then
*narrow* that at delegation time. Both layers are needed:

- The provisioned policy is the ceiling. A session policy cannot grant beyond it (session
  policies intersect), so the ceiling is what makes `SESSION_POLICY_SCOPED` a meaningful
  attenuation mechanism to test.
- The session policy is the attenuation under measurement, and is synthesized at runtime by
  the adapter from capability bindings — never hand-written per scenario.

Getting this backwards (provisioning narrow roles and calling that "attenuation") would make
the scope-attenuation family measure Terraform rather than STS.

## Required inputs

`namespace`, `agent_role_names`, `resource_arns`, `capability_action_map` (the capability →
action/resource mapping, passed in so Terraform and the Python bindings cannot drift
silently), `enable_negative_controls`.

## Required outputs

`policy_arns` (map role → policy ARN) and `capability_ceiling` (map role → capability list),
the latter consumed by `chainbreak validate` to cross-check the provisioned ceiling against
what scenarios assume.

## Requirements

1. Every statement is scoped to a namespaced ARN. `objectstore.write` additionally carries a
   condition on `s3:prefix` restricted to `cb-{ns}/scratch/*`; `keyvalue.write` carries
   `dynamodb:LeadingKeys` restricted to `cb-scratch#*`. Two independent controls, because
   prefix confinement is what keeps write probes from touching markers.
2. `identity.delegate` is expressed as `sts:AssumeRole` on the *specific* next-hop role ARN,
   never a wildcard over `role/cb-{ns}-*`.
3. Negative-control policies exist only under `enable_negative_controls` and each carries a
   `Sid` naming the defect, e.g. `CbNegativeControlExpansionKeyvalueRead`, so the injected
   defect is visible in the console and in a policy diff.

## Verification

`terraform output capability_ceiling` must equal the union of `intended_capabilities` across
all scenarios targeting that role. `chainbreak validate` performs this comparison and fails
on drift — a ceiling narrower than a scenario expects would produce false
`AUTHORITY_NARROWING` findings, which is exactly the kind of measurement error the benchmark
exists to avoid.
