# CHAINBREAK -- run 01M0A5WS8Q912NJSP0FEH1DWSK


scenario `scope-attenuation-basic` v1.0.0 (scope-attenuation) -- provider `aws` (adapter 0.1.0)
status `COMPLETED` -- bundle_root_verified `False`
> **bundle_root_verified: false -- integrity check failed.**

## Category results

| category | status | coverage | confidence |
|---|---|---|---|
| DELEGATION_INTEGRITY | CONSISTENT | 1.00 | HIGH |
| SCOPE_ATTENUATION | DIVERGENT | 1.00 | HIGH |
| REVOCATION_RESPONSIVENESS | NOT_MEASURED | -- | -- |
| AUTHORITY_FRESHNESS | NOT_MEASURED | -- | -- |
| FAILURE_TRANSPARENCY | NOT_MEASURED | -- | -- |
| CREDENTIAL_HYGIENE | CONSISTENT | 1.00 | HIGH |

NOT_MEASURED is not a pass. 3 of 6 categories were not exercised by this scenario.


## Findings

### AUTHORITY_NARROWING (INFORMATIONAL, confidence HIGH)

- observation: principal did not return ALLOWED for expected capabilities function.invoke, keyvalue.read, keyvalue.write, objectstore.list, objectstore.read, objectstore.write at phase BASELINE
- expected_state: {"capabilities": ["function.invoke", "identity.delegate", "identity.whoami", "keyvalue.read", "keyvalue.write", "objectstore.list", "objectstore.read", "objectstore.write"]}
- observed_state: {"capabilities": ["identity.delegate", "identity.whoami"]}
- security_interpretation: Authority expected by the scenario was not observed. This is a narrowing, not necessarily a defect -- it may be a legitimate, tighter-than-intended grant.

### AUTHORITY_EXPANSION (REVIEW, confidence HIGH)

- observation: agent-a returned ALLOWED for keyvalue.write, objectstore.list in all trials at phase POST_DELEGATION
- expected_state: {"capabilities": ["function.invoke", "identity.delegate", "identity.whoami", "keyvalue.read", "objectstore.read", "objectstore.write"]}
- observed_state: {"capabilities": ["function.invoke", "identity.delegate", "identity.whoami", "keyvalue.read", "keyvalue.write", "objectstore.list", "objectstore.read", "objectstore.write"]}
- security_interpretation: agent-a holds authority its delegation chain did not intend it to hold. Determine whether the capability originates from the identity's own permission policy rather than the delegated scope.

### DELEGATION_DRIFT (REVIEW, confidence HIGH)

- observation: agent-a holds unexpected authority keyvalue.write, objectstore.list (ORIGINATED)
- expected_state: {"capabilities": ["function.invoke", "identity.delegate", "identity.whoami", "keyvalue.read", "objectstore.read", "objectstore.write"]}
- observed_state: {"capabilities": ["function.invoke", "identity.delegate", "identity.whoami", "keyvalue.read", "keyvalue.write", "objectstore.list", "objectstore.read", "objectstore.write"]}
- security_interpretation: Divergence at an upstream hop propagated to agent-a. Remediation belongs at the origin hop, not here.

### EXPECTED_BEHAVIOR (INFORMATIONAL, confidence HIGH)

- observation: agent-b returned observed authority matching expected authority in all 8 probed capabilities at phase POST_DELEGATION
- expected_state: {"capabilities": ["identity.whoami", "objectstore.read"]}
- observed_state: {"capabilities": ["identity.whoami", "objectstore.read"]}
- security_interpretation: No divergence detected. This is a measurement, not a guarantee.


## Limitations

- Single account: real-AWS bundles cover one account; fake-provider bundles use one synthetic account and are apparatus checks.
- Single region: real-AWS bundles cover one region; fake-provider bundles use one synthetic region and are apparatus checks.
- Simple policies: the shipped scenarios exercise a small number of statements per identity, not production-scale policy complexity.
- Deterministic worker: v0.1's task worker is a deterministic, synthetic implementation of the TaskWorker Protocol, not a real agent.
- Small n: trial counts and cross-run sample sizes are both modest (see coverage/confidence per category and n reported with every timing result).
