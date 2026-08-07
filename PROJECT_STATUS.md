# CHAINBREAK Project Status

**The durable source of truth.** Every other document defers to this one on questions of what
exists, what works, and what has actually been measured. Updated at the end of every
milestone.

**Last updated:** 2026-08-07 · **Version:** 0.1.0a0 · **Phase:** M5 complete, M6 next

---

## The honest headline

> CHAINBREAK has a complete architecture, a verified domain model, a validated scenario
> corpus, and a full implementation plan.
>
> **No benchmark has been executed. No AWS experiment has been run. No measurement exists
> anywhere in this repository.**
>
> Every number appearing in any document is either an illustration of an algorithm — labelled
> as such — or a design parameter. None is a result.

---

## Current phase

**Architecture and specification: complete.** Twenty milestones specified with acceptance
criteria and verification commands. Fourteen ADRs accepted. Twelve security invariants defined
with named enforcement points. Fifteen threats modelled with seven accepted residual risks.

**Implementation: M0 through M5 complete, M6 is the next action.** M0 made the repository
buildable, lintable, type-checkable and testable, and put CI in a state where it enforces the
structural rules the rest of the project depends on. M1 completed the domain model and
authorization graph: the divergence algorithms in AUTHORIZATION_MODEL.md section 4, graph
invariants G-1 through G-5, canonical JSON, and root-to-leaf path analysis. M2 completed the
capability layer: the binding registry, the runtime operation-allowlist that makes SI-3
enforceable, and precondition resolution. M3 completed the scenario language: the five-stage
validation pipeline and the compiler that turns a scenario document into a `CompiledScenario`.
M4 completed the entry point and the gate every run must pass: layered configuration
resolution, the `SafetyGate` (SI-5/SI-7/SI-8), the monotonic run clock (SI-7), the redaction
log filter (SI-10), and the full `chainbreak` Typer CLI surface. M5 completed the provider
Protocol and a real, deterministic fake authorization engine — real explicit-deny-over-allow
policy evaluation with session-policy intersection, credential lifetime capping, an injectable
consistency model that can reproduce a genuine non-monotonic revocation transition, and bindings
for all 10 catalog capabilities — proven byte-for-byte reproducible across independent processes
from a single seed. All six milestones are
analysis/domain/capability/scenario/CLI/provider-laboratory work — no benchmark has executed
and no AWS experiment has run.

---

## Architecture status

| Area | Status | Authority |
|---|---|---|
| Layer map and dependency rule | Complete | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Domain model | Complete **and verified in code** | [AUTHORIZATION_MODEL.md](AUTHORIZATION_MODEL.md), `core/models.py` |
| Authorization graph and divergence algorithms | Complete **and verified in code** — G-1–G-5, all section 4 algorithms, canonical JSON | AUTHORIZATION_MODEL §2, §4, `graph/`, `core/canonical.py` |
| Capability model | Complete **and verified in code** — catalog v1.0.0/10 capabilities, registry, operation allowlist (SI-3), preconditions | [CAPABILITY_MODEL.md](CAPABILITY_MODEL.md), `capabilities/` |
| Scenario language v1alpha1 | Complete **and verified in code** — full five-stage pipeline, compiler, all 12 scenarios compile | [SCENARIO_SPECIFICATION.md](SCENARIO_SPECIFICATION.md), `scenarios/` |
| Evidence schema | Complete; 11 JSON Schemas generated and validated | [EVIDENCE_SCHEMA.md](EVIDENCE_SCHEMA.md) |
| Config, SafetyGate, CLI | Complete **and verified in code** — layered config resolution, `SafetyGate` at 100% coverage, monotonic run clock, redaction filter, full `chainbreak` Typer surface | [M04-cli-config-safety.md](docs/implementation/milestones/M04-cli-config-safety.md), `config/`, `core/safety.py`, `core/clock.py`, `cli/` |
| Provider abstraction | Complete **and verified in code** — `ProviderAdapter` Protocol, live wire types, `assert_namespace` (SI-2) | ARCHITECTURE §3.8, [ADR-008](docs/adr/ADR-008-provider-adapter-boundary.md), `providers/base/` |
| Fake provider laboratory | Complete **and verified in code** — real policy engine, session lifetimes, injectable consistency model, 10/10 capability bindings, 3 named profiles, all 12 scenarios walk without crashing | ARCHITECTURE §3.9, `providers/fake/` |
| AWS provider | Specified, not implemented | [AWS_PROVIDER_SPEC.md](AWS_PROVIDER_SPEC.md) |
| Terraform | Module contracts written, no `.tf` implemented | `infra/terraform/**/CONTRACT.md` |
| Scoring | Specified, not implemented | [SCORING_MODEL.md](SCORING_MODEL.md) |
| Reporting | Specified, not implemented | ARCHITECTURE §3.16 |
| Research methodology | Complete | [RESEARCH_METHODOLOGY.md](RESEARCH_METHODOLOGY.md) |
| Threat model | Complete | [THREAT_MODEL.md](THREAT_MODEL.md) |

---

## Milestone status

### Completed

**M0 — Repository foundation and toolchain.** All five acceptance criteria demonstrated;
see [docs/implementation/milestones/M00-foundation.md](docs/implementation/milestones/M00-foundation.md)
for the criteria and the verification commands below for the pasted output. Criterion 4
("CI green on a PR with no AWS credentials configured") was demonstrated via direct pushes
to `main` rather than an actual pull request — this repository had no collaborators or
open PRs at M0 — but the workflow runs identical jobs on both `push` and `pull_request`
triggers, so the substance of the criterion (CI passes end-to-end without cloud credentials)
is verified; the PR-specific trigger path itself remains unexercised.

Delivered: editable install on Python 3.12 (3.13 covered by the CI matrix, not locally
verified — no 3.13 interpreter in the environment M0 was built in); `ruff` and `mypy`
already configured in `pyproject.toml`, now clean (12 pre-existing lint findings and 4
pre-existing `mypy` findings fixed — all mechanical: `noqa`/`nosec`/`type: ignore` on
false positives from bandit misreading a hardened YAML loader and an enum member,
plus one line-length wrap and one unescaped regex `match=` in a test); import-linter
contracts encoding ARCH-1 (`[tool.importlinter]` in `pyproject.toml`, six contracts, all
kept, verified against a planted `boto3` import in `graph/`); `tests/unit/test_import_boundaries.py`
(AST-based, independent of the import-linter config, with its own planted-violation
negative controls); `tests/conftest.py` gating the `aws`/`e2e` markers behind
`CHAINBREAK_ALLOW_AWS_TESTS=1` (F5), proven both ways with `tests/aws/test_placeholder.py`;
`Makefile`, `.pre-commit-config.yaml`, `chainbreak.example.toml`.

CI (`ci.yml`, `aws-experiment.yml`) existed before M0 but had never executed (see prior
"known issues" entry, now resolved) and referenced functionality from later milestones.
M0 found and fixed three latent bugs in it: an unpinned `aws-actions/configure-aws-credentials`
and an unpinned (`@master`) `bridgecrewio/checkov-action`, both now SHA-pinned; and a
`pull_request_target` guard step that grepped for its own literal script text and would
have failed on its first real run regardless of the workflow's actual triggers, now scoped
to the YAML trigger-key form. `pip-audit --strict` was replaced with `pip-audit --skip-editable`
because `--strict` treats the repository's own editable-installed package as an unauditable,
fatal dependency. Two coverage gates (SI-1 redaction, SI-5 SafetyGate) reference test files
that belong to M6 and M4 respectively; rather than deleting them or faking a pass, they are
guarded to activate automatically the moment those files exist. The `chainbreak scenario
validate --offline` CLI step was replaced with a comment pointing at
`tests/scenarios/test_scenario_corpus.py`, which already exercises the same
load-and-validate pipeline the CLI will wrap once it exists (M4) — no coverage was lost.
The AWS-credentialed steps in `aws-experiment.yml` cannot be exercised before M9 (they need
real infrastructure) and are unverified until then; that workflow cannot execute
accidentally regardless, since it needs a human to supply `confirm: APPLY` inside the
`aws-benchmark` environment.

CI was then observed running for real on GitHub Actions after the push (run
[31179401063](https://github.com/KubixDesiney/chainbreak/actions/runs/31179401063)). Seven
of eight jobs went green on the first run; `security` failed on a check that had not been
exercised locally with real git history: the AWS-key-shaped-string regex, run against
`git log -p --all`, has no `EXAMPLE` exemption, so it self-triggered the moment the synthetic
test fixture at [tests/unit/test_domain_contract.py:101](tests/unit/test_domain_contract.py)
(a fake `ASIA`-prefixed session credential used to prove `SecretMaterial` never renders its
value) entered history. Fixed by applying the same `grep -v 'EXAMPLE'` exemption the
working-tree check already uses, in a follow-up commit. That fix commit's own message
reproduced the literal fixture value in prose outside `tests/`, which the *working-tree*
variant of the same check (rightly) has zero tolerance for — caught by the second CI run,
fixed by describing the fixture instead of quoting it (this paragraph included). Two rounds
of "the security check catches the security-check bug report" — noted here because it is a
genuinely instructive example of why these checks apply uniformly rather than trusting any
file, including this one, to police itself.

A third run then failed `boundaries` with `lint-imports` reporting `chainbreak.evidence`
missing entirely -- not a flaky check, an actual missing file. `.gitignore`'s `evidence/`
rule (meant for a runtime evidence-output directory) was unanchored, so it also matched
`src/chainbreak/evidence/`, the source package, and silently excluded it from every commit
made in this environment; it was never pushed. `git status --ignored` confirmed it was the
only source file affected. Fixed by anchoring `evidence/`, `runs/` and `reports/` to the
repo root (`/evidence/`, `/runs/`, `/reports/`) so they match only the top-level runtime
output directories, and committing the previously-excluded `src/chainbreak/evidence/__init__.py`.
This is the kind of defect a local `pytest`/`lint-imports` run cannot catch by construction
(gitignore doesn't affect the local working tree, only what git tracks) — it only surfaces
on a fresh clone, which is exactly what CI is for.

The fourth run
([31180564148](https://github.com/KubixDesiney/chainbreak/actions/runs/31180564148)) passed
all ten jobs (`boundaries`, `guards`, `lint`, `types`, `security`, `schemas`, `scenarios`,
`terraform`, `test` × {3.12, 3.13}). Known issue 5 is resolved: CI is no longer merely
"believed correct", it has been observed green on GitHub's own runner. All four defects it
took to get there were things a from-scratch review would have had a real chance of missing,
too — a self-matching grep, an `EXAMPLE`-blind git-history scan, a status doc quoting its own
forbidden string, and an unanchored gitignore rule silently eating a source package. None
were hypothetical; each was found by the exact mechanism designed to find it, on the first
real execution against a real clone.

**M1 — Domain model and authorization graph.** All five acceptance criteria demonstrated.
Delivered: `graph/builder.py` (G-3 monotone intent with the negative-control downgrade path,
G-4 catalog-closure half — the provider-binding half is explicitly M3's, see known issue 2 —
G-5 bounded depth; G-1/G-2 already lived on `AuthorizationGraph` since before M0);
`graph/divergence.py` (`edge_divergence`, `first_divergence`, `classify_drift` — all four
drift classes including `CORRECTED`, table-driven and verified against a naive
misclassification); `graph/paths.py` (`analyze_path`/`analyze_all_paths`, set- and
cardinality-monotonicity computed separately over measured pairs only); `core/canonical.py`
(sorted-key JSON, UTC ISO-8601 microsecond timestamps, verified identical across two
independent subprocess interpreters, not just two calls); `EdgeDivergence` added to
`core/models.py` alongside the pre-existing `DivergencePoint`/`PathAnalysis`. The
AUTHORIZATION_MODEL.md section 7 worked example is reproduced exactly as a shared pytest
fixture (`tests/conftest.py::worked_example_graph`) and used across the divergence, path and
first-divergence test files rather than duplicated in each.

Coverage forced a wider pass than M1's own file list: TESTING.md's acceptance bar
(`core/` and `graph/` both ≥95%, enforced per-package not globally) was 86% and 99%
respectively before M1 touched anything, because `core/secrets.py` (SI-1's primary
enforcement point) and most of `core/ids.py` had no dedicated test file, and roughly 50
validator/property branches across `core/models.py` were untested. None of that is M1's own
new code, but the acceptance criterion is a hard bar on the whole package, not just what a
milestone added, so `tests/unit/test_secrets.py`, `tests/unit/test_ids.py` and
`tests/unit/test_domain_models_extra.py` were added alongside the M1-proper files. `core/`
finished at ~99.5%, `graph/` at ~99%.

**M2 — Capability model and catalog.** All five acceptance criteria demonstrated. Delivered:
`capabilities/registry.py` (`BindingRegistry`, keyed by `(provider, capability_id)`, duplicate
registration rejected — F1); `capabilities/guard.py` (`OperationAllowlist`, a context manager
shaped for the AWS adapter's future botocore `before-call` hook — M8 — that raises
`CapabilityBroadeningError` on exit whenever a recorded operation fell outside the binding's
declared `actions`, verified to fire even when the probe body itself completed without its
own exception, and even when it raised for an unrelated reason — F3, SI-3);
`capabilities/preconditions.py` (`PreconditionRegistry` resolving precondition names to
verifier callables — F4; what a failed precondition means for an in-flight probe matrix is
explicitly the executor's job, M5+, and out of scope here). `tests/fixtures/bad_bindings.py`
supplies the wrong-provider, wrong-probe-kind, missing-precondition and
over-broad/extra-action fixtures the milestone's Tests section calls for, built against the
real `objectstore.read` catalog entry rather than a synthetic stand-in.

One resolution worth recording: the M2 spec's Tests section groups "an over-broad binding
(extra action)" alongside three `validate_binding`-rejection fixtures, which reads as if all
four should fail *compile-time* validation. But SECURITY_MODEL.md's own SI-3 description and
the milestone's negative-controls section both describe the over-broad case as a *runtime*
concern — a probe invoking an operation the binding never declared — which is exactly what
`OperationAllowlist` (not `validate_binding`) exists to catch. `validate_binding` has no
"actions exceed declared" check today because a *binding's own* `actions` list has nothing to
be over-broad relative to at compile time; only a probe's *invoked* operations can exceed it,
and only once probing exists. Implemented accordingly: the "over-broad" fixture is a normal,
fully valid binding (confirmed by its own `validate_binding` pass in
`test_binding_validator.py`), and the extra-action violation lives entirely in
`test_operation_allowlist.py`.

`capabilities/` had no dedicated test file before M2 (65% coverage, all incidental, from
other tests exercising `loader.py` in passing) against a 90% acceptance bar. Alongside the
M2-proper files, `test_capability_catalog.py`, `test_binding_validator.py` and
`test_catalog_safety.py` close the loader's own remaining gaps (a capability absent from the
catalog entirely, a `DANGEROUS`-capability binding, the restricted YAML loader's tag
rejection) as well as testing the new modules. `capabilities/` finished at 100%.

**M3 — Scenario language, validation and compiler.** All five acceptance criteria
demonstrated. Delivered: `scenarios/loader.py` (`validate_scenario`/`load_and_compile`,
orchestrating all five stages with their documented exit codes 0/2/3/4/5; stage 1's JSON
Schema check is generated in-memory from `ScenarioDocument.model_json_schema()` rather than
read from `schemas/`, so the loader has no runtime dependency on that directory existing
outside a repository checkout); `scenarios/compiler.py` (expected-authority derivation by
intersection with the redundant-`expect_capabilities` agreement check naming both values on
mismatch — F2; probe matrix construction honoring `declared`/`scenario`/`catalog` universes
with `identity.whoami` always included — F3; wires M1's `graph/builder.py` and M2's
`BindingRegistry`/`resolve_bindings` together, which is what actually closes the G-4
provider-binding gap known issue 3 has tracked since M1 — for scenarios compiled against a
populated registry); `scenarios/plan.py` (`SNAPSHOT` auto-inserted before and after every
`MUTATE` — F4); `scenarios/policy_synthesis.py` (size-checked, fingerprinted placeholder
policy artifacts against AWS's documented 2048-byte inline-session-policy ceiling — F7,
out-of-scope real policy JSON deferred to M8 by design). `core/models.py` gains
`CompiledScenario`, `ProbeMatrix`, `PlanStep`, `SynthesizedPolicy`, `CompileWarning`,
`CompiledExpectedFinding`.

A genuine finding, not a design choice: the milestone's own negative-controls section claims
compiling `nc-scope-expansion.yaml` produces a G-3 warning that disappears if
`suppress_graph_check` is removed. Empirically, neither is true — the scenario's *declared*
delegation graph never violates G-3 in the first place (hop-2's intended capabilities are
already a subset of agent-a's derived expected authority); the defect it validates is
injected at the infrastructure level (an inline IAM policy on agent-b's role, per the
scenario's own description), which is invisible to compile-time graph analysis by
construction. `suppress_graph_check` is implemented and independently verified to work (a
hand-built G-3-violating fixture proves the downgrade-to-warning path in
`tests/unit/test_scenario_loader.py`); it simply isn't exercised by this particular shipped
scenario. Acceptance criterion 4 ("nc-* scenarios compile with warnings, not errors") is
satisfied on the "not errors" half for all six; none carry a warning, which is correct given
where their defects actually live.

`scenarios/` was at 83% before M3 touched anything (schema.py 79%, export_schema.py 0% —
exercised only via a CI subprocess that pytest-cov can't see into) against a 90% bar.
`test_export_schema.py` and `test_scenario_schema_extra.py` (roughly thirty untested
Pydantic validator branches — every failure mode in every `ScenarioSpec` sub-model, none of
it new code) close the gap alongside the M3-proper `test_scenario_loader.py`,
`test_scenario_compiler.py`, `test_probe_matrix.py` and `test_scenario_safety.py`.
`scenarios/` finished at 98%.

**M4 — CLI, configuration and the SafetyGate.** All five acceptance criteria demonstrated.
Delivered: `config/settings.py` (`Settings`, `resolve_settings` — defaults → repo
`chainbreak.toml` → user config → `CHAINBREAK_*` env → CLI overrides, later wins field by
field, each layer contributing only what it explicitly set; `resolve_safety_envelope` wraps
Pydantic's `ValidationError` as the domain `SafetyEnvelopeError` F2 requires);
`config/fingerprint.py` (`fingerprint_settings`, reusing M1's canonical JSON); `core/safety.py`
(`SafetyGate.authorize` — envelope presence, account/region/namespace checks, and cost
estimation against a compiled plan; `estimate_cost`, verified conservative by a dedicated
test asserting the estimate is never below true-call-count × table, S4); `core/clock.py`
(`RunClock`, monotonic via an injectable `now_ns`, never wall-clock subtraction; the SI-7
14400s hard ceiling is enforced structurally on `SafetyEnvelope` itself, so it cannot reach
`authorize` in the first place); `cli/logging.py` (`RedactionFilter`, installed on the root
logger and directly on `botocore`/`boto3`/`urllib3` for defense in depth against a library
setting `propagate = False` on itself — SI-10); the full `cli/` Typer surface — `main.py`
plus one module per command group (`validate`, `scenario`, `run`, `analyze`, `report`,
`runs`+`evidence`, `infra`) — with every not-yet-implemented command exiting 2 with a named
milestone rather than a stack trace (F4).

Two gaps in `SafetyGate.authorize` surfaced only while writing tests against the milestone's
own list of what `test_safety_gate.py` must cover ("missing envelope, wildcard account,
disallowed region, namespace mismatch, cost over ceiling, duration over ceiling"): the
pre-existing implementation checked only `account_id` and cost, with no way to check a
candidate region or namespace against the envelope at all. Extended `authorize` with
`region`/`namespace` parameters, symmetric with the existing `account_id` check — region
against `envelope.allowed_regions`, namespace against `envelope.namespace_pattern` via
`re.fullmatch` — and added `RegionNotAllowedError` (new) while reusing the pre-existing
`NamespaceViolationError` (SI-2) rather than inventing a second namespace error. "Wildcard
account" and "duration over ceiling" turned out not to need new `SafetyGate` logic at all:
both are refused at `SafetyEnvelope` construction time by its own Pydantic validators, so
they collapse to the same `authorize(None, ...)` path as "missing envelope" — verified
directly rather than assumed.

The non-functional requirement — `chainbreak --help` under 500ms — was not met on first
measurement (949ms). Diagnosed via `python -X importtime` and manual timing splits: import
cost was the suspected cause (heavy modules like `pydantic`/`jsonschema`/the compiler sitting
at module level in `cli/validate.py` and `cli/scenario.py`, imported unconditionally by
`cli/main.py` on every invocation including `--help`) and deferring those imports into the
command bodies did help (949ms → ~650ms) but left the budget still missed. `-X importtime`
against the deferred version showed the actual remaining cost was not import time at all
(`chainbreak.cli.main` imports in ~180ms) — it was **Typer's rich-markup help renderer**,
which drives `rich`'s full layout engine over every option/command panel at *invocation*
time, independent of what got imported. Isolated with a minimal repro: the same Typer app
with `rich_markup_mode=None` rendered `--help` in 2.3ms versus 270ms with rich panels on.
Setting `rich_markup_mode=None` on the root `Typer()` app (it propagates to every sub-app)
brought `chainbreak --help` to a stable 340–390ms. Plain `Usage:`-style help output instead
of rich's colored panels is the tradeoff; `validate`'s own `rich.table.Table` output is
unaffected, since that's the command's own rendering, not Typer's `--help` machinery.

`test_cli_surface.py`'s bypass-flag detector (S1) uses duck typing
(`param.param_type_name == "option"`, `hasattr(command, "commands")`) rather than
`isinstance(cmd, click.Group)`: this environment's installed Typer (0.12+) vendors its own
internal fork at `typer._click`, distinct from the separately-installed top-level `click`
8.4.2 package, so `TyperGroup` does not satisfy `isinstance(..., click.Group)` against the
wrong module — confirmed directly (`isinstance` returned `False` for every node in the real
command tree) before switching approaches. The milestone's own negative-control instruction
("add `--skip-safety` on a scratch branch, confirm the test fails") was both reproduced as a
permanent, always-run fixture in `TestNegativeControlDetectorCatchesAPlantedBypassFlag` (a
scratch Typer app with a planted `--skip-safety` option, asserted caught) and demonstrated by
hand against the real `cli/run.py` — a `--skip-safety` option was added, `test_cli_surface.py`
was confirmed to fail with the exact offending flag named in the assertion message, then
reverted; `git status`/`git diff` confirmed a clean revert before continuing. `infra
apply`/`infra destroy`'s `--auto-approve` was deliberately not flagged: it mirrors `terraform
apply -auto-approve`'s standard non-interactive-confirmation convention (and `infra` is not
wired to the `SafetyGate` at all yet — stub until M9), not a safety bypass; a dedicated test
asserts the flag exists and does not match the bypass-keyword pattern, so this is a recorded
decision, not a gap the detector missed.

`cli/` had no dedicated test file before M4. Beyond the five files the milestone's own file
list names (`test_config_layering.py`, `test_safety_gate.py`, `test_clock.py`,
`test_logging_filter.py`, `test_cli_surface.py`), two more were added to cover ground the
file list didn't explicitly name but the acceptance criteria do: `test_cli_commands.py`
(acceptance criteria 1 and 5 — `chainbreak validate`'s six checks, each tested at the
function level plus one end-to-end `CliRunner` pass against a real config and the repo's own
scenario corpus from an isolated cwd; every not-yet-implemented command's exit-2 behavior)
and `test_cli_scenario_command.py` (`cli/scenario.py`'s `validate`/`list` commands, which had
real logic and only 24% incidental coverage from nothing exercising it directly).
`core/safety.py` finished at exactly 100% (acceptance criterion 4); `cli/` finished at 90%+
across every module except the two now-`--help`-only stub paths in `cli/main.py`.

**M5 — Provider Protocol and the deterministic fake laboratory.** All five acceptance criteria
demonstrated. Delivered: `providers/base/protocol.py` (`ProviderAdapter`, a `typing.Protocol` —
structural conformance, no shared base class, so neither `providers/fake` nor the future
`providers/aws` imports the other, matching the layered contract import-linter enforces);
`providers/base/types.py` (the *live* wire types one adapter call takes/returns —
`PreflightReport`, `EnvironmentDescriptor`, `DelegationRequest`/`DelegationResult`,
`ProbeRequest`/`ProbeResult` — deliberately distinct from the evidence-layer records already in
`core/models.py`; `ProbeResult` reuses `ProbeOutcome`/`ProbeTiming` wholesale rather than
duplicating their fields, and `DelegationResult` is a plain frozen dataclass, not a
`DomainModel`, because it carries a live `TemporaryCredential` that must never be pydantic-
serialized); `providers/base/namespace.py` (`assert_namespace`, SI-2's actual enforcement
point — substring containment against the run's namespace, called before every probe and
delegation).

`providers/fake/` is a real authorization engine, not a stub, matching F2-F8: `engine.py`
(`PolicyEngine` — explicit deny > explicit allow > implicit deny, session policy intersecting
never granting, resource policy able to grant across the intersection, the documented AWS
asymmetry); `session.py` (`SessionStore` — the chained-role 3600s duration cap, so
`CredentialRecord.lifetime_capped` is exercisable offline; credential ids and key material
drawn from a per-store seeded RNG, never `core.ids.new_ulid()`, which reads the wall clock and
would break F6 reproducibility); `consistency.py` (`ConsistencyModel`/`MutationVisibility` — a
virtual clock nothing in the fake ever sleeps against, propagation delay with seeded jitter,
and an oscillation mode that produces a genuinely non-monotonic visibility sequence, not just a
slow single flip); `bindings.py`/`probes.py` (one binding and one outcome-construction path per
capability, sharing the policy engine — `identity.whoami`'s control-capability exemption and a
failed-precondition's `ERROR_INFRASTRUCTURE` classification are both handled here, never as a
denial); `adapter.py` (`FakeProviderAdapter`, wiring all of the above behind the Protocol; the
one piece of state that lives here rather than in `engine.py` is the *pending mutation
transition* per identity — while a consistency-model window is open, `probe()` evaluates
against a captured pre-mutation snapshot via `PolicyEngine.evaluate_against`, not the
already-updated authoritative state, which is what lets `snapshot_policy_state` (the
bootstrap's fast confirmed read) and an agent's own `probe()` (subject to `propagation_delay_ms`
longer) disagree correctly during the window); `profiles.py` (`deterministic`/`eventual`/
`hostile`, F8).

Three things worth recording as genuine findings, not just design choices:

1. **A real bug, caught by the session's own smoke test before any test file existed for it.**
   `SessionStore.issue` originally minted its own `IdentityRef` (`fake:{account}:{identity_id}`,
   no namespace embedded) independently of `adapter._make_ref` (which does embed the namespace).
   Once `probe()`'s namespace assertion was tightened to check the *request's* declared
   namespace instead of a tautological check against the adapter's own namespace (see finding 2
   below), every probe against a delegated identity started failing `NamespaceViolationError`
   for a namespace that was in fact correct — the ref itself was simply built with a different,
   inconsistent shape. Fixed by making the adapter the single source of truth for ref
   construction: `SessionStore.issue` now takes a pre-built `identity_ref` parameter rather than
   minting its own, and no longer needs `account_ref`/`region` fields at all.
2. **The original namespace checks in both `probe()` and `delegate()` were tautological.**
   Each compared a value built from `self.namespace` against `self.namespace` itself — always
   true, catching nothing, ever. `probe()` now checks the caller-supplied `ProbeRequest.namespace`
   (a real, independent field) against the adapter's own namespace; `delegate()` checks the
   *caller's* (`request.source_identity`) ref rather than the target ref it is about to mint
   itself (which is in-namespace by construction and therefore nothing to check). Both fixes
   were verified with a direct reproduction — a request carrying a foreign namespace or a
   foreign account's ref — before any formal test existed, then locked in by
   `test_out_of_namespace_probe_refused_before_any_evaluation` and
   `test_out_of_namespace_delegation_refused` in the contract suite.
3. **A correctness bug in the pending-transition lifecycle, caught only once an oscillation
   test was written against the actual scheduled flip points rather than a fixed sampling
   grid.** `_decide_outcome` originally deleted `_pending[identity_id]` the first time
   `MutationVisibility.is_visible()` returned `True` — correct for a simple delayed transition,
   wrong for an oscillating one: the first `True` sample is a mid-window flip, not the final
   settled state, so deleting the pending entry there permanently stranded every later probe on
   authoritative (post-mutation) state regardless of whether the schedule called for a flip back.
   A grid-sampled test at 100ms resolution passed by accident (it happened not to land on a
   second flip for the seed used); rewriting the test to sample at the schedule's own recorded
   `oscillation_flips_ms` exposed the bug immediately. Fixed by only clearing the pending entry
   once `at_ms >= settle_at_ms` (fully, unconditionally settled), never merely because
   `is_visible()` happened to return `True`.

Two of M5's own artifacts are written as if a later milestone had already landed, the same
pattern M3's `nc-scope-expansion.yaml` finding established a precedent for:

- The verification command `chainbreak run scenarios/scope-attenuation/basic.yaml --provider
  fake --seed 1729` cannot run: `execution/orchestrator.py` (the actual run loop) is M10's
  deliverable, not M5's, per `docs/implementation/MILESTONES.md`'s own dependency graph and
  M10's milestone file naming it explicitly. `cli/run.py` remains M4's documented stub.
- The negative controls ("assert the eventual analysis reports `AUTHORITY_EXPANSION`"; "assert
  the measured transition window contains 2000ms") both name analysis (M7) and a poller (M12)
  that do not exist yet.

Rather than skip these, each was verified at the layer that actually exists today:
`tests/integration/test_fake_scenario_compatibility.py` compiles all 12 real scenarios (reusing
`synthetic_aws_registry`, the same synthetic-binding pattern M2/M3 tests already established)
and walks every identity, delegation edge and probe matrix through the fake adapter for all
three profiles — 36 parametrized cases, all crash-free, closing acceptance criterion 4 at the
provider layer M10's future orchestrator will call into.
`tests/unit/test_fake_provider.py::TestNegativeControlMechanisms` demonstrates the over-grant,
propagation-delay and oscillation mechanisms directly against the adapter, with an explicit note
that full classification (`AUTHORITY_EXPANSION`, `NON_MONOTONIC_TRANSITION`) is M7's/M12's job,
not M5's.

Acceptance criterion 3 (same seed ⇒ identical evidence) is proven in
`tests/unit/test_fake_determinism.py`: a realistic multi-step sequence — delegation through a
session-scoped credential, probes across all 10 capabilities, a policy mutation, probes again,
a snapshot — run against two independently constructed adapters with the same seed produces a
byte-identical canonical-JSON hash of the full observation stream, and (following the same
rigor `test_scenario_compiler.py` established for `compiled_hash`) identically across two
separate Python interpreter processes, not just two in-process calls.

`providers/base/` and `providers/fake/` had no dedicated tests before M5 (the packages did not
exist). `providers/base/` finished at 100%; `providers/fake/` at ~99.7% (both well above the
90% acceptance bar) — `providers/base/protocol.py`'s Protocol method stubs are marked
`# pragma: no cover` (a structural interface with `...` bodies is never meant to execute, the
same category `raise NotImplementedError`/`@overload` already get excluded for) and additionally
proven structurally sound via `@runtime_checkable` plus `isinstance(FakeProviderAdapter(),
ProviderAdapter)`.

### Implemented ahead of its milestone (design verification, not milestone completion)

The following exists and passes tests, but the corresponding milestone is **not** complete
because the milestone's full scope and acceptance criteria have not been met.

| Component | Belongs to | State |
|---|---|---|
| `schemas/*.json` — 11 generated schemas | M6 | Complete, all valid draft 2020-12 |
| `schemas/run-index.sql` | M6 | Complete, applies cleanly |

### In progress

None.

### Blocked

None. M6 can start immediately.

### Not started

M6 through M19. See [docs/implementation/MILESTONES.md](docs/implementation/MILESTONES.md).

---

## Tests

```
576 passed, 1 deselected in ~11s     (Python 3.12.7, pytest -m "unit or integration")
1 skipped, 576 deselected            (Python 3.12.7, pytest -m aws -- gated by CHAINBREAK_ALLOW_AWS_TESTS)
```

| Suite | Tests | Covers |
|---|---|---|
| `tests/unit/test_domain_contract.py` | 41 | Set algebra, secret non-serializability, safety envelope rejection, graph invariants G-1/G-2, divergence at node level, outcome classification, interval ordering, min-confidence, lifetime capping, catalog integrity, binding validation, SI-11 literal-infrastructure rejection, ULID monotonicity |
| `tests/scenarios/test_scenario_corpus.py` | 28 | Every scenario validates; capability closure (G-4); negative controls are correctly located and marked; all six defect kinds covered; all five families present |
| `tests/unit/test_import_boundaries.py` | 6 | ARCH-1: core imports nothing internal, graph imports only core, boto3 confined to `providers/aws/`, AWS service strings confined to `providers/` and `AWS_PROVIDER_SPEC.md`, plus two planted-violation negative controls |
| `tests/aws/test_placeholder.py` | 1 (skipped by default) | F5: proves the `aws`/`e2e` marker gate in `tests/conftest.py` actually skips, and actually un-gates under `CHAINBREAK_ALLOW_AWS_TESTS=1` |
| `tests/unit/test_divergence.py` | 17 | Per-edge divergence (both observed- and expected-baseline variants), the section 7 worked example reproduced exactly, `classify_drift` table including `CORRECTED`, `edge_divergence`'s unmeasured-endpoint guards |
| `tests/unit/test_first_divergence.py` | 10 | Single-node graphs, an unmeasured node reported rather than skipped, branching graphs analyzed independently, both M1-spec negative controls (hop-3-gain-propagates, hop-4-corrects) |
| `tests/unit/test_graph_invariants.py` | 9 | G-1 (cycle among non-root nodes) through G-5, each with a violating fixture naming the invariant, plus the G-3 negative-control downgrade path |
| `tests/unit/test_paths.py` | 6 | `PathAnalysis` over the worked example, single-node graphs, a non-monotone chain, an unmeasured node excluded from (not breaking) monotonicity, branching graphs |
| `tests/unit/test_canonical.py` | 15 | Sorted keys, fixed float formatting, `AuthoritySet` and nested-model rendering, UTC ISO-8601 with microseconds, naive-datetime rejection, identical output across two independent subprocess interpreters |
| `tests/unit/test_secrets.py` | 17 | Every `SecretMaterial` serialization path (pickle, Pydantic), `reveal`/`digest`/`constant_time_equals`, `TemporaryCredential.scrub()` irreversibility |
| `tests/unit/test_ids.py` | 15 | Every prefixed ID constructor, salting, ULID monotonicity including a simulated clock-backwards (NTP) step |
| `tests/unit/test_domain_models_extra.py` | 39 | Remaining `core/models.py` validators and properties (see the M1 entry under "Completed") |
| `tests/unit/test_capability_catalog.py` | 14 | All 10 capabilities load/validate/resolve against a test binding set, `BindingRegistry` register/get/duplicate-rejection/per-provider filtering |
| `tests/unit/test_binding_validator.py` | 8 | `validate_binding` against `bad_bindings.py`'s wrong-provider/wrong-probe-kind/missing-precondition/wrong-capability-id fixtures, plus `DANGEROUS` rejection and a catalog-absent capability in `resolve_bindings` |
| `tests/unit/test_operation_allowlist.py` | 8 | `OperationAllowlist` raises on an out-of-band operation even when the probe body raised nothing, and even when it raised something else first |
| `tests/unit/test_catalog_safety.py` | 9 | SI-9's config+CLI double switch (all four combinations), the restricted YAML loader rejecting an unknown tag and a non-mapping document |
| `tests/unit/test_preconditions.py` | 7 | `PreconditionRegistry` register/resolve/verify/verify_all, duplicate rejection, the provisioning identity is what gets passed to the verifier |
| `tests/unit/test_scenario_loader.py` | 21 | All 12 shipped scenarios compile; each of the four invalid fixtures yields its documented exit code (2/3/4/5); an orphaned (never-delegated-to) identity; `load_and_compile`'s exception and success paths |
| `tests/unit/test_scenario_compiler.py` | 8 | `compiled_hash` determinism across two calls and two independent subprocess interpreters, and that it changes with catalog version; F2 expected-authority derivation against the worked example; auto-inserted `SNAPSHOT`s around a real `MUTATE` phase; one `SynthesizedPolicy` per delegation; negative controls compile without errors |
| `tests/unit/test_probe_matrix.py` | 7 | `identity.whoami` in every universe; the `scenario` universe includes capabilities a node must *not* hold (the point of the default); `declared` is per-target-identity; `catalog` is everything; one matrix per `PROBE`/`DEFERRED_EXECUTION` phase; trials from the execution block |
| `tests/unit/test_scenario_safety.py` | 15 | Literal ARN/account-id/region/URL rejection (with `example`/`localhost` exempted); oversized documents; custom and `!!python/object` YAML tags rejected; invalid YAML syntax; non-mapping documents; excessive node count and nesting depth |
| `tests/unit/test_export_schema.py` | 7 | Every registered schema export is valid draft 2020-12; `main()` writes one file per export with the default and an explicit output directory |
| `tests/unit/test_scenario_schema_extra.py` | 40 | Every `ScenarioSpec` sub-model validator failure branch: timing/concurrency, root/agent capability declarations, session-policy source exclusivity, delegation mechanism and self-delegation checks, all five `PhaseSpec` kind requirements, all `ExpectationSpec` kind requirements, `ScenarioSpec`'s full referential-integrity sweep, negative-control id marking |
| `tests/unit/test_config_layering.py` | 18 | All four config layers individually and combined, later-wins semantics, a partial layer never clobbering an untouched field, env tuple/int/bool coercion, a `None` CLI override not overwriting an earlier layer, `resolve_safety_envelope` success/failure, fingerprint determinism |
| `tests/unit/test_safety_gate.py` | 16 | Missing envelope; wildcard account and duration-over-14400s both collapsing to the envelope-construction-refusal path; account/region/namespace checks (SI-2, SI-5, S1); cost within/over ceiling; `estimate_cost` conservatism (S4) against a real compiled scenario |
| `tests/unit/test_clock.py` | 12 | `RunClock` before/at/past its deadline via an injected fake monotonic source, `elapsed_seconds`/`remaining_seconds`/`expired`, the real `time.monotonic_ns` default path, `no_offset_estimator` |
| `tests/unit/test_logging_filter.py` | 14 | AKIA/ASIA keys, a simulated botocore DEBUG record with a JSON-quoted session token (acceptance criterion 3), key=value and JSON-quoted spellings, `install()` idempotence, third-party loggers covered even with `propagate = False` set on themselves |
| `tests/unit/test_cli_surface.py` | 5 | S1: no option anywhere in the real command tree matches a bypass keyword; `--auto-approve` deliberately not flagged (documented exception); the negative-control detector both catches a planted `--skip-safety` fixture and stays silent on a clean one |
| `tests/unit/test_cli_commands.py` | 28 | F3: each of `validate`'s six checks at the function level, plus an end-to-end `CliRunner` pass on a correct config (text and `--json`) and an informative failure on a missing one; F4: all thirteen not-yet-implemented commands exit 2 with "not implemented until M\<n\>", never a stack trace |
| `tests/unit/test_cli_scenario_command.py` | 6 | `chainbreak scenario validate`/`list` against a real scenario, a missing file, a structurally invalid document, the repo corpus, a missing directory, an empty directory |
| `tests/unit/test_namespace_guard.py` | 7 | `assert_namespace` exact/embedded/lookalike/empty-ref cases, error context carries both `namespace` and `ref` |
| `tests/unit/test_fake_policy_engine.py` | 16 | F2's full evaluation order: identity allow alone, explicit deny beating identity and session allow, session intersection never granting, resource policy granting across the intersection, `replace`/`apply_allow`/`remove_allow`, `evaluate_against` against an explicit snapshot with no registered identity at all |
| `tests/unit/test_fake_consistency.py` | 15 | Immediate/delayed/oscillating visibility, the 2000ms transition-window negative control, jitter staying within configured bounds, oscillation genuinely non-monotonic (a value reappears `True` after `False`), determinism (same seed -> identical schedule, different seed -> different jitter), `VirtualClock` never moving backwards |
| `tests/unit/test_fake_session.py` | 13 | Uncapped mechanisms unaffected, `ROLE_CHAIN`/`ROLE_CHAIN_WITH_SESSION_POLICY` capped at 3600s and reported (`lifetime_capped`), `max_session_duration_s` ceiling, credential liveness before/after expiry and after `revoke`, identical credentials from two independently constructed stores with the same seed |
| `tests/unit/test_fake_profiles.py` | 4 | `deterministic`/`eventual`/`hostile` each carry their documented parameters |
| `tests/unit/test_fake_provider.py` | 21 | `isinstance` against the `@runtime_checkable` Protocol; preflight region/namespace failure; unknown-capability resolution; throttle and transient fault injection; a revoked session denied on its next probe; all six `MutationKind` branches including the two built-in negative controls; the pending-transition lifecycle (in-flight, settled, folded-into-a-second-mutation); the three named negative controls (over-grant, propagation-delay bracketed to 1ms, oscillation) |
| `tests/unit/test_fake_probes.py` | 2 | A missing precondition marker produces `ERROR_INFRASTRUCTURE`, never a denial; a capability the identity policy grants but the session narrowed away is attributed `SESSION_POLICY`, not `IMPLICIT_NO_ALLOW` |
| `tests/unit/test_fake_determinism.py` | 4 | Acceptance criterion 3: a realistic multi-step sequence hashes identically for the same seed, differently for a different seed, identically across three independent in-process runs, and identically across two separate Python interpreter processes |
| `tests/integration/test_provider_contract.py` | 12 | The adapter-agnostic shared contract suite: preflight account check, namespace refused before any evaluation (probe and delegate), every capability classifies allow/deny correctly, the control capability never denied, delegation metadata carries no secret, mutation returns a confirmed receipt, protected-identity mutation refused, lifetime capping reported, snapshot fingerprints stable and change after a mutation |
| `tests/integration/test_fake_scenario_compatibility.py` | 37 | Acceptance criterion 4: every one of the 12 real shipped scenarios, compiled for real and walked (register, delegate along every edge, probe every matrix cell) through all three fake profiles, crash-free (36 parametrized cases) plus a corpus-count guard |

**Not yet written:** the AWS layer proper (M8), e2e layer (M9/M17), and the rest of the
unit suite described in [TESTING.md](TESTING.md) that covers modules later milestones will
add (`analysis/`, `evidence/`). CI is green on GitHub Actions (see the M0 entry under
"Completed" for the four real defects the first three runs found and the fixes that
followed, and the M1 entry for its own clean first-try run). The M4 push was observed green
on the first try — all 10 jobs, including the SI-5 SafetyGate coverage gate activating for
the first time (it had sat inactive, gated on `test_safety_gate.py` not existing, since M0)
and passing at 100% ([run 31211555428](https://github.com/KubixDesiney/chainbreak/actions/runs/31211555428)).
That run was also the first to observe M2 and M3's own additions, which had not yet had a
dedicated run at the time either was completed. The M5 push was also observed green on the
first try — all 10 jobs
([run 31216636287](https://github.com/KubixDesiney/chainbreak/actions/runs/31216636287)).

Coverage: `core/` ~99.5%, `graph/` ~99%, `capabilities/` 100%, `scenarios/` ~98%, `config/`
~99%, `cli/` ~96%, `providers/base/` 100%, `providers/fake/` ~99.7% (all exceed their
TESTING.md bars, where one is stated — 95%, 95%, 90%, 90% respectively; `config/`, `cli/` and
`providers/` have no stated bar in TESTING.md's per-module table, so M5's own 90% acceptance
criterion is the one actually gating `providers/`). `core/safety.py` is exactly 100%, its own
acceptance criterion. The SI-1 redaction `--cov-fail-under` gate in CI remains inactive because
`evidence/redaction.py` does not exist yet (M6); the SI-5 SafetyGate gate is active and
passing. Coverage is otherwise not enforced project-wide.

---

## Measured experiments

**None.**

| Family | Implemented | Run against fake | Run against AWS |
|---|---|---|---|
| Scope attenuation | no | no | no |
| Delegation drift | no | no | no |
| Revocation propagation | no | no | no |
| Stale authority | no | no | no |
| Silent narrowing | no | no | no |

Negative controls authored: 6 of 6. Executed: 0 of 6.

[docs/research/lab-log.md](docs/research/lab-log.md) is empty and will receive its first entry
at M17.

---

## Known issues

1. **No hash-locked lockfile yet (T-14).** M0 established a real, addressable development
   environment (a `.venv` under Python 3.12, not the prior ad hoc sandbox), but `pip install
   --require-hashes` and a committed lockfile are still outstanding. `pyproject.toml`
   dependency bounds are the only supply-chain control today; `pip-audit` runs in CI but a
   compromised transitive release between audits is still possible. Not blocking M1; should
   land before M8 pulls in `boto3`.
2. ~~`BindingRegistry` and `PreconditionRegistry` are empty at runtime, outside tests.~~
   **Half-resolved by M5, for the fake provider.** `providers/fake/bindings.py` and
   `providers/fake/probes.py` register real, production bindings and precondition verifiers
   for all 10 catalog capabilities into `FakeProviderAdapter.bindings`/`.preconditions` at
   construction time — not a test fixture, the actual adapter callers will use. The AWS half
   remains open until M8: compiling a real `provider: aws` scenario still requires supplying
   `tests/conftest.py::synthetic_aws_registry` (or an equivalent), since no production AWS
   binding exists yet.
3. ~~G-4's provider-binding half is not enforced.~~ **Resolved by M3.** `scenarios/compiler.py`
   calls `resolve_bindings` (M2) against the graph `graph/builder.py` (M1) already built,
   which is what full G-4 enforcement actually needed — a component able to import both
   `graph/` and `capabilities/`, which neither of those packages may do to each other
   (ARCH-1). All of G-1 through G-5 are now enforced for any scenario compiled against a
   populated registry (known issue 2 above is what "populated" depends on).
4. ~~`OperationAllowlist` is not wired to anything yet.~~ **Resolved by M5.**
   `providers/fake/adapter.py`'s `probe()` wraps every call in `OperationAllowlist`, recording
   the binding's declared action(s) — the first real (non-test) caller since M2 built the
   mechanism. The AWS adapter's botocore `before-call` hook (M8) remains the other intended
   caller and is still unbuilt; the fake's own call pattern always records exactly its own
   binding's actions, so today's wiring cannot itself observe a *cross-capability* mismatch
   (a caller passing a binding for one capability alongside a different declared
   `capability_id`) — worth a defensive assertion if that ever turns out to matter in
   practice, not added now since it is out of M5's scope.
5. ~~`chainbreak scenario validate` (the CLI) does not exist yet.~~ **Resolved by M4.**
   `cli/scenario.py`'s `validate` command wraps `scenarios.loader.validate_scenario` directly.
   One consequence carries forward from known issue 2, worth stating explicitly here since
   it is now user-visible rather than just a test-fixture concern: stage 4 (provider binding)
   always resolves against an empty `BindingRegistry` today, because no provider package has
   registered a real binding into one yet (M5 fake, M8 AWS). Running `chainbreak scenario
   validate` against any of the repo's real, structurally valid scenarios today exits 4
   (`EXIT_BINDING`), never 0 (`EXIT_VALID`) — this is correct current behavior, not a bug, and
   is why `chainbreak validate`'s own "scenarios" check (F3) treats `EXIT_BINDING` as
   informational rather than a failure until a provider exists.
6. **No `.tf` files exist.** Only contracts. `chainbreak infra *` will not work until M9. The
   `terraform` CI job is a structural no-op against an empty tree until then and has not been
   run locally (no `terraform` binary in the M0 development environment).
7. **`make` itself is not available in the M0 development environment.** `Makefile` targets
   were verified by running the commands each target wraps directly, not via `make lint`
   etc. Low risk (the targets are one-line wrappers) but genuinely unexercised.
8. **`nc-scope-expansion.yaml` carries a `suppress_graph_check: [G-3]` that the compiler
   never actually needs.** Its declared graph never violates G-3 (see the M3 entry under
   "Completed" for the full analysis); the field is harmless (downgrading a violation that
   isn't there is a no-op) but is either vestigial or defensive against a future edit. Not
   worth removing without operator sign-off, since it's a real committed scenario fixture and
   removing it changes nothing about current behavior either way.
9. **`chainbreak --help` renders plain `Usage:`-style output, not Typer's colored rich
   panels.** A deliberate tradeoff (M4, see the M4 entry under "Completed" for the
   measurement): rich's panel layout engine costs ~270ms per `--help` invocation regardless
   of import time, which alone blows the 500ms non-functional budget. `rich_markup_mode=None`
   on the root `Typer()` app trades the visual polish for a stable 340–390ms. `validate`'s own
   `rich.table.Table` output is unaffected — that is the command's own rendering, not Typer's
   `--help` machinery, and still renders in color.
10. **`chainbreak run` still exits 2 (M4's stub); `execution/orchestrator.py` does not exist.**
    M5's own verification command (`chainbreak run scenarios/scope-attenuation/basic.yaml
    --provider fake --seed 1729`) names a command that is not implementable until M10, per
    `docs/implementation/MILESTONES.md`'s dependency graph and M10's own file list
    (`execution/orchestrator.py`, `execution/matrix.py`, `execution/delegation.py`). See the
    M5 entry under "Completed" for how acceptance criteria 3 and 4 were verified instead, at
    the provider layer that exists today.

---

## Technical debt

Recorded now so it is deliberate rather than discovered later.

- **`AuthoritySet` is a Pydantic model wrapping a `frozenset`.** Slightly heavier than a bare
  frozenset. Kept deliberately: canonical ordering is what makes evidence diffable and
  hashable. Do not "optimize" it.
- **`ProbeCellResult.resolved` returns `self.trials[0]` for mixed denial attributions.**
  Correct for the current taxonomy but fragile if denial kinds proliferate. Revisit at M7.
- **JSON Schemas are generated but not yet diffed in CI.** The `schemas` job now runs
  `python -m chainbreak.scenarios.export_schema schemas && git diff --exit-code schemas/` in
  every CI run; whether it correctly blocks a real drifted PR is unverified until GitHub
  Actions runs it against a real drift, which has not happened yet.
- **`docs/research/` has a lab log and nothing else.** `results-v0.1.md` arrives at M17.

---

## External resources eventually required

| Resource | Needed from | Notes |
|---|---|---|
| A **dedicated** AWS account, no production workloads | M8 | Hard requirement; the allowlist admits no wildcard |
| An IAM identity able to assume the bootstrap and principal roles | M8 | SSO or OIDC preferred; never a static key |
| Terraform 1.7+ | M9 | |
| AWS spend | M8 | Under $1 for the full suite; Budgets alarm at $5 |
| A GitHub environment `aws-benchmark` with required reviewers | M17 | For the manually-dispatched experiment workflow |
| At least three separate time windows | M17 | Control C-7: timing trials must be distributed across blocks |

Nothing before M8 requires any of these. M0–M7 and M10–M16 are entirely offline.

---

## Current next action

**Implement M6 — Evidence pipeline, redaction and sealing.**

Prompt: [docs/CLAUDE_CODE_HANDOFF.md](docs/CLAUDE_CODE_HANDOFF.md) § M6.
Specification: [docs/implementation/milestones/M06-evidence-pipeline.md](docs/implementation/milestones/M06-evidence-pipeline.md).

M6 depends on M5 (complete) and is the highest-stakes milestone for SI-1 and EV-1: produce
sealed, schema-valid, secret-free evidence bundles, and make redaction structurally impossible
to bypass. `evidence/writer.py` (append-only JSONL streams, flushed per record so an aborted
run yields usable partial evidence — F2), `evidence/redaction.py` (the single choke point
every record passes through — this is what activates the SI-1 `--cov-fail-under=100` gate in
CI, currently inactive since the file does not exist), `evidence/manifest.py` (per-artifact
SHA-256 plus a root over sorted `name:hash` pairs — F3), `evidence/index.py` (SQLite run
index), `evidence/reader.py` (bounded, streaming, schema-validated ingest of a possibly-
untrusted bundle), `evidence/export.py` (`--public` scrub with a printed diff — F6). Once M6
lands, `chainbreak runs list|show|reindex` and `chainbreak evidence export` (M4's stubs) have
something real to wrap.

Before starting, confirm M0-M5's toolchain and domain/capability/scenario/CLI/provider layers
are intact:

```bash
pip install -e ".[dev,aws,report,analysis]"
ruff check . && ruff format --check .              # clean
mypy                                                # clean
lint-imports                                        # 6 contracts kept
pytest -m "unit or integration" -q                  # expect 576 passed, 1 deselected
pytest -m aws -q                                    # expect 1 skipped
pytest --cov=chainbreak.core --cov=chainbreak.graph --cov=chainbreak.capabilities \
  --cov=chainbreak.scenarios --cov=chainbreak.config --cov=chainbreak.cli \
  --cov=chainbreak.providers.base --cov=chainbreak.providers.fake \
  --cov-report=term-missing -m unit
     # expect core/ ~99.5%, graph/ ~99%, capabilities/ 100%, scenarios/ ~98%, config/ ~99%,
     # cli/ ~96%, providers/base/ 100%, providers/fake/ ~99.7%
chainbreak --help                                   # expect < 500ms
```

---

## Important decisions

Fourteen ADRs, indexed in [docs/DECISIONS.md](docs/DECISIONS.md). The four with the widest
blast radius:

- **[ADR-009](docs/adr/ADR-009-empirical-probing-over-policy-simulation.md)** — effective
  authority is determined by probing, not by policy simulation. Everything about the
  infrastructure, the markers and the disambiguation logic follows from this.
- **[ADR-006](docs/adr/ADR-006-observation-separated-from-conclusion.md)** — observation and
  conclusion are different objects with different lifetimes. This is what keeps the project
  from overclaiming.
- **[ADR-010](docs/adr/ADR-010-no-composite-score.md)** — no composite score. Six independent
  category results.
- **[ADR-012](docs/adr/ADR-012-unanimity-across-trials.md)** — unanimity, not majority voting,
  because a false expansion finding manufactured from noise is the most damaging error this
  benchmark can make.

---

## Update rules

- Update this file at the end of every milestone, in the same change as the work.
- Never move an experiment from "unmeasured" to "measured" without a run ID.
- Never mark a milestone complete unless every acceptance criterion passed and the
  verification commands were run.
- Record known issues and technical debt when they are created, not when they are noticed.
- README.md's status block must match this file. If they disagree, this file is right and the
  README is a bug.
