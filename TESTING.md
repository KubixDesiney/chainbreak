# CHAINBREAK Testing Strategy

Four layers, three of which never touch AWS. **Default CI requires no cloud credentials.**

---

## 1. Layers

| Layer | Marker | Needs AWS | Runs in CI | Target runtime | What it proves |
|---|---|---|---|---|---|
| Unit | `unit` | no | every push/PR | < 30 s | Logic is correct in isolation |
| Integration | `integration` | no | every push/PR | < 3 min | Full scenarios execute correctly end-to-end against a known-truth provider |
| AWS sandbox | `aws` | **yes** | manual dispatch only | < 10 min | The adapter matches real IAM/STS behavior |
| End-to-end | `e2e` | **yes** | manual dispatch only | < 30 min | Provision → run → analyze → report → destroy works |

```bash
pytest -m unit                    # fast inner loop
pytest -m "unit or integration"   # what CI runs on every PR
pytest -m aws                     # requires CHAINBREAK_AWS_TEST_ACCOUNT + assumed role
pytest -m e2e                     # billable; provisions and destroys infrastructure
```

The `aws` and `e2e` markers refuse to run unless `CHAINBREAK_ALLOW_AWS_TESTS=1` **and** the
resolved account is in the allowlist. The refusal is a `pytest.skip` with an explanatory
message, so a developer who runs the full suite by accident gets a clear message rather than
a cloud bill.

---

## 2. Unit layer

Pure logic. No filesystem beyond `tmp_path`, no network, no clock (frozen via `freezegun`),
no randomness (seeded).

**Coverage targets by module** — enforced per-module, not globally, because a global 85%
can hide 40% on the module that matters:

| Module | Minimum | Why |
|---|---|---|
| `core/` | 95% | Domain invariants; cheap to test |
| `graph/` | 95% | Divergence algorithms are the analytic core |
| `analysis/` | 95% | Produces the findings |
| `evidence/redaction.py` | **100%** | SI-1; a missed branch is a credential leak |
| `core/safety.py` | **100%** | SI-5 |
| `capabilities/` | 90% | Binding validation |
| `scenarios/` | 90% | Untrusted input parsing |
| `providers/base/` | 90% | Contract definitions |
| `providers/aws/` | 70% | Much of it is thin boto3 wrapping; `moto` covers more in the aws layer |
| `reporting/` | 70% | Rendering |

**Representative unit tests**

- `test_authority_set.py` — set algebra, canonical ordering, hashing stability.
- `test_divergence.py` — table-driven over hand-computed expected/observed pairs, including
  the four drift classes and the `CORRECTED` case that a naive implementation gets wrong.
- `test_first_divergence.py` — branching graphs, unmeasured nodes, single-node chains.
- `test_graph_invariants.py` — G-1…G-5, each with a violating fixture, plus the
  negative-control downgrade path.
- `test_capability_catalog.py` — ID regex, uniqueness, no `DANGEROUS` entries, every
  capability has a `probe_kind`.
- `test_binding_validator.py` — SI-3: an over-broad binding is rejected.
- `test_scenario_schema.py` — every field, every enum, every bound; round-trip
  YAML→model→YAML.
- `test_scenario_safety.py` — SI-11: YAML bombs, python-object tags, embedded ARNs, size caps.
- `test_scenario_compiler.py` — determinism (same input ⇒ same `compiled_hash`), expected
  authority derivation, auto-inserted snapshots, session-policy synthesis size limit.
- `test_outcome_classification.py` — every `OutcomeClass` from a recorded provider response
  fixture, including the S3 403/404 ambiguity and the Lambda `FunctionError` case.
- `test_revocation_math.py` — window computation, non-monotonic transitions, no-transition,
  uncertainty half-width.
- `test_stale_classification.py` — the full classification table including
  `EXPIRED_CREDENTIAL_HONORED`.
- `test_redaction.py` — property-based; see §5.
- `test_safety_gate.py` — SI-5, including introspecting the CLI for a bypass flag.
- `test_preflight_ordering.py` — SI-6, exactly one AWS call before an account-mismatch abort.
- `test_namespace_guard.py` — SI-2, lookalike ARNs.
- `test_mutation_guard.py` — SI-12.
- `test_cost_estimator.py` — SI-8 conservatism.
- `test_evidence_schema.py` — every record validates against its JSON Schema; sealing and
  verification round-trip; tamper detection.
- `test_scoring.py` — category status mapping, min-not-mean confidence, `NOT_MEASURED`
  handling.
- `test_report_language.py` — the forbidden/required language rules from
  [EXPERIMENT_PROTOCOL §7](EXPERIMENT_PROTOCOL.md#7-reporting-language-rules).
- `test_security_invariants.py` — asserts every SI id in SECURITY_MODEL has a test.
- `test_import_boundaries.py` — the dependency rule (ARCH-1); no `boto3` import outside
  `providers/aws/`; no AWS string literals outside `providers/`.

---

## 3. Integration layer — the deterministic laboratory

The fake provider is not a stub. It is a small authorization engine with:

- A real policy evaluation model: explicit deny > explicit allow > implicit deny, evaluated
  across identity policy, session policy (intersection semantics), and resource policy.
- Simulated credential issuance with lifetimes, expiry, and the chained-role duration cap.
- An **injectable consistency model**: `propagation_delay_ms` (with optional jitter and an
  oscillation mode), so revocation timing logic can be tested against a *known* answer.
- Fault injection: `transient_error_rate`, `clock_skew_ms`, `throttle_after_n_calls`.
- A seeded RNG so every run is reproducible.

This is what makes M12–M14 developable and testable without AWS, and it is the reason a
timing bug is caught in CI rather than discovered after a billable experiment.

**Representative integration tests**

- `test_provider_contract.py` — the shared contract suite. Both adapters must pass it. Covers:
  preflight rejects a wrong account; out-of-namespace targets refused; every capability
  probes allow and deny correctly; delegation returns metadata without secrets; mutation
  returns a confirmed receipt; lifetime capping is reported.
- `test_scenario_execution.py` — each of the five families runs end to end and produces a
  sealed, schema-valid bundle.
- `test_known_truth_divergence.py` — the fake provider is configured with a *known*
  authority set that differs from intent; the analysis must produce exactly the expected
  findings, with exactly the expected confidence. This is the differential control (C-9).
- `test_known_truth_timing.py` — fake `propagation_delay_ms = 2000`; the measured
  `transition_window` must contain 2000 ms. Directly validates the timing math.
- `test_negative_controls.py` — every negative control scenario produces its declared
  finding; then, each is deliberately "fixed" and the harness must emit `DETECTOR_FAILURE`.
- `test_duration_abort.py` — SI-7; a stalling provider produces a sealed partial bundle.
- `test_cleanup_contract.py` — SI-4; mutations are reverted; a killed run leaves an
  actionable revert log.
- `test_run_isolation.py` — T-08; concurrent runs do not collide.
- `test_analyze_idempotence.py` — analyzing the same bundle twice yields byte-identical
  findings.
- `test_report_generation.py` — HTML report renders; no unescaped bundle content (T-10).

---

## 4. AWS layer

Opt-in. Two sub-layers:

**`moto`-backed** (`tests/aws/test_adapter_moto.py`) — runs in CI because `moto` needs no
real account. Covers boto3 call shapes, parameter marshalling, and error handling. It does
**not** validate IAM semantics: moto's policy evaluation is an approximation, and treating
it as ground truth would be a serious methodological error. Every moto test carries a
docstring saying so.

**Real-account** (`tests/aws/test_adapter_real.py`, marker `aws`) — the only place real IAM
semantics are validated:

- `test_assume_role_chain_duration_cap` — H7: request 7200 s on a chained hop, assert the
  grant is 3600 s and `LIFETIME_CAPPED` is emitted.
- `test_session_policy_cannot_grant` — H1: session policy allows an action the role lacks;
  assert denial.
- `test_explicit_deny_wins` — deny in the role policy, allow in the session policy.
- `test_denial_message_attribution` — assert the explicit/implicit message shapes the
  classifier depends on still exist. **This test is the canary for AWS changing its error
  message format**, which would silently break `denial_attribution`.
- `test_s3_403_404_ambiguity` — assert the documented behavior the precondition control
  exists to handle.
- `test_marker_precondition_failure` — delete the marker; assert `CONFIGURATION_ERROR`, not
  a wave of denials.
- `test_whoami_never_denied` — the control capability's premise.
- `test_namespace_violation_refused` — attempt a probe against an out-of-namespace ARN;
  assert refusal before the API call.

---

## 5. Redaction testing — the highest-stakes suite

`tests/unit/test_redaction.py` is property-based (Hypothesis-style, or a deterministic
generator if Hypothesis is not adopted):

1. Enumerate every Pydantic model in `core/` by reflection.
2. For each, construct an instance with every string-typed field populated with a synthetic
   secret from a corpus (fake AKIA/ASIA keys, a JWT, a PEM block, a base64 blob, a
   session-token-shaped string).
3. Serialize a full evidence bundle containing it.
4. Assert: either `SecretLeakError` was raised, or zero corpus values appear in any output
   byte.
5. Additionally assert the secret never appears in `repr()`, `str()`, `format()`, an
   exception traceback, or a log record.

New model fields are covered automatically because the test discovers models by reflection.
A contributor who adds a secret-bearing field without handling it fails CI without having to
remember this document exists.

---

## 6. CI pipeline

```yaml
# .github/workflows/ci.yml  (summary; see the file for the pinned version)
jobs:
  lint:      ruff check . && ruff format --check .
  types:     mypy
  boundaries: import-linter (ARCH-1)
  security:  bandit -r src/ ; pip-audit ; custom no-secrets-in-repo scan
  test:      pytest -m "unit or integration" --cov --cov-fail-under-per-module
  schemas:   validate every scenario + every JSON Schema is itself valid
  scenarios: chainbreak scenario validate on every file in scenarios/ (offline mode)
  terraform: terraform fmt -check ; terraform validate ; tflint ; checkov
  docs:      link checker ; mermaid syntax check ; forbidden-language lint on templates
```

Separate, manually dispatched workflow `aws-experiment.yml`: `workflow_dispatch` only,
environment `aws-benchmark` with required reviewers, OIDC role assumption (no static keys),
never triggered by `pull_request`. It runs `pytest -m aws` and, optionally, a full
experiment with `infra apply` → `run` → `analyze` → `verify-clean` → `destroy`, with
`destroy` in an `always()` step.

---

## 7. Fixtures

`tests/fixtures/` holds:

- `provider_responses/` — recorded, redacted real AWS responses (success, explicit deny,
  implicit deny, throttle, 403-on-missing-key, Lambda FunctionError). These are the ground
  truth for `test_outcome_classification.py`. Each is accompanied by a `.provenance.json`
  recording when and how it was captured, so a maintainer can tell whether it is stale.
- `scenarios/` — valid, and deliberately invalid, scenario documents (one per validation
  failure mode).
- `bundles/` — golden evidence bundles for analysis regression, plus a tampered bundle and
  a malicious bundle (T-10).
- `bad_bindings.py` — over-broad bindings that must be rejected.

---

## 8. What is deliberately not tested

- **AWS's own correctness.** Not our subject.
- **moto's policy engine.** Used for call shapes only.
- **Report aesthetics.** Rendering is smoke-tested; visual design is not.
- **Performance beyond the run-duration ceiling.** Throughput is not a goal.

---

## 9. Definition of a passing build

`ruff` clean · `mypy --strict` clean · import boundaries clean · `bandit` and `pip-audit`
clean · `pytest -m "unit or integration"` green · per-module coverage thresholds met ·
100% coverage on `redaction.py` and `safety.py` · every scenario validates · every JSON
Schema valid · Terraform formatted, valid, and policy-scanned · docs links resolve ·
forbidden-language lint clean.

A build that is green with a `DETECTOR_FAILURE` in the negative-control integration suite is
**not** passing. That test is a merge gate.
