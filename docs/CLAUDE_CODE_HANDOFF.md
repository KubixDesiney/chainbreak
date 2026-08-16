# Claude Code Implementation Handoff

Read this before implementing any milestone. It states what must not change, how the pieces
fit, and the conventions the repository already follows. Then use the ready-to-copy prompt
for your assigned milestone.

**One milestone per session.** There is no "build all of CHAINBREAK" prompt, and creating one
would defeat the purpose of the milestone structure.

---

## Part 1 — What already exists

Do not rewrite these. They are working, tested, and authoritative.

| Path | Status |
|---|---|
| All root `*.md` documents | Complete specifications |
| `docs/adr/ADR-001..014` | Accepted decisions |
| `src/chainbreak/core/{enums,errors,ids,secrets,models}.py` | Implemented, 41 passing tests |
| `src/chainbreak/capabilities/{catalog.yaml,loader.py}` | Implemented; 10 capabilities, v1.0.0 |
| `src/chainbreak/scenarios/{schema,safety,export_schema}.py` | Implemented; v1alpha1 |
| `schemas/*.json`, `schemas/run-index.sql` | Generated/validated |
| `scenarios/**` (12 files) | All validate; 6 positive, 6 negative controls |
| `tests/unit/test_domain_contract.py`, `tests/scenarios/test_scenario_corpus.py` | Passing |
| `infra/terraform/**/CONTRACT.md` | Specifications for M9 |

Verify before starting:

```bash
pip install -e ".[dev]"
pytest -m unit -q            # expect: all passing
```

If something here is genuinely wrong, **stop and say so** rather than working around it.
A specification bug is worth fixing properly; a workaround buried in an implementation is not.

---

## Part 2 — Invariants that must not be redesigned

Changing any of these requires an ADR, which requires stopping and asking. They are not
style preferences; each exists because the alternative produces wrong measurements or leaks
credentials.

### Architecture

**ARCH-1 — layer dependencies point one way.** `core/` imports nothing from CHAINBREAK.
`graph/` imports only `core/`. Nothing outside `providers/aws/` imports `boto3`. Nothing
outside `providers/` names an AWS service, action or ARN. Enforced by
`tests/unit/test_import_boundaries.py`.

**PROV-1 — adapters may narrow, never broaden.** A binding declares its complete action set;
the executor asserts invoked operations are a subset.

**INFRA-1 — two planes.** Terraform provisions identities and resources. Runtime does STS
delegation and mutations on *agent* roles only. CHAINBREAK never creates an IAM role or
attaches a managed policy at runtime.

### Model

**AUTH-1 — observed authority contains only `ALLOWED` cells.** Every other outcome is a
denial (excluded) or an exclusion (recorded with a reason). There is no inference, and no
third option.

**G-1…G-5 — graph invariants.** Acyclic, single root, monotone intent, capability closure,
bounded depth. Negative controls downgrade a *named* invariant for one scenario; nothing
disables them globally.

**CAP-1 — an unresolvable capability is a compile error.** Never a silent skip. A silently
skipped capability lets a scenario appear to pass without testing the thing it exists to test.

**ADR-012 — unanimity.** A cell is `ALLOWED` only if every trial was `ALLOWED`. Mixed results
are `INDETERMINATE` with the trial vector recorded. Do not implement majority voting.

**Timing has no scalar form.** `Interval(low, point, high)` everywhere; the SQLite
`measurements` table has no scalar column. If you find yourself wanting to return a float,
that is the design telling you something.

### Security

**SI-1 — secrets are unrenderable.** `SecretMaterial` raises on `str`, `repr`, `format`,
`bytes`, pickle and Pydantic serialization. `redact()` **raises** on a detected secret; it
does not sanitize and continue. `.reveal()` is called in exactly two places — a grep for it
is a complete audit.

**SI-2 — namespace assertion before every call.** Probe, mutation, delegation. Plus an
independent botocore hook in the AWS adapter.

**SI-5/SI-6 — the SafetyGate cannot be bypassed.** There is no `--force`, `--skip-preflight`,
or equivalent, and `test_cli_surface.py` fails if one is added. `GetCallerIdentity` is the
first AWS call and, on account mismatch, the only one.

**SI-11 — scenarios are data.** `yaml.safe_load` via a restricted loader; no ARNs, account
IDs or regions in a scenario document.

**SI-12 — the benchmark cannot revoke its own observability.** Mutations refuse `bootstrap`
and `principal`.

**EV-1 — no secret material in evidence.** Not the key, not a truncation, not an encrypted
copy.

### Method

**ADR-006 — observation ≠ conclusion.** `Finding.observation` and
`Finding.security_interpretation` are separate fields, rendered under separate headings.
Never merge them into prose.

**ADR-010 — no composite score.** Six independent category results. `CONSISTENT` describes a
measurement, not a grade. `NOT_MEASURED` is rendered with the literal sentence
"NOT_MEASURED is not a pass."

**ADR-009 — probing is ground truth.** Policy simulation corroborates; it never contributes
to `ObservedAuthority`.

**ADR-011 — timing-sensitive scenarios are serial.** Concurrency destroys the measurement.

**Prefer INCONCLUSIVE over a guess.** If a probe cannot be classified, a precondition fails,
a mutation receipt is unconfirmed, or the clock offset is out of tolerance — say so. A
confident wrong number is worse than no number.

---

## Part 3 — How the pieces fit

### Capability abstraction

A `Capability` is abstract (`objectstore.read`) and defined by an observable, benign,
verifiable operation. A `ProviderCapabilityBinding` maps it to provider actions, a resource
template, a probe class and preconditions. The catalog names no provider; bindings live in
provider packages.

Two capabilities are special. `identity.whoami` is the **control**: granted to every
identity, undeniable by an identity policy, and its failure means the apparatus is broken —
discard the matrix rather than recording denials. `identity.delegate` is the capability to
delegate onward, modeled as first-class so drift in delegation authority is measurable.

### Scenario compilation

```
YAML → safety.load_scenario_yaml (SI-11)
     → ScenarioDocument (Pydantic)
     → semantic validation (G-1..G-5, references, phase ordering)
     → binding resolution (CAP-1)
     → CompiledScenario { graph, probe_matrices, plan, policy_artifacts, warnings }
```

`node.expected = parent.expected ∩ edge.intended` — **intersection, not assignment.**
`compiled_hash` = SHA-256 over canonical spec + catalog version + adapter version, and it
must be byte-identical across processes. Always use `core/canonical.py`; never `json.dumps`
directly.

Probe universe defaults to `scenario`: every capability the scenario names, **not** only
those a node is expected to hold. You cannot detect expansion by testing only for what you
expect.

### Evidence rules

Append-only JSONL written during the run, so a crash yields usable partial evidence. Sealed
at completion with per-artifact hashes and a root. `findings.json` is produced by `analyze`
and is regenerable; `observations.jsonl` is not. Everything passes through `redact()`. All
identifiers are salted-hashed per ADR-013; denial messages are redacted **in place** so the
sentence structure that carries `denial_attribution` survives.

### The measurement hazard you must respect

On S3, `GetObject` against a *missing* key returns `AccessDenied` — the same as a denial —
when the caller lacks `s3:ListBucket`. An agent under test generally lacks it. Therefore:

1. The bootstrap identity verifies markers exist and match their digest **before** every read
   matrix.
2. A read probe is `ALLOWED` only if the returned content matches the expected digest.
   "No exception" is not success.
3. A failed precondition makes the whole matrix `ERROR_INFRASTRUCTURE`, never a set of
   denials.

Get this wrong and every `objectstore.read` measurement in the project is meaningless. It is
the single highest-value correctness detail in the codebase.

### Terraform boundaries

Terraform: roles, trust policies, permission policies, resources, markers. Runtime: STS
assumption, session policies, mutations on agent roles. Contracts are in
`infra/terraform/**/CONTRACT.md` — implement to them. Terraform output names are a stable
interface consumed by preflight P5.

### Test requirements

Four layers (`unit`, `integration`, `aws`, `e2e`); CI runs the first two and needs no cloud
credentials. Coverage per module, not globally: **100%** on `evidence/redaction.py` and
`core/safety.py`, 95% on `core/`, `graph/`, `analysis/`.

Every detector needs a negative control, and every negative control needs its inverse test
(deliberately "fix" the defect and assert `DETECTOR_FAILURE`). Both directions, always.

Never weaken a provider contract test to make an adapter pass. That is the one change that
would make the whole apparatus untrustworthy.

---

## Part 4 — Conventions

- Python 3.12+, `ruff` (line length 100), `mypy --strict`. Both are merge gates.
- All timestamps timezone-aware UTC. All intervals from `time.monotonic_ns()`. Never subtract
  wall-clock times.
- Pydantic models are `frozen=True, extra="forbid"`.
- Domain exceptions from `core/errors.py`; never a bare `Exception`; never swallow an
  exception without recording an observation or event that explains it.
- No `print()` outside `reporting/`.
- Capability collections are `AuthoritySet`, always. Do not "optimize" it into a raw
  `frozenset` — canonical ordering is what makes evidence diffable.
- Update the affected documents **in the same change**. A code change contradicting a
  specification means one of them is wrong; leaving them inconsistent is worse than either.

---

## Part 5 — Milestone prompts

> **Stale for M10–M16.** These prompts were written before implementation started and describe
> an empty repository. M0–M7 are now complete and M8/M9 are code-complete. Use
> [implementation/NEXT_PROMPTS.md](implementation/NEXT_PROMPTS.md) for anything still to be
> built. Parts 1–4 above remain current and every prompt in that file references them.

Each prompt is self-contained. Copy it verbatim.

### Common preamble (already embedded in each prompt below)

> Before writing code: inspect the repository, read the listed documents, and run
> `pytest -m unit -q` to confirm the existing suite passes. Implement only the assigned
> milestone. Preserve every invariant in `docs/CLAUDE_CODE_HANDOFF.md` Part 2. Do not
> refactor adjacent code, do not implement the next milestone, do not revise a decision
> recorded in an ADR — if you believe one is wrong, stop and say so. Write the tests the
> milestone specifies. Run the verification commands and paste the real output, not a
> description of it. Repair failures before reporting done. Update `PROJECT_STATUS.md`.
> Stop only when every acceptance criterion passes.

---

### M0 — Repository foundation and toolchain

```
Implement milestone M0 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M00-foundation.md, ARCHITECTURE.md (section 2, the ARCH-1
dependency rule), and TESTING.md. Run `pytest -m unit -q` and confirm the existing 41+ tests
pass. Significant work already exists in src/chainbreak/core/, capabilities/ and scenarios/
— do not rewrite it; M0 builds tooling around it.

Implement exactly M00-foundation.md: editable install, Makefile, pre-commit,
import-linter contracts encoding ARCH-1, CI workflow requiring no AWS credentials, a
manually-dispatched AWS workflow using OIDC with required reviewers, chainbreak.example.toml,
tests/conftest.py with marker enforcement, and tests/unit/test_import_boundaries.py.

The import boundary test must actually catch violations. Demonstrate this: temporarily add a
file importing boto3 under src/chainbreak/graph/, show the test failing, then remove it.
Do the same for a naive datetime.now() and the ruff DTZ rule.

Do not implement any benchmark logic, provider code, or Terraform.

Preserve every invariant in the handoff Part 2. Run the verification commands from the
milestone file and paste real output. Update PROJECT_STATUS.md: mark M0 complete, set M1 as
the current next action. Stop only when every acceptance criterion in M00-foundation.md
passes.
```

### M1 — Domain model and authorization graph

```
Implement milestone M1 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M01-domain-model.md, and AUTHORIZATION_MODEL.md in full —
sections 4 and 7 are the specification you are implementing. Run `pytest -m unit -q`.

src/chainbreak/core/models.py already contains the domain model and passes 41 tests.
Extend it; do not rewrite it. Add graph/builder.py, graph/divergence.py, graph/paths.py and
core/canonical.py.

Implement every algorithm in AUTHORIZATION_MODEL section 4: per-node divergence, per-edge
divergence (against the source's OBSERVED authority, with the expected-based variant computed
alongside), first_divergence per root-to-leaf path, drift classification, and PathAnalysis
with set- and cardinality-monotonicity computed separately.

Pay particular attention to the CORRECTED drift class: a hop that cleans up upstream drift.
A naive implementation misclassifies it as PROPAGATED, which would make CHAINBREAK report a
working defense-in-depth control as a failure. Test it explicitly.

Reproduce the AUTHORIZATION_MODEL section 7 worked example exactly as a test, including drift
classes and first divergence hop.

Keep core/ and graph/ pure: no I/O, no logging, no clock reads. Coverage must reach 95% on
both.

Preserve every invariant in the handoff Part 2 — AUTH-1 and G-1..G-5 especially. Run the
verification commands and paste real output. Update PROJECT_STATUS.md. Stop only when every
acceptance criterion passes.
```

### M2 — Capability model and catalog

```
Implement milestone M2 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M02-capability-model.md, CAPABILITY_MODEL.md, and
SECURITY_MODEL.md sections SI-3 and SI-9. Run `pytest -m unit -q`.

src/chainbreak/capabilities/catalog.yaml (10 capabilities, v1.0.0) and loader.py already
exist and pass tests. Extend them. Add registry.py, guard.py and preconditions.py.

The important deliverable is guard.py: an OperationAllowlist context manager that records
which provider operations a probe actually invoked and raises CapabilityBroadeningError if
any lies outside the binding's declared action set. This is the mechanism that makes SI-3
enforceable rather than aspirational. Design its interface so M8 can wire it to a botocore
before-call hook.

Create tests/fixtures/bad_bindings.py with an over-broad binding, a wrong-provider binding, a
wrong-probe-kind binding, and one omitting a required precondition. Each must be rejected
with a message naming the problem.

Verify the allowlist catches a real broadening: register a binding declaring one action whose
probe invokes another, and assert it raises even though the probe would otherwise have
succeeded.

Do not add capabilities. Do not implement AWS or fake bindings.

Preserve every invariant in the handoff Part 2. Run the verification commands and paste real
output. Update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

### M3 — Scenario language, validation and compiler

```
Implement milestone M3 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M03-scenario-language.md, and SCENARIO_SPECIFICATION.md in
full. Run `pytest -m unit -q` and `pytest tests/scenarios/ -q`.

scenarios/schema.py, scenarios/safety.py, scenarios/export_schema.py,
schemas/scenario.v1alpha1.schema.json and 12 validating scenario files already exist.
Extend; do not rewrite. Add loader.py (the five-stage pipeline), compiler.py,
policy_synthesis.py and plan.py.

Two requirements carry most of the weight:

1. Expected-authority derivation is INTERSECTION: node.expected = parent.expected ∩
   edge.intended. If the scenario also declares expect_capabilities, assert agreement and
   fail naming both values.
2. compiled_hash must be byte-identical across separate processes. Use core/canonical.py
   exclusively; never call json.dumps directly. Test determinism by compiling in two
   subprocesses and comparing.

Probe universe defaults to `scenario` — the union of every capability the scenario names,
not only what a node is expected to hold. Test that this includes capabilities the node
should NOT have, since that is what makes expansion detectable.

Auto-insert a SNAPSHOT phase immediately before and after every MUTATE.

Handle negative controls: listed graph invariants downgrade to CompileWarning, and
expect_finding is carried into the compiled artifact. Verify nc-scope-expansion.yaml compiles
with a warning, and that removing suppress_graph_check makes it fail.

Create tests/fixtures/scenarios/ with one invalid fixture per failure mode, each asserting
its documented exit code (2 schema, 3 semantic, 4 binding, 5 safety).

Preserve every invariant in the handoff Part 2. If the schema changes, regenerate schemas/
with `python -m chainbreak.scenarios.export_schema`. Run the verification commands and paste
real output. Update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

### M4 — CLI, configuration and the SafetyGate

```
Implement milestone M4 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M04-cli-config-safety.md, SECURITY_MODEL.md (SI-5, SI-6, SI-7,
SI-8, SI-10), and AWS_PROVIDER_SPEC.md section 2. Run `pytest -m unit -q`.

Implement config/settings.py, config/fingerprint.py, core/safety.py, core/clock.py, the
Typer CLI in cli/, and cli/logging.py.

The SafetyGate is the point of this milestone. Requirements that are not negotiable:

- No bypass flag may exist. Write tests/unit/test_cli_surface.py that introspects every Typer
  command and fails if any option matches --force, --skip-*, --no-safety or similar. Then
  demonstrate it works by temporarily adding such a flag and showing the test fail.
- allowed_account_ids admits no wildcard, no "current account" default, no empty value.
- The run-duration ceiling of 14400s is not configurable upward.
- The cost estimator must be conservative: assert the estimate is >= the true call count
  times the cost table.
- The redaction log filter is installed before any import that may log, and covers
  third-party loggers. Test it by enabling botocore DEBUG logging and asserting a
  session-token-shaped string is scrubbed.

Commands not yet implemented exit 2 with "not implemented until M<n>" — never a stack trace.

Coverage on core/safety.py must be 100%.

Preserve every invariant in the handoff Part 2. Run the verification commands and paste real
output. Update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

### M5 — Provider Protocol and the deterministic fake laboratory

```
Implement milestone M5 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M05-fake-provider.md, ARCHITECTURE.md sections 3.8-3.10, and
ADR-008. Run `pytest -m "unit or integration" -q`.

Implement providers/base/ (the ProviderAdapter Protocol, shared types, assert_namespace) and
providers/fake/.

The fake provider is not a stub. It must implement a real policy evaluator with explicit
deny > explicit allow > implicit deny, across identity policy, session policy (INTERSECTION
semantics — a session policy can never grant), and resource policy. It must model credential
lifetimes, expiry, and a configurable chained-role duration cap so LIFETIME_CAPPED is
exercisable offline.

It must also support an injectable consistency model (propagation_delay_ms, jitter, an
oscillation mode) and fault injection (transient_error_rate, clock_skew_ms,
throttle_after_n_calls), all fully seeded so the same seed produces byte-identical runs.
This is what makes M12-M14 developable and testable without AWS.

Use a virtual clock for waiting so a 600-second deferral test runs instantly, while the
measurement code still uses the monotonic clock abstraction.

The most important deliverable is tests/integration/test_provider_contract.py: the shared
behavioral suite both adapters must pass. Fixed-role providers may use explicit setup hooks,
but the behavioral assertions must remain shared and must never branch on adapter.name.

Ship three profiles: deterministic (no faults), eventual (2s propagation), hostile (faults +
skew + oscillation).

Preserve every invariant in the handoff Part 2 — SI-2 especially: the fake must refuse
out-of-namespace targets exactly as AWS will. Run the verification commands and paste real
output, including two identical-seed runs producing identical evidence. Update
PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

### M6 — Evidence pipeline, redaction and sealing

```
Implement milestone M6 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M06-evidence-pipeline.md, EVIDENCE_SCHEMA.md in full,
SECURITY_MODEL.md SI-1, and ADR-013. Run `pytest -m "unit or integration" -q`.

Implement evidence/writer.py, redaction.py, manifest.py, index.py, reader.py and export.py.

This is the highest-stakes milestone in the project. redact() is the single serialization
choke point every record passes through, and it RAISES SecretLeakError on a hit — it does not
sanitize and continue. A leak is a bug to fix, not a value to clean up.

tests/unit/test_redaction.py must be property-based and reflection-driven: discover every
Pydantic model in core/ by reflection, populate every string field from a synthetic secret
corpus (fake AKIA/ASIA keys, a JWT, a PEM block, a base64 blob, a session-token shape),
serialize a bundle, and assert either SecretLeakError was raised or zero corpus values appear
in any output byte — and that the secret appears in no repr, str, format, traceback or log
record. Reflection-driven discovery means future model fields are covered automatically.

Coverage on evidence/redaction.py must be 100%. A missed branch is a credential leak.

Identifiers are salted-hashed per ADR-013. Denial messages are redacted IN PLACE — replace
ARNs with <REDACTED_ARN> rather than dropping the field, because the sentence structure is
what carries denial_attribution.

Create tests/fixtures/bundles/ with golden, tampered and malicious bundles. The reader must
handle a hostile bundle with bounded rejection, not a crash.

Preserve every invariant in the handoff Part 2 — EV-1 and SI-1 above all. Run the
verification commands and paste real output, including the grep showing no key-shaped strings
in evidence. Update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

### M7 — Analysis, findings and the confidence gate

```
Implement milestone M7 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M07-analysis-findings.md, AUTHORIZATION_MODEL.md sections 4-6,
ADR-006 and ADR-012. Run `pytest -m "unit or integration" -q`.

Implement analysis/: authority.py, divergence.py, confidence.py, rules.py, timing.py,
detector.py, pipeline.py.

Cell resolution is by UNANIMITY (ADR-012), not majority voting: all-ALLOWED yields ALLOWED;
all-denial yields that denial or DENIED_UNATTRIBUTED if attributions differ; all-error yields
that error; anything mixed yields INDETERMINATE with the trial vector recorded.

Every finding must carry observation, expected_state, observed_state and
security_interpretation as SEPARATE fields. Never merge them into prose.
security_interpretation strings must be static templates with substituted values, never
free-form text built from bundle content — that would be an injection path into the HTML
report.

The two most valuable tests are the known-truth differentials, which no AWS run can provide:

- test_known_truth_divergence.py: configure the fake with an authority set that differs from
  intent in a known way; assert exactly the expected findings with exactly the expected
  confidence.
- test_known_truth_timing.py: set fake propagation_delay_ms to 2000; assert the measured
  transition window contains 2000ms.

Run all six nc-* scenarios against the fake; each must produce its declared finding. Then
deliberately "fix" each defect and assert DETECTOR_FAILURE is emitted. Both directions are
required: the first proves detection, the second proves the detector check itself works.

Do not smooth a NON_MONOTONIC_TRANSITION. Oscillation is the most interesting possible result
in the revocation family; hiding it would be a research failure, not a usability improvement.

analyze must be idempotent: byte-identical findings.json on repeat.

Preserve every invariant in the handoff Part 2. Run the verification commands and paste real
output. Update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

### M8 — AWS provider adapter

```
Implement milestone M8 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M08-aws-adapter.md, AWS_PROVIDER_SPEC.md IN FULL, and
SECURITY_MODEL.md. Run `pytest -m "unit or integration" -q`.

This milestone requires an operator-owned AWS benchmark account for the `aws` test layer.
Confirm with the operator before running anything billable. Non-AWS parts are developable
with moto.

Implement providers/aws/: adapter, preflight, session, bindings, probes, mutation, policy,
disambiguation, policy_synthesis, retry.

Implement in this order, because correctness depends on it:

1. preflight.py — P1-P11 in the documented order. GetCallerIdentity is the first call and, on
   account mismatch, the ONLY call. Prove it with a call-log assertion.
2. Marker precondition verification by the bootstrap identity.
3. Probes — only after preconditions work.

The reason for that order is AWS_PROVIDER_SPEC section 6.1: on S3, GetObject against a
missing key returns AccessDenied — identical to a denial — when the caller lacks
s3:ListBucket, which an agent under test generally does. Without a verified marker,
objectstore.read cannot be measured at all. A read probe is ALLOWED only if the returned
content matches the expected digest; "no exception" is not success. A failed precondition
makes the whole matrix ERROR_INFRASTRUCTURE, never a set of denials.

Wire the M2 OperationAllowlist and the namespace assertion to a botocore before-call hook, so
SI-2 and SI-3 are enforced independently of whether a probe remembered to call them.

test_adapter_real.py (marker aws) is where IAM semantics are validated: the role-chain
duration cap, session policies cannot grant, explicit deny wins, denial message attribution,
the 403/404 ambiguity, missing marker handling, whoami never denied, out-of-namespace refusal.
The denial-message test is the canary for AWS changing its error format — it must fail loudly
rather than fall back to a guess.

test_adapter_moto.py covers call shapes ONLY. Every moto test must carry a docstring stating
that moto's policy evaluation is an approximation and is not ground truth.

The AWS adapter must pass the shared M5 contract assertions. Fixed Terraform roles may be
selected through setup hooks; do not weaken or override a contract assertion.

Preserve every invariant in the handoff Part 2. Run the verification commands and paste real
AWS output. Update PROJECT_STATUS.md recording which AWS tests actually ran, when, and in
which account (hashed). Stop only when every acceptance criterion passes.
```

### M9 — Terraform AWS sandbox

```
Implement milestone M9 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M09-terraform-sandbox.md, infra/terraform/README.md, and every
CONTRACT.md under infra/terraform/. Those contracts ARE the specification — implement to them
rather than restating or replacing them. Read AWS_PROVIDER_SPEC.md sections 3, 5, 8 and 9.

This milestone requires an operator-owned AWS account and real (small) spend. Confirm before
applying.

Implement main.tf, variables.tf, outputs.tf and versions.tf for all five modules and both
environments, plus cli/infra.py.

Non-negotiable requirements:

- benchmark-account must fail at PLAN time on an account mismatch, not apply time. An
  operator pointed at the wrong account should never reach a diff that looks appliable.
- No Resource: "*" except a statement whose only action is sts:GetCallerIdentity. Add the
  tflint/checkov rule that enforces this.
- Bootstrap must not be able to mutate itself or the principal. Verify with
  iam:SimulatePrincipalPolicy in a test, not by reading the policy.
- default_tags at the provider level, with service-specific fail-closed enumerators (including
  IAM roles and policies) so verify-clean cannot claim clean from a partial inventory.
- DynamoDB PAY_PER_REQUEST. Provisioned capacity is the most likely way to accidentally spend
  money here.
- terraform destroy must succeed with zero manual steps, and a second destroy must be a clean
  no-op. Test this by actually destroying twice, not by reading the plan.

Verify the full cycle for real: apply, chainbreak validate (all preflight checks), destroy,
chainbreak infra verify-clean showing zero remaining resources.

Preserve every invariant in the handoff Part 2 — INFRA-1 and INFRA-2 especially. Run the
verification commands and paste real output including the verify-clean result. Update
PROJECT_STATUS.md with the apply/destroy cycle actually performed. Stop only when every
acceptance criterion passes.
```

### M10 — Scope attenuation benchmark

```
Implement milestone M10 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M10-scope-attenuation.md, EXPERIMENT_PROTOCOL.md section 1,
and RESEARCH_METHODOLOGY.md section 4 (the controls). Run `pytest -m "unit or integration" -q`.

Implement execution/: orchestrator.py, matrix.py, delegation.py, preconditions.py,
control.py. Everything runs against the fake provider; AWS execution is M17.

Design the phase loop against the FULL PhaseKind enum from the start, even though only PROBE
is exercised here. Building orchestration that only works for one family means rewriting it
in M12.

Controls that must be implemented, not deferred:

- C-6: probe order shuffled with a RECORDED seed. Without this, a capability probed last
  systematically carries more credential age and throttling pressure.
- C-1: identity.whoami probed in every matrix. Its failure raises
  ControlCapabilityFailedError and DISCARDS the matrix rather than recording a wave of
  denials.
- C-2: preconditions verified by the provisioning identity before every read matrix.
- Credential lifetime checked before each matrix; re-delegate if remaining lifetime is under
  2x the estimated matrix duration, recording the re-delegation as an event.

Run both scope-attenuation negative controls. nc-surviving-authority is the important one: it
fails if divergence is computed only at node level, because a node's derived expectation can
coincide with the observed set while the EDGE's intent was violated.

Preserve every invariant in the handoff Part 2. Run the verification commands and paste real
output. Update PROJECT_STATUS.md marking Family A implemented AND explicitly noting it has
not been run against AWS. Stop only when every acceptance criterion passes.
```

### M11 — Delegation drift benchmark

```
Implement milestone M11 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M11-delegation-drift.md, AUTHORIZATION_MODEL.md sections 4.4,
4.5 and 7, and EXPERIMENT_PROTOCOL.md section 2. Run `pytest -m "unit or integration" -q`.

Implement execution/chain.py and analysis/drift.py, and author the depth-2, 3, 5 and 6
scenarios (four-hop already exists). Each depth is a SEPARATE file so compiled_hash differs
and results can never be accidentally pooled.

Reproduce the AUTHORIZATION_MODEL section 7 worked example end to end: divergence at hop 3
classified ORIGINATED, hop 4 PROPAGATED, first divergence reported as hop 3, and hop 4's
finding citing hop 3 as its cause rather than raising an independent alarm.

Also construct a case where hop 3 gains a capability and hop 4 drops it, and assert hop 4
classifies CORRECTED. A benchmark that reports that as a failure would flag working
defense-in-depth as a problem.

Depth and total probe count are confounded: a depth-6 chain issues more calls, takes longer,
and has more opportunity for transient error. Report divergence as a RATE PER HOP, not per
chain, and report the excluded-trial count per depth alongside it. If deeper chains show more
divergence AND more exclusions, the result is inconclusive and must be reported as such. This
is requirement F6 and it is not optional.

Preserve every invariant in the handoff Part 2. Run the verification commands and paste real
output. Update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

### M12 — Revocation propagation benchmark

```
Implement milestone M12 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M12-revocation.md, AUTHORIZATION_MODEL.md section 5.1,
RESEARCH_METHODOLOGY.md sections 6 and 7, EXPERIMENT_PROTOCOL.md section 3, and ADR-011.
Run `pytest -m "unit or integration" -q`.

Implement execution/mutation.py, execution/polling.py, execution/revert.py and the timing
extensions in analysis/timing.py. Author the three remaining revocation scenarios.

Requirements that determine whether the measurements mean anything:

- t_M is the monotonic instant the mutation request was SENT. Confirmation latency is
  recorded separately. Using the send instant is conservative: it can only make the window
  appear longer.
- Warm baseline before mutation: poll to stable allow, so the first post-mutation poll is not
  systematically slower than the rest.
- The window is [t_last_allow - t_M, t_first_deny - t_M] with a midpoint estimate and a
  half-width. There is NO scalar representation anywhere. Add a test that scans findings.json
  for a bare timing value and fails if it finds one.
- NON_MONOTONIC_TRANSITION preserved with the full timeline. Never smoothed.
- NO_TRANSITION_OBSERVED_WITHIN_WINDOW with the window length — an honest negative, not a
  pass.
- The revert log is written BEFORE each mutation, so a SIGKILL still leaves actionable
  recovery information. Test this by killing the orchestrator mid-phase.
- Between trials: revert, confirm, wait for stable allow before the next mutation.

Validate the interval math against known answers: fake propagation_delay_ms in {0, 500, 2000,
10000}; the measured window must contain the true value in every case. This is the only place
the math can be checked against ground truth, so it is the most important test here.

Run nc-no-revocation (must yield NO_TRANSITION_OBSERVED) and
revocation/trust-policy-null-condition (must show NO transition — that is control C-5, the
instrument check).

Preserve every invariant in the handoff Part 2. Run the verification commands and paste real
output. Update PROJECT_STATUS.md stating plainly that no AWS revocation measurement exists
yet. Stop only when every acceptance criterion passes.
```

### M13 — Stale authority benchmark

```
Implement milestone M13 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M13-stale-authority.md, AUTHORIZATION_MODEL.md section 5.2,
and EXPERIMENT_PROTOCOL.md section 4. Run `pytest -m "unit or integration" -q`.

Implement execution/deferred.py, execution/credential_store.py and analysis/stale.py, and
author the short-defer, long-defer and post-expiry scenarios.

The design element that makes this family interpretable at all is the PAIRED FRESH
CREDENTIAL. After the deferred probe using the pinned pre-mutation credential, immediately
probe the same capability with a freshly minted credential. Without the pair, an ALLOWED at
t_exec is ambiguous between "the policy change never propagated" and "the old credential
retained old authority" — two completely different findings. Implement this as requirement
F3, and test the ambiguous case explicitly: configure the fake so the change has not
propagated, and assert the classification is "not propagated", NOT stale authority.

WAIT phases must not touch the credential — no keepalive, no refresh. The waiting is the
experiment.

Assert credential pinning from the EVIDENCE STREAM (the deferred observation's credential_id
matches the phase's), not from the code path, so a refactor cannot silently break it.

STALE_AUTHORITY_LIVE_CREDENTIAL is documented bearer-token behavior. Reports must say so in
the same paragraph as the result. Only EXPIRED_CREDENTIAL_HONORED contradicts documented
behavior.

Use the fake's virtual clock so a 600-second deferral test runs instantly in CI while the
measurement code still uses the clock abstraction. Make sure the SI-7 run deadline accounts
for deferral time.

Preserve every invariant in the handoff Part 2. Run the verification commands and paste real
output. Update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

### M14 — Silent narrowing benchmark

```
Implement milestone M14 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M14-silent-narrowing.md, SCENARIO_SPECIFICATION.md section 6,
EXPERIMENT_PROTOCOL.md section 5, and ADR-007. Run `pytest -m "unit or integration" -q`.

Implement execution/workers/base.py and deterministic.py, execution/task_runner.py,
execution/side_effects.py and analysis/task_contract.py.

Define the TaskWorker Protocol purely in terms of a capability-invoker and a returned
TaskOutcome — nothing about how the worker decides. A v0.4 LLM-backed worker must be able to
implement the same interface with no downstream change. Building the Protocol around the
deterministic implementation would foreclose that.

Ship four deterministic workers: sequential (honest), always-complete (the negative-control
liar), substituting, redelegating.

The core requirement is INDEPENDENT SIDE-EFFECT VERIFICATION: after the task, the bootstrap
identity checks whether the output marker the task claims to have written actually exists.
The worker's self-report is never trusted. A task reporting COMPLETE while its output marker
is absent is the purest form of silent failure, and this check catches it even when the
worker's step counts are internally consistent.

Workers invoke capabilities only through the executor's capability-invoker, never a raw
provider client, so SI-2 and SI-3 apply to task actions exactly as to probes. A redelegation
attempt is RECORDED and refused, not permitted.

Include a positive control: the same task with full authority must report COMPLETE and the
marker must exist.

Every report including this family must state that v0.1's worker is synthetic, so the family
measures the harness rather than agent behavior.

Preserve every invariant in the handoff Part 2. Run the verification commands and paste real
output. Update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

### M15 — Per-category scoring

```
Implement milestone M15 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M15-scoring.md, SCORING_MODEL.md in full, and ADR-010.
Run `pytest -m "unit or integration" -q`.

Implement scoring/: categories.py, coverage.py, confidence.py, aggregate.py.

Six independent category evaluators. There is NO composite score, and there must be no
function anywhere that reduces categories to a single number. Add a test that asserts this by
module introspection, and a grep in the verification step.

Rules that are easy to get subtly wrong:

- A category not exercised by the scenario is NOT_MEASURED, never CONSISTENT. Rendered output
  must contain the literal sentence "NOT_MEASURED is not a pass."
- coverage < 0.7 forces PARTIAL regardless of what the measured cells showed.
- Confidence aggregates with min, never a mean. Averaging would let a pile of easy
  measurements launder one shaky one. Test with five HIGH and one LOW; the result must be LOW.
- Revocation Responsiveness is DIVERGENT only when an ASSERTIVE scenario expectation was
  exceeded. There is no built-in propagation threshold, because CHAINBREAK does not know what
  a correct propagation time is.
- STALE_AUTHORITY_LIVE_CREDENTIAL yields CONSISTENT with a mandatory note that it is
  documented behavior. Only EXPIRED_CREDENTIAL_HONORED is DIVERGENT.
- Cross-run aggregation refuses differing compiled_hash, adapter_version or catalog_version.
  No mean without dispersion; no dispersion below n=5.

No CLI flag may raise confidence or coverage. --allow-unsealed and --allow-heterogeneous only
lower it. Assert this by introspecting the command surface.

Preserve every invariant in the handoff Part 2. Run the verification commands and paste real
output. Update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

### M16 — Reporting and visualization

```
Implement milestone M16 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M16-reporting.md, EXPERIMENT_PROTOCOL.md section 7 (the
language rules), SCORING_MODEL.md section 4, and THREAT_MODEL.md T-10.
Run `pytest -m "unit or integration" -q`.

Implement reporting/: terminal.py, markdown.py, html.py, figures.py, language.py, templates/.

Two requirements do most of the work:

1. reporting/language.py implements the EXPERIMENT_PROTOCOL section 7 rules as a checkable
   lint over templates and generated text: required elements present (n, interval, mechanism,
   region on every timing result; coverage and confidence on every category), forbidden words
   absent ("vulnerable", "broken", "insecure", "exploit", "proves"), no timing value without
   an interval, no percentage without a denominator. Demonstrate it works by planting a
   violating sentence in a template and showing the test fail.

2. Jinja2 autoescape on, with NO |safe anywhere — asserted by a test that greps the template
   directory. A third-party evidence bundle is a plausible XSS vector into a generated HTML
   report. Test with a bundle whose security_interpretation contains a script tag.

Every finding renders observation, expected_state, observed_state and security_interpretation
under separate headings, in that order.

A provider: fake run must be stamped as non-measurement output in the header AND in every
figure caption, enforced in the rendering layer rather than left to the operator. A
fake-provider report must never be mistakable for a measurement.

Every report carries a limitations section naming: single account, single region, simple
policies, deterministic worker, small n.

All figures are generated from evidence. Never hand-written numbers.

Commit a sample HTML report from a fake run under examples/, with its header stating it is
fake-provider output.

Preserve every invariant in the handoff Part 2. Run the verification commands and paste real
output. Update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

### M17 — Full AWS experiment suite

```
Execute milestone M17 for CHAINBREAK — the first real measurements.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M17-aws-experiment-suite.md, EXPERIMENT_PROTOCOL.md IN FULL,
and RESEARCH_METHODOLOGY.md IN FULL. Run the complete test suite.

This milestone requires an operator-owned AWS benchmark account and real spend (under $1).
Confirm with the operator before starting, and confirm again before each block.

This is not primarily a coding milestone. It is an experimental one, and the discipline is
the deliverable.

Procedure per block:

1. Run the EXPERIMENT_PROTOCOL section 0 pre-experiment checklist. Record the result in
   docs/research/lab-log.md. An experiment whose checklist was not run is not a CHAINBREAK
   experiment.
2. Apply infrastructure with enable_negative_controls = true.
3. Run all five families with the required trial counts: n>=5 timing, n>=3 set-valued.
4. Run ALL SIX negative controls in the SAME block, on the same infrastructure, with the same
   adapter version. A control run later against different infrastructure proves less.
5. Record every exclusion with its reason.
6. Capture the exact namespace before destroy; destroy, then run
   `chainbreak infra verify-clean aws-sandbox --namespace <captured-namespace>`.

Distribute timing trials across at least THREE separate hours (control C-7), recording
block_id. IAM propagation may plausibly vary with provider-side load, and back-to-back trials
cannot detect that.

If any block produces a DETECTOR_FAILURE, that block is unvalidated: do not publish any
result from it. This is not a guideline.

Write docs/research/results-v0.1.md from actual measurements only. Every timing result gets
n, an interval, the mechanism, and the region. Every claim is scoped to "this account, this
region, this time". Apply the EXPERIMENT_PROTOCOL section 7 language rules.

If a result suggests a genuine provider defect rather than one of the documented behaviors in
AWS_PROVIDER_SPEC section 10: STOP, reproduce it, run the negative controls again, and follow
coordinated disclosure per SECURITY.md before publishing anything.

Update PROJECT_STATUS.md moving experiments from "unmeasured" to "measured" WITH RUN IDS, and
listing what remains unmeasured. Paste real run IDs and real output. Never claim an
experiment ran unless it ran.
```

### M18 — Reproducibility and hardening

```
Implement milestone M18 for CHAINBREAK.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M18-reproducibility-hardening.md, and REPRODUCIBILITY.md in
full. Run the complete test suite.

Implement analysis/compare.py, evidence/archive.py, evidence/migrate.py, and a Dockerfile.

chainbreak compare must classify results into the three levels from REPRODUCIBILITY section
1: analytical (identical), structural (set-valued results match exactly), distributional
(timing overlaps). Timing results are Level 3 and exact reproduction is NOT expected — anyone
claiming exact timing reproducibility on a shared cloud control plane is mistaken, and the
tool should say so in its output.

Refuse to compare across differing compiled_hash, adapter_version or catalog_version without
--allow-heterogeneous, which lowers confidence. --cross-operator relaxes environment checks
and must print a prominent note that environment equivalence is assumed and unverified.

evidence export --archive must produce a tarball containing the bundle, the resolved scenario,
the capability catalog AS IT WAS AT RUN TIME, the JSON Schemas, and a generated REPRODUCE.md.
Schemas are included because a bundle without its schema is uninterpretable once schemas
evolve. Test self-containment by extracting into a container with no repository checkout.

--archive implies --public scrubbing. There is no unscrubbed archive path.

Add the dependency lockfile with hashes and pip install --require-hashes in CI (threat T-14).

Preserve every invariant in the handoff Part 2. Run the verification commands and paste real
output, including two identical-seed runs comparing as identical and a Docker run producing
byte-identical output. Update PROJECT_STATUS.md. Stop only when every acceptance criterion
passes.
```

### M19 — Portfolio and public release

```
Execute milestone M19 for CHAINBREAK — v0.1.0 release.

First: inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M19-portfolio-release.md, docs/PORTFOLIO_STORY.md and
PROJECT_STATUS.md. Run the complete test suite.

Perform the full consistency review. Verify, and fix any contradiction you find, across:
scenario schema <-> domain models <-> authorization graph <-> provider abstraction <->
capability model <-> AWS adapter <-> Terraform contracts <-> testing strategy <-> evidence
schema <-> findings <-> scoring <-> README. Record each resolution in docs/DECISIONS.md.
Do not paper over a contradiction; one of the two documents is wrong and it matters which.

Then, and this is the part that requires the most discipline: audit every document for
claims about results. Update docs/PORTFOLIO_STORY.md and README.md so they describe ONLY
what was actually measured in M17, each with its run ID. Anything not measured is described
as designed-and-implemented-but-unmeasured, explicitly.

The strongest temptation in this project arrives here: describing the architecture as if it
were results. The architecture is real and defensible; the measurements are whatever M17
actually produced. State both accurately — the artifact is stronger for it than an overclaim
would make it.

Verify no sensitive value exists in the repository OR ITS GIT HISTORY: account IDs, ARNs,
key-shaped strings, hostnames, session names. A working-tree scan is not sufficient.

Execute every command that appears in the README and confirm it works as documented.

Write CHANGELOG.md. Publish a scrubbed sample report under examples/. Confirm the README
status block matches PROJECT_STATUS.md exactly. Tag v0.1.0.

Paste real output for every verification command. Update PROJECT_STATUS.md to reflect the
released state including an explicit list of what remains unmeasured.
```

---

## Part 6 — When to stop and ask

Stop and ask rather than deciding unilaterally when:

- An invariant in Part 2 appears to be wrong or to block a milestone requirement.
- A specification document contradicts another and you cannot tell which is authoritative.
- A milestone's acceptance criteria cannot be met without changing a design decision.
- Real AWS behavior contradicts `AWS_PROVIDER_SPEC.md` section 10.
- A measurement suggests a genuine provider defect rather than documented behavior.
- Spend is about to exceed the configured ceiling.
- A test would need to be weakened to make an implementation pass.

The last one is the most important. A weakened test is a silent, permanent loss of assurance,
and it is always cheaper to raise the question than to discover later that a green suite meant
nothing.
