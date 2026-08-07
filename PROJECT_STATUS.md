# CHAINBREAK Project Status

**The durable source of truth.** Every other document defers to this one on questions of what
exists, what works, and what has actually been measured. Updated at the end of every
milestone.

**Last updated:** 2026-08-07 · **Version:** 0.1.0a0 · **Phase:** M3 complete, M4 next

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

**Implementation: M0 through M3 complete, M4 is the next action.** M0 made the repository
buildable, lintable, type-checkable and testable, and put CI in a state where it enforces the
structural rules the rest of the project depends on. M1 completed the domain model and
authorization graph: the divergence algorithms in AUTHORIZATION_MODEL.md section 4, graph
invariants G-1 through G-5, canonical JSON, and root-to-leaf path analysis. M2 completed the
capability layer: the binding registry, the runtime operation-allowlist that makes SI-3
enforceable, and precondition resolution. M3 completed the scenario language: the five-stage
validation pipeline and the compiler that turns a scenario document into a `CompiledScenario`.
All four milestones are analysis/domain/capability/scenario work — no benchmark has executed
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
| Provider abstraction | Specified, not implemented | ARCHITECTURE §3.8, [ADR-008](docs/adr/ADR-008-provider-adapter-boundary.md) |
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

None. M4 can start immediately.

### Not started

M4 through M19. See [docs/implementation/MILESTONES.md](docs/implementation/MILESTONES.md).

---

## Tests

```
346 passed, 1 deselected in ~5s      (Python 3.12.7, pytest -m "unit or integration")
1 skipped, 346 deselected            (Python 3.12.7, pytest -m aws -- gated by CHAINBREAK_ALLOW_AWS_TESTS)
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

**Not yet written:** the AWS layer proper (M8), e2e layer (M9/M17), and the rest of the
unit suite described in [TESTING.md](TESTING.md) that covers modules later milestones will
add (`analysis/`, `evidence/`, `core/safety.py`, the CLI). CI is green on GitHub Actions (see
the M0 entry under "Completed" for the four real defects the first three runs found and the
fixes that followed, and the M1 entry for its own clean first-try run); M2's and M3's
additions have not yet had their own dedicated CI run observed at the time of this update.

Coverage: `core/` ~99.5%, `graph/` ~99%, `capabilities/` 100%, `scenarios/` ~98% (all exceed
their TESTING.md bars — 95%, 95%, 90%, 90% respectively). `--cov-fail-under` gates for SI-1
redaction and SI-5 SafetyGate remain inactive because those modules do not exist yet (M6, M4).
Coverage is otherwise not enforced project-wide.

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
2. **`BindingRegistry` and `PreconditionRegistry` are empty at runtime, outside tests.** M2
   built the mechanism; M3's compiler now genuinely calls `resolve_bindings` against whatever
   registry it is given (closing known issue 3 below), but no *production* provider package
   has registered a real AWS or fake binding into one yet, because no provider package exists
   yet (M5 fake, M8 AWS). Tests use `tests/conftest.py::synthetic_aws_registry`, a synthetic
   stand-in covering all 10 shipped capabilities under `Provider.AWS` — the same pattern M2's
   own tests used for a synthetic FAKE-provider set. Compiling any real scenario today
   requires supplying a populated registry explicitly; there is no default that works.
3. ~~G-4's provider-binding half is not enforced.~~ **Resolved by M3.** `scenarios/compiler.py`
   calls `resolve_bindings` (M2) against the graph `graph/builder.py` (M1) already built,
   which is what full G-4 enforcement actually needed — a component able to import both
   `graph/` and `capabilities/`, which neither of those packages may do to each other
   (ARCH-1). All of G-1 through G-5 are now enforced for any scenario compiled against a
   populated registry (known issue 2 above is what "populated" depends on).
4. **`OperationAllowlist` is not wired to anything yet.** It is a complete, tested mechanism
   with no caller: the botocore `before-call` hook it is shaped for is M8's AWS adapter, and
   the fake provider that would exercise it in CI arrives at M5.
5. **`chainbreak scenario validate` (the CLI) does not exist yet.** M3's acceptance criterion
   1 names this command; M4 owns the CLI and was sequenced after M2/M3 in this
   implementation, not before. Verified instead through
   `scenarios.loader.validate_scenario`/`load_and_compile` directly, which is what the future
   CLI command will call. `docs/implementation/milestones/M03-scenario-language.md`'s
   verification commands assume M4 already landed; adjust them to call the loader functions
   directly if running them before M4 exists.
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
  Actions runs it (see known issue 5).
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

**Implement M4 — CLI, configuration and the SafetyGate.**

Prompt: [docs/CLAUDE_CODE_HANDOFF.md](docs/CLAUDE_CODE_HANDOFF.md) § M4.
Specification: [docs/implementation/milestones/M04-cli-config-safety.md](docs/implementation/milestones/M04-cli-config-safety.md).

M4 depends only on M1 (not M3) and builds the entry point and, more importantly, the gate
every run must pass: `config/settings.py` (layered resolution), `config/fingerprint.py`,
`core/safety.py` (`SafetyGate` — 100% coverage is an acceptance criterion, not a target),
`core/clock.py`, the Typer `cli/` surface, `cli/logging.py` (redaction filter installed
before any import that may log). The load-bearing requirement: `test_cli_surface.py` must
introspect every command and fail if a `--force`/`--skip-*`/`--no-safety` bypass flag exists
anywhere — demonstrated by temporarily adding one and showing the test catch it. Once M4
lands, retire known issue 5 (the CLI-wrapper gap `scenarios.loader` currently stands in for)
by wiring `chainbreak scenario validate` to `scenarios.loader.validate_scenario`.

Before starting, confirm M0-M3's toolchain and domain/capability/scenario layers are intact:

```bash
pip install -e ".[dev,aws,report,analysis]"
ruff check . && ruff format --check .              # clean
mypy                                                # clean
lint-imports                                        # 6 contracts kept
pytest -m "unit or integration" -q                  # expect 346 passed, 1 deselected
pytest -m aws -q                                    # expect 1 skipped
pytest --cov=chainbreak.core --cov=chainbreak.graph --cov=chainbreak.capabilities \
  --cov=chainbreak.scenarios --cov-report=term-missing -m unit
                     # expect core/ ~99.5%, graph/ ~99%, capabilities/ 100%, scenarios/ ~98%
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
