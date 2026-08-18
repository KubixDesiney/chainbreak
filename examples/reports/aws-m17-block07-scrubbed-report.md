# CHAINBREAK -- run 01M08YHCCBE9E58W0VRQHVYT1C


scenario `revocation-remove-policy` v1.0.0 (revocation) -- provider `aws` (adapter 0.1.0)
status `COMPLETED` -- bundle_root_verified `True`

## Category results

| category | status | coverage | confidence |
|---|---|---|---|
| DELEGATION_INTEGRITY | NOT_MEASURED | -- | -- |
| SCOPE_ATTENUATION | NOT_MEASURED | -- | -- |
| REVOCATION_RESPONSIVENESS | PARTIAL | 1.00 | HIGH |
| AUTHORITY_FRESHNESS | NOT_MEASURED | -- | -- |
| FAILURE_TRANSPARENCY | NOT_MEASURED | -- | -- |
| CREDENTIAL_HYGIENE | CONSISTENT | 1.00 | HIGH |

NOT_MEASURED is not a pass. 4 of 6 categories were not exercised by this scenario.


## Findings

### EXPECTED_BEHAVIOR (INFORMATIONAL, confidence HIGH)

- observation: agent-b returned observed authority matching expected authority in all 2 probed capabilities at phase BASELINE
- expected_state: {"capabilities": ["identity.whoami", "objectstore.read"]}
- observed_state: {"capabilities": ["identity.whoami", "objectstore.read"]}
- security_interpretation: No divergence detected. This is a measurement, not a guarantee.

### EXPECTED_BEHAVIOR (INFORMATIONAL, confidence HIGH)

- observation: agent-b returned observed authority matching expected authority in all 2 probed capabilities at phase FINAL
- expected_state: {"capabilities": ["identity.whoami", "objectstore.read"]}
- observed_state: {"capabilities": ["identity.whoami", "objectstore.read"]}
- security_interpretation: No divergence detected. This is a measurement, not a guarantee.

### NO_TRANSITION_OBSERVED (INFORMATIONAL, confidence HIGH)

- observation: no ALLOWED->denied transition observed for agent-b/objectstore.read within a 70.6s window (603 polls at 500ms)
- expected_state: {}
- observed_state: {"window_length_s": 70.641}
- security_interpretation: An honest negative: the window closed without a transition.


## Limitations

- Single account: real-AWS bundles cover one account; fake-provider bundles use one synthetic account and are apparatus checks.
- Single region: real-AWS bundles cover one region; fake-provider bundles use one synthetic region and are apparatus checks.
- Simple policies: the shipped scenarios exercise a small number of statements per identity, not production-scale policy complexity.
- Deterministic worker: v0.1's task worker is a deterministic, synthetic implementation of the TaskWorker Protocol, not a real agent.
- Small n: trial counts and cross-run sample sizes are both modest (see coverage/confidence per category and n reported with every timing result).
