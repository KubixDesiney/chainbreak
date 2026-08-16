# M5 — Provider Protocol and the deterministic fake laboratory

## Purpose
Define the `ProviderAdapter` Protocol, ship the shared contract test suite, and build a fake
provider that is a real authorization engine — not a stub. This is the milestone that makes
every subsequent analysis milestone developable offline against known ground truth.

## Dependencies
M3, M4.

## Required components
`providers/base/protocol.py`, `providers/base/types.py` (`DelegationRequest/Result`,
`ProbeRequest/Result`, `PolicyMutation`, `PreflightReport`, `EnvironmentDescriptor`),
`providers/base/namespace.py` (`assert_namespace`), `providers/fake/` (engine, policy
evaluator, sessions, bindings, probes, consistency model), and the contract suite.

## Files expected
```
src/chainbreak/providers/base/{protocol,types,namespace,contract.py}
src/chainbreak/providers/fake/{adapter,engine,policy,session,bindings,probes,consistency}.py
tests/integration/test_provider_contract.py
tests/unit/{test_namespace_guard,test_fake_policy_engine,test_fake_consistency}.py
```

## Functional requirements
- F1 Protocol: `preflight`, `resolve_capability`, `describe_environment`, `delegate`,
  `probe`, `apply_policy_mutation`, `snapshot_policy_state`.
- F2 Fake policy evaluator implements **explicit deny > explicit allow > implicit deny**
  across identity policy, session policy (intersection semantics), and resource policy.
- F3 Credential lifetimes, expiry, and a configurable chained-role duration cap so
  `LIFETIME_CAPPED` is exercisable offline.
- F4 Injectable consistency model: `propagation_delay_ms`, jitter, and an oscillation mode
  that produces a `NON_MONOTONIC_TRANSITION`.
- F5 Fault injection: `transient_error_rate`, `clock_skew_ms`, `throttle_after_n_calls`.
- F6 Fully seeded: same seed ⇒ identical run, byte-for-byte, on any machine.
- F7 Bindings for all 10 capabilities, with a probe per `ProbeKind`.
- F8 Fake profiles: `deterministic` (no faults), `eventual` (2 s propagation), `hostile`
  (faults + skew + oscillation).

## Non-functional requirements
A full scenario against the fake completes in under 5 s. No sleeping in wall-clock time —
the fake advances a virtual clock so a 120 s deferral test runs instantly, while the
*measurement* code still uses real monotonic time against that clock abstraction.

## Security requirements
- S1 SI-2: `assert_namespace` is called by every probe, mutation and delegation. The fake
  refuses out-of-namespace targets exactly as AWS will.
- S2 The fake issues `SecretMaterial`-wrapped fake credentials so the secret-handling path is
  exercised in CI, not only under AWS.
- S3 The fake must never be selectable when `--provider aws` was requested and preflight
  failed — no silent fallback.

## Tests
The **contract suite** is the deliverable that matters. It must cover: preflight rejects a
wrong account; out-of-namespace target refused before the call; each capability classifies
allow and deny correctly; delegation returns metadata with no secret; mutation returns a
confirmed receipt; requested-vs-granted lifetime reported; snapshot returns stable
fingerprints. Both adapters run the shared behavioral assertions; providers with fixed
provisioned identities supply setup hooks rather than inventing identities that do not exist.

## Negative controls
Configure the fake to grant a capability the scenario does not intend; assert the eventual
analysis (M7) reports `AUTHORITY_EXPANSION`. Set `propagation_delay_ms = 2000`; assert the
measured transition window contains 2000 ms. Set oscillation; assert
`NON_MONOTONIC_TRANSITION` is flagged rather than smoothed.

## Acceptance criteria
1. The fake adapter passes the full contract suite.
2. Every one of the 10 capabilities has a working fake binding and probe.
3. Same seed ⇒ identical evidence, verified by hashing two runs' observation streams.
4. All three fake profiles run all 12 scenarios without crashing.
5. Coverage ≥ 90% on `providers/base/` and `providers/fake/`.

## Verification commands
```bash
pytest -m integration tests/integration/test_provider_contract.py -q
chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake --seed 1729
chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake --seed 1729   # identical
pytest -m unit tests/unit/test_fake_policy_engine.py -q
```

## Definition of done
Acceptance criteria met; ARCHITECTURE §3.9 updated if the fake's capabilities changed;
`PROJECT_STATUS.md` updated.

## Out of scope
AWS. Terraform. Evidence writing beyond what the contract suite needs (M6).

## Risks
A fake that is too permissive makes CI green while AWS fails. Mitigate by implementing real
deny-precedence and intersection semantics, and by keeping the contract suite adapter-agnostic
— never add a branch on `adapter.name`.
