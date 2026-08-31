# CHAINBREAK Project Status

**The durable source of truth.** Every other document defers to this one on questions of what
exists, what works, and what has actually been measured. Updated at the end of every
milestone.

**Verification refresh:** 2026-08-16. Dedicated-account acceptance for M8/M9 passed live P1–P11,
all 21 AWS adapter tests, the wrong-account call-log gate, Terraform teardown, and service
enumeration. The shared contract behavioral assertions run unchanged with explicit AWS setup
hooks for its fixed Terraform roles. M17 has only invalid/incomplete apparatus attempts: zero
valid or publishable blocks and no M17 measurement.

**Last updated:** 2026-08-16 · **Version:** 0.1.0a0 · **Phase:** M0–M16 complete; M8/M9
dedicated-account acceptance complete; M17 has zero valid/publishable blocks; M18 offline
complete with real-AWS exercise pending; M19 not started.

---

## The honest headline

> **Status: 0.1.0a0 — M0–M16 are complete, including dedicated-account acceptance for M8
> (AWS provider adapter) and M9 (Terraform AWS sandbox). M17 has had invalid/incomplete
> apparatus attempts only: zero valid or publishable blocks and no M17 measurement. M18's
> offline reproducibility portion is complete; its real-AWS exercise remains pending. M19
> has not started. The offline baseline before this documentation pass was 1,772 passed
> tests.**

CHAINBREAK has a complete architecture, a verified domain model, a validated scenario corpus,
and a full implementation plan. The execution engine runs end to end against the deterministic
fake provider for all five benchmark families — an apparatus check, not an AWS benchmark result.
M15 turns that evidence into six independent category results, and M16 renders it into terminal,
Markdown, and self-contained HTML reports. M17 has no valid/publishable block, so no M17 result is
reported below.

### M8/M9 dedicated-account verification record — 2026-08-15

Evidence from the dedicated benchmark account, with account identifiers and raw response
content omitted:

- Live P1–P11 preflight: passed; Terraform apply: `44 added, 0 changed, 0 destroyed`.
- Second apply: no-op; Terraform fmt/validate, TFLint, the custom wildcard rule, and Checkov
  (`138 passed, 0 failed, 30 documented skips`): passed.
- AWS adapter suite: `21 passed` after extending the acceptance poll to cover the observed
  IAM propagation envelope and correcting the fixed-role contract test to use a non-terminal
  agent for `identity.delegate`; no semantic assertion was weakened.
- Wrong-account preflight call log: exactly `[GetCallerIdentity]`; no resource or IAM call was
  issued before the account gate failed.
- Disambiguation fixture suite: `24 passed`; scrubbed response-shape fixtures and provenance
  are under `tests/fixtures/provider_responses/`. They are documented AWS shapes, not live
  account captures.
- Real CLI cleanup contract: `2 passed` after granting the scoped
  `iam:ListInstanceProfilesForRole` permission and fixing apply's scrubbed no-op summary.
- Temporary inline mutation policies: removed. Service-specific post-destroy enumeration and
  `verify-clean`: zero remaining benchmark resources.
- Terraform destroy: two successful invocations, with the second a no-op; no manual IAM-role
  cleanup was required after the permission fix.
- Service-specific API enumeration and `verify-clean`: zero remaining benchmark resources.

---

## Current phase

**Architecture and specification: complete.** Twenty milestones specified with acceptance
criteria and verification commands. Fourteen ADRs accepted. Twelve security invariants defined
with named enforcement points. Fifteen threats modelled with seven accepted residual risks.

**Implementation: M0 through M16 complete. M8's AWS adapter and M9's Terraform sandbox both
passed dedicated-account acceptance, including all 21 AWS tests, the cleanup contract, and
zero-manual-step destroy. M10 (the
delegation-drift benchmark, Family B) are both complete against the fake provider — M10 was the
first milestone whose acceptance criteria required an actual end-to-end run to satisfy, not just
unit-level proof of the pieces; M11 extended the same execution engine to multi-hop chains and
found two real defects in already-existing M7-era analysis code by actually proving its
acceptance criteria against a deeper chain than any prior test used.** M0 made the repository
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
from a single seed. M6 completed the evidence pipeline: an append-only, flush-per-record bundle
writer; the `redact()` choke point every record passes through, with `evidence/redaction.py` at
exactly 100% coverage via a reflection-driven property test; SHA-256 sealing and root
verification; a disposable SQLite run index; a bounded, streaming, schema-validated reader for
untrusted bundles; and the `--public` export scrub. M7 completed analysis: cell resolution by
unanimity (ADR-012), the observed-authority/divergence/drift pipeline, the revocation-window
interval math, the six-row stale-authority classifier, the confidence gate, one rule function per
`FindingType`, the negative-control detector, and `analysis/pipeline.py` orchestrating a sealed
bundle into `findings.json` end to end, wired to `chainbreak analyze`. M8 built the AWS provider
adapter — preflight P1–P11, STS delegation for all five mechanisms, the ten capability probes
with content verification and denial-message disambiguation, the mutation choke point, retry with
full-jitter backoff, and policy snapshotting — verified against moto-emulated AWS resources and,
for the message-parsing logic, against literal AWS error strings; its dedicated-account acceptance
passed with no unresolved adapter denial/ambiguity failures. M9 wrote all five Terraform modules
(`benchmark-account`, `resources`, `identities`, `delegation`, `observability`) and both
environments (`aws-sandbox`, `local-development`) to their contracts, plus a real
`cli/infra.py` wrapping `plan`/`apply`/`destroy`/`status`/`verify-clean`; `terraform fmt -check
-recursive` and `terraform validate` pass locally for every module and environment (a genuine
capability gain over M0's "no terraform binary in the development environment" — a binary was
downloaded and a filesystem-mirrored provider plugin set up for this milestone specifically),
and its dedicated-account apply/destroy contract now passes. M10 built the execution engine — `execution/orchestrator.py`, `matrix.py`, `delegation.py`,
`preconditions.py`, `control.py` — and wired `chainbreak run` for real against the fake provider:
`scope-attenuation/basic.yaml` runs end to end producing a sealed bundle and findings, both
scope-attenuation negative controls are detected, and the probe-order seed (C-6) is recorded and
reproducible. M11 extended execution to multi-hop chains (`execution/chain.py`) and added the
depth-sweep confound treatment (`analysis/drift.py`, F6: divergence as a rate per hop, exclusions
per depth, `INCONCLUSIVE` when both rise together) — depths 2 through 6 all run end to end and
`chainbreak analyze --aggregate --scenario-family delegation-drift` reports the sweep. Most of
M11's drift-classification algorithms already existed from M1/M7; its own real contribution was
finding and fixing a citation-chaining bug and an unwired path-analysis output in that existing
code, caught only by running a genuinely deeper chain than any prior test exercised. M12 built
the revocation-propagation benchmark (Family C) — `execution/mutation.py`, `polling.py` and
`revert.py`, and the `CompiledScenario.mutation_plans`/`poll_plans` compiler output that feeds
them — wiring the `MUTATE`/`POLL`/`SNAPSHOT` `PhaseKind` branches `execution/orchestrator.py`
had deliberately left as named-milestone stubs since M10. The revocation-window interval math and
the `_revocation_findings` analysis wiring both already existed from M7; M12's real contribution
was the execution layer that actually produces the events and polled observations that math
consumes, plus a revert log written before every mutation (F8) and reverted from the
orchestrator's own `finally` block regardless of how the run ends. M13 built the stale-authority
benchmark (Family D) — `execution/deferred.py`, `execution/credential_store.py`,
`analysis/stale.py` — wiring the last two named-but-stubbed `PhaseKind` branches
(`WAIT`/`DEFERRED_EXECUTION`) `execution/orchestrator.py` had left since M10. Its own real
contribution is entirely about *making the paired fresh-credential comparison actually
distinguishable from noise*: `classify_stale_authority` (M7's six-row table) and
`StaleAuthorityMeasurement` already existed, but a naive execution layer built straight against
the fake's M5-era mutation-visibility model cannot ever produce a genuine
`STALE_AUTHORITY_LIVE_CREDENTIAL` result — see M13's own "genuine findings" below. M14 built the
silent-narrowing benchmark (Family E) — `execution/workers/{base,deterministic}.py`,
`execution/task_runner.py`, `execution/side_effects.py`, `analysis/task_contract.py` — wiring the
last named-but-stubbed `PhaseKind` branch (`TASK`) `execution/orchestrator.py` had left since M10,
so every member of the enum now has a real branch. Its own real contribution mirrors M13's: the
`TaskWorker` Protocol and four deterministic workers are new, but the core detection mechanism —
independent side-effect verification never trusting a worker's self-report — only works because
`execution/task_runner.py` computes `redelegation_attempts`/`substituted_capabilities` from its
own objective invocation log rather than the worker's returned claim, the same "never trust
self-report for anything independently observable" discipline F4 already applies to the output
marker; see M14's own "genuine findings" below for what a naive implementation would have gotten
wrong. M15 built per-category scoring — `scoring/{categories,coverage,confidence,aggregate}.py` —
the six independent `CategoryResult` evaluators SCORING_MODEL.md section 2 defines, each funnelled
through one shared `_finalize` helper that applies F2 (zero applicable cells is `NOT_MEASURED`,
never `CONSISTENT`), F3 (`coverage < 0.7` forces `PARTIAL`, overriding even a would-be `DIVERGENT`
verdict — also enforced a second time as a `CategoryResult` model validator, redundant by design),
F4 (confidence is `min()` across the category's own coverage and every contributing finding,
reusing `core/models.py::min_confidence`) and S2 (a negative control's detector failure forces
`DETECTOR_FAILED` last, overriding everything computed above it) identically across all six.
`scoring/aggregate.py` adds cross-run aggregation (F7/F8): refuses to combine runs whose
`compiled_hash`/`adapter_version`/`catalog_version` differ unless `--allow-heterogeneous` is
passed, reports n/median/IQR/min/max with no dispersion below n=5, and counts excluded runs by
reason rather than dropping them silently. `cli/analyze.py` now writes `scores.json` alongside
`findings.json` on every `chainbreak analyze <run-id>`, prints the literal sentence "NOT_MEASURED
is not a pass." whenever at least one category was not exercised, and gained
`--aggregate-scores --scenario-id <id> [--allow-heterogeneous]` for the cross-run path. Building
M15 surfaced two real findings, neither of which is M15's own defect: three of the six
negative-control scenarios (`nc-scope-expansion`, `nc-non-monotone-chain`,
`nc-surviving-authority`) inject their defect only through a `mini_orchestrator.py` test-only hook
or a Terraform infrastructure profile, so a genuine `chainbreak run --provider fake` never
triggers them and `chainbreak analyze` correctly reports `DETECTOR_FAILED` for each — S2 doing
exactly what it exists to do, not a scoring bug (flagged as a follow-up, not fixed here, since the
fix belongs in the fake provider or scenario compiler, out of M15's own file list); and
`analysis/stale.py` now populates `StaleAuthorityMeasurement.stale_window_seconds` from the
mutation send instant; `scoring/categories.py` consumes that value. M16 renders that same
evidence into terminal, Markdown and self-contained HTML reports —
`reporting/language.py` implements EXPERIMENT_PROTOCOL.md section 7's language rules as a lint
every renderer calls before returning rather than a convention renderers are merely asked to
follow; `reporting/figures.py` builds seven figure kinds as hand-built inline SVG rather than
Plotly (a deviation recorded in the module's own docstring — Plotly's only self-contained
rendering paths each violate a harder requirement the milestone states in the same breath); HTML
keeps Jinja2 autoescape on with no `|safe` anywhere in the template, verified by a grep-based
test, since a third-party bundle's `security_interpretation` is a plausible XSS vector into the
rendered page. M0 through M9 are domain/capability/scenario/CLI/provider-laboratory/evidence/
analysis/AWS-adapter-offline/Terraform-local work; M10 through M14 are the milestones that
actually execute something end to end — against the fake provider only; M15 and M16 are both
downstream of that evidence rather than producing more of it. M17 has no valid or publishable
five-family dedicated-account block; all incomplete attempts are recorded as superseded/excluded
apparatus evidence in the lab log.
M18's offline portion — `chainbreak compare`'s three-level classification, `--archive`, the
migration framework, a verified-deterministic Docker image, and a hash-locked
`requirements.lock` enforced with `--require-hashes` in CI — is also complete, ahead of
M18-reproducibility-hardening.md's own listed dependency on M17: `docs/implementation/
NEXT_PROMPTS.md`'s P2 prompt scopes this deliberately, since Level 2/3 comparison logic "can be
exercised against two fake-provider runs with different seeds," which needs no AWS account to
validate; only the real-AWS half of that comparison remains blocked on M17.

---

## Architecture status

| Area | Status | Authority |
|---|---|---|
| Layer map and dependency rule | Complete | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Domain model | Complete **and verified in code** | [AUTHORIZATION_MODEL.md](AUTHORIZATION_MODEL.md), `core/models.py` |
| Authorization graph and divergence algorithms | Complete **and verified in code** — G-1–G-5, all section 4 algorithms, canonical JSON | AUTHORIZATION_MODEL §2, §4, `graph/`, `core/canonical.py` |
| Capability model | Complete **and verified in code** — catalog v1.0.0/10 capabilities, registry, operation allowlist (SI-3), preconditions | [CAPABILITY_MODEL.md](CAPABILITY_MODEL.md), `capabilities/` |
| Scenario language v1alpha1 | Complete **and verified in code** — full five-stage pipeline, compiler, all 20 scenarios compile | [SCENARIO_SPECIFICATION.md](SCENARIO_SPECIFICATION.md), `scenarios/` |
| Evidence schema | Complete; 11 JSON Schemas generated and validated | [EVIDENCE_SCHEMA.md](EVIDENCE_SCHEMA.md) |
| Evidence pipeline | Complete **and verified in code** — writer, `redact()` (100%), manifest sealing/verification, SQLite index, bounded reader, `--public` export | `evidence/` |
| Analysis | Complete **and verified in code** — authority aggregation (ADR-012 unanimity), divergence/drift, revocation-window math, stale-authority classification, confidence gate, finding rules, negative-control detector, end-to-end `findings.json` pipeline, `chainbreak analyze` | [AUTHORIZATION_MODEL.md](AUTHORIZATION_MODEL.md), `analysis/` |
| Config, SafetyGate, CLI | Complete **and verified in code** — layered config resolution, `SafetyGate` at 100% coverage, monotonic run clock, redaction filter, full `chainbreak` Typer surface | [M04-cli-config-safety.md](docs/implementation/milestones/M04-cli-config-safety.md), `config/`, `core/safety.py`, `core/clock.py`, `cli/` |
| Provider abstraction | Complete **and verified in code** — `ProviderAdapter` Protocol, live wire types, `assert_namespace` (SI-2) | ARCHITECTURE §3.8, [ADR-008](docs/adr/ADR-008-provider-adapter-boundary.md), `providers/base/` |
| Fake provider laboratory | Complete **and verified in code** — real policy engine, session lifetimes, injectable consistency model, 10/10 capability bindings, 3 named profiles, all 23 scenarios walk without crashing; M13 added an opt-in per-credential authority-caching mode (`enable_authority_caching`), never active for M10-M12 scenarios | ARCHITECTURE §3.9, `providers/fake/` |
| AWS provider | Implemented and verified offline; dedicated-account acceptance passed all 21 AWS tests and the wrong-account call-log gate; no valid M17 experiment result | [AWS_PROVIDER_SPEC.md](AWS_PROVIDER_SPEC.md), `providers/aws/` |
| Terraform | All five modules + both environments implemented; dedicated-account apply/destroy/no-op/verify-clean acceptance passed | `infra/terraform/`, [M09-terraform-sandbox.md](docs/implementation/milestones/M09-terraform-sandbox.md) |
| Execution engine (Family A: scope attenuation; Family B: delegation drift; Family C: revocation propagation; Family D: stale authority; Family E: silent narrowing) | Complete **and verified in code, run end to end** — phase loop against the full `PhaseKind` enum, every member with a real branch as of M14 (`PROBE`/`SNAPSHOT`/`MUTATE`/`POLL`/`WAIT`/`DEFERRED_EXECUTION`/`TASK`), C-1/C-2/C-6/F6 controls, multi-hop chains to depth 6, all five revocation mechanisms with a pre-mutation revert log and `finally`-block reversion, paired pinned/fresh-credential probes with unconditional re-delegation for the fresh leg, four deterministic task workers with independent side-effect verification, `chainbreak run` wired (including `--fake-profile`) — **against the fake provider only; never run against AWS** | ARCHITECTURE §3.11, [M10-scope-attenuation.md](docs/implementation/milestones/M10-scope-attenuation.md), [M11-delegation-drift.md](docs/implementation/milestones/M11-delegation-drift.md), [M12-revocation.md](docs/implementation/milestones/M12-revocation.md), [M13-stale-authority.md](docs/implementation/milestones/M13-stale-authority.md), [M14-silent-narrowing.md](docs/implementation/milestones/M14-silent-narrowing.md), `execution/` |
| Delegation-drift analysis (Family B) | Complete **and verified in code, run end to end** — per-hop drift classification and cause-citation chaining (any depth, not only the origin's immediate child), first-divergence-per-path wired into analysis output, F6's rate-per-hop/exclusion-rate depth-sweep aggregation with an explicit `INCONCLUSIVE` verdict | AUTHORIZATION_MODEL §4.4-4.5, [M11-delegation-drift.md](docs/implementation/milestones/M11-delegation-drift.md), `analysis/drift.py` |
| Revocation-propagation execution (Family C) | Complete **and verified in code, run end to end** — `MutationPlan`/`PollPlan` compiled from scenario `MUTATE`/`POLL` phases, serial polling with `STABLE_DENIAL`/`STABLE_ALLOW`/`TIMEOUT` stability detection, an unconfirmed mutation receipt aborting the run (F4), pre-mutation policy snapshots, revert log written before every mutation and reverted in a `finally` block regardless of outcome (F8/F9) — the interval math and finding rules that consume the resulting evidence already existed from M7 | AUTHORIZATION_MODEL §5.1, [M12-revocation.md](docs/implementation/milestones/M12-revocation.md), `execution/mutation.py`, `execution/polling.py`, `execution/revert.py` |
| Stale-authority execution and analysis (Family D) | Complete **and verified in code, run end to end** — `execution/credential_store.py` (per-phase credential registry), `execution/deferred.py` (`WAIT` via virtual-clock advance, `DEFERRED_EXECUTION`'s pinned-then-fresh probe pair), `analysis/stale.py` (pairs `DEFERRED_EXECUTION`/`PAIRED_FRESH_CREDENTIAL` observations by identity+capability, reads `DELETE_SESSION_POLICY_SCOPE` mutation events for `SESSION_SCOPE_CACHED`) — the six-row classifier and `StaleAuthorityMeasurement` already existed from M7; the fake adapter gained an opt-in per-credential authority-caching mode (never active outside a `DEFERRED_EXECUTION` phase) that is what makes `STALE_AUTHORITY_LIVE_CREDENTIAL` genuinely, deterministically distinguishable from "not yet propagated" rather than a race against `propagation_delay_ms` | AUTHORIZATION_MODEL §5.2, [M13-stale-authority.md](docs/implementation/milestones/M13-stale-authority.md), `execution/deferred.py`, `execution/credential_store.py`, `analysis/stale.py` |
| Silent-narrowing execution and analysis (Family E) | Complete **and verified in code, run end to end** — `execution/workers/base.py` (`TaskWorker` Protocol, defined purely over a capability-invoker and a `TaskOutcome`, ADR-007), `execution/workers/deterministic.py` (four workers: `sequential`, `always-complete`, `substituting`, `redelegating`), `execution/task_runner.py` (the capability-invoker every worker is confined to — S1 — and the objective invocation log that overrides `redelegation_attempts`/`substituted_capabilities` rather than trusting either worker self-report), `execution/side_effects.py` (independent bootstrap-attributed marker verification, F4), `analysis/task_contract.py` (up to three distinct findings per task — `SILENT_NARROWING`, `CAPABILITY_SUBSTITUTED`, `REDELEGATION_ATTEMPTED`, two new `FindingType` members added this milestone — never collapsed into one) | AUTHORIZATION_MODEL §6, [M14-silent-narrowing.md](docs/implementation/milestones/M14-silent-narrowing.md), `execution/workers/`, `execution/task_runner.py`, `execution/side_effects.py`, `analysis/task_contract.py` |
| Scoring | Complete **and verified in code, run end to end** — six independent `CategoryResult` evaluators (F1), NOT_MEASURED/PARTIAL/DIVERGENT/DETECTOR_FAILED status rules (F2/F3/S2), min-aggregated confidence (F4), cross-run aggregation refusing heterogeneous compiled_hash/adapter_version/catalog_version (F7/F8), `chainbreak analyze` writes `scores.json` and `--aggregate-scores`; no composite score anywhere (ADR-010) | [SCORING_MODEL.md](SCORING_MODEL.md), [M15-scoring.md](docs/implementation/milestones/M15-scoring.md), `scoring/` |
| Reporting | Complete **and verified in code, run end to end** — terminal (`rich`), Markdown and self-contained HTML (Jinja2, autoescape on, no `|safe`) all render from a real fake-provider bundle; `reporting/language.py`'s EXPERIMENT_PROTOCOL §7 lint enforced at render time (`enforce_report`), not left to operator discipline; seven evidence-derived figures as inline SVG; every finding renders observation/expected_state/observed_state/security_interpretation under separate headings (ADR-006); `provider: fake` stamped in the header and every figure caption | ARCHITECTURE §3.16, [M16-reporting.md](docs/implementation/milestones/M16-reporting.md), `reporting/` |
| Reproducibility tooling | Offline portion complete **and verified in code** — three-level `chainbreak compare` (`analysis/compare.py`), self-contained `--archive` (`evidence/archive.py`), the bundle-migration framework (`evidence/migrate.py`), a 68 MB Docker image verified to run genuinely determinism-preserving fake-provider scenarios, a 90-package hash-locked `requirements.lock` verified with `pip install --require-hashes` in a clean Linux container — **real-AWS Level 2/3 comparison and real-AWS archive/migrate exercise not yet done, blocked on M17** | [REPRODUCIBILITY.md](REPRODUCIBILITY.md), [M18-reproducibility-hardening.md](docs/implementation/milestones/M18-reproducibility-hardening.md), `analysis/compare.py`, `evidence/archive.py`, `evidence/migrate.py` |
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

**M6 — Evidence pipeline, redaction and sealing.** All five acceptance criteria demonstrated.
Delivered: `evidence/redaction.py` (`redact()` — the single serialization choke point every
record passes through before touching disk; raises `SecretLeakError` on a hit rather than
sanitizing (S2); two independent pattern families — secret-shaped credential patterns that are
fatal, and identifier-shaped ARN/hostname/account-id patterns that `redact_message()` substitutes
in place, preserving sentence structure per ADR-013); `evidence/manifest.py` (`Manifest`,
per-artifact SHA-256 plus a root over sorted `name:hash` pairs — F3 — `seal()`/`verify()`);
`evidence/writer.py` (`BundleWriter` — append-only `.jsonl` streams flushed per record, so a
killed process still leaves a usable partial bundle — F2; the only module in `evidence/` that
opens a file for writing, enforced by a grep-based test so `evidence/export.py` funnels its own
writes through `write_text_artifact` rather than touching the filesystem directly — S1);
`evidence/index.py` (the SQLite run index — schema embedded as a literal copy of
`schemas/run-index.sql`, checked byte-identical by a dedicated test rather than read from disk at
runtime, matching the precedent M3 set for `scenarios/loader.py`; `reindex()` rebuilds it from
bundles alone — F5); `evidence/reader.py` (bounded, streaming, schema-validated ingest of a
possibly-untrusted bundle — T-10 — a per-line byte cap so a hostile `.jsonl` line cannot exhaust
memory before its own size is even checked, `json.loads` only, never `eval`); `evidence/export.py`
(`export_public` — F6 — scrubs ARNs, hostnames, bare account IDs and policy documents from a
sealed bundle, re-scans its own output before writing anything, and prints a diff of what it
stripped). `evidence/verify.py` is an additional convenience module, not in M6's required file
list: a thin `python -m chainbreak.evidence.verify <run_dir>` wrapper matching the milestone's own
verification-commands section literally.

`cli/runs.py`'s five M4 stubs (`runs list|show|reindex`, `evidence export`) now wrap the real
implementation instead of exiting 2; `evidence export` without `--public` remains a documented
stub, since only the public-scrub path is in M6's scope. `tests/unit/test_cli_commands.py`'s
generic "not implemented until M`n`" sweep was updated to drop the four resolved commands, with
their real behavior covered by the new `tests/unit/test_cli_runs_command.py` — the same pattern
M4 established for `cli/scenario.py`.

Three genuine findings, not design choices:

1. **`AuthoritySet` could be written but not read back.** `core/canonical.py` has, since M1,
   deliberately serialized `AuthoritySet` as a bare sorted list rather than its actual
   `{"capabilities": [...]}` field shape, for evidence diffability. Nothing before M6 ever needed
   to read that format back — M5's fake-provider tests only ever *write* through `canonical.dumps`
   for hashing — so the asymmetry was latent until `evidence/reader.py` became the first code to
   round-trip a bundle: `CredentialRecord.model_validate()` on a freshly-written
   `credentials.jsonl` line failed with `Input should be a valid dictionary or instance of
   AuthoritySet`, caught immediately by `test_golden_bundle_credentials_match_credential_schema`
   before any fixture was hand-massaged to hide it. Fixed at the source rather than worked around
   in the reader: `AuthoritySet` gained a `model_validator(mode="before")` accepting its own
   canonical list rendering as an alternate input shape, so the type is symmetric in both
   directions. All 576 pre-existing tests continued to pass unmodified — the change only *adds*
   an accepted input shape, never narrows one.
2. **The ARCH-1 literal-AWS-string boundary needed the same, already-precedented exception
   twice more.** `test_import_boundaries.py::test_no_aws_service_strings_outside_allowed_paths`
   (added at M0, a merge gate) failed the moment `evidence/redaction.py`'s ARN-shape regex and
   `evidence/writer.py`'s error message (`"already exists:"`, which contains the substring
   `sts:`) existed. The regex hit was a real instance of a category the test already carves out
   an exception for — `scenarios/safety.py` needs to recognize an ARN shape to reject it under
   SI-11, "a different thing from the rest of the engine depending on AWS semantics," per that
   test's own comment — and `evidence/redaction.py`/`evidence/export.py` need the identical
   recognition for SI-1/T-13, so both were added to the existing allowed-paths list rather than
   weakening the check. The `writer.py` hit was a coarse-regex false positive (`"exists:"` is not
   an STS reference); fixed by rewording the message, not by touching the boundary rule.
3. **A bundle sealed on Windows did not verify on Linux.** The first push (run
   [31240770166](https://github.com/KubixDesiney/chainbreak/actions/runs/31240770166)) failed
   `test` on both 3.12 and 3.13 with `root_verified: False` for the committed golden fixture —
   `manifest.verify()` returning `False` for a bundle that verified locally every time. The cause:
   `BundleWriter` opened its `.jsonl` streams and `write_text_artifact` opened its target files
   without `newline=""`, so Python's universal-newline translation wrote `\r\n` on the Windows
   machine the fixtures were generated on. `hash_file()` reads raw bytes, so the sealed hashes were
   computed over that `\r\n` content. Locally, re-cloning the repo on the *same* Windows machine
   re-triggered `core.autocrlf=true`'s checkout-side LF→CRLF conversion, silently reproducing the
   same bytes and making local verification pass by symmetric coincidence — the local re-check was
   not actually independent. On the Linux CI runner, git checks out the stored blob (already
   normalized to LF on commit) without re-converting, so the bytes genuinely differed from what was
   sealed, and `verify()` was correctly reporting real corruption, not a false alarm. Fixed at the
   source (`newline=""` on every write in `evidence/writer.py`, both the JSONL streams and
   `write_text_artifact`) and by regenerating `tests/fixtures/bundles/{golden,tampered}/` with the
   corrected writer; `test_writer_never_writes_crlf` locks the invariant in. The `security` job on
   the same push separately caught the synthetic secret corpus in `test_redaction.py` using
   non-EXAMPLE-exempted AKIA/ASIA-shaped strings — CI's T-01 tree-and-history scan only exempts a
   line containing the literal word `EXAMPLE` (see the M0 entry's own description of this
   mechanism); fixed by switching to the AWS-documented example access-key shape
   `test_logging_filter.py` already established elsewhere in the suite (prefix, seven-character
   account hint, then the literal word the exemption looks for) rather than an arbitrary
   16-character suffix. Both were real defects a from-scratch review had
   a genuine chance of missing, caught by the exact mechanisms designed to catch them, on the first
   real execution against a real clone — the same pattern M0's own four defects followed.

`evidence/` had no dedicated tests before M6 (the package did not exist). Delivered:
`test_redaction.py` (the property-based, reflection-driven sweep required by acceptance criterion
2 — every `DomainModel` subclass in `core/models.py` discovered by `inspect.getmembers`, every
field reflection identifies as unconstrained free text populated from a synthetic secret corpus
of six shapes — AKIA/ASIA keys, a JWT, a PEM block, a base64 blob, a session-token shape —
asserting `redact()` either raises or the secret appears nowhere in the canonical serialization;
plus focused regressions proving `sha256:`-digests, ULIDs and full git commit SHAs are never
false positives, since every hash field in the schema depends on that), `test_evidence_schema.py`,
`test_sealing.py`, `test_bundle_ingest_safety.py`, `test_public_export_scrub.py`,
`test_evidence_index.py`, `test_evidence_reader.py`, `test_evidence_verify_cli.py`,
`test_cli_runs_command.py`. `tests/fixtures/bundles/{golden,tampered,malicious}/` were generated
via a one-off script driving the real `BundleWriter` (golden), a single-byte tamper of the golden
copy leaving `manifest.json` untouched (tampered), and hand-crafted oversized/malformed `.jsonl`
lines (malicious) — not committed as a generator, since M6's file list names the fixture
directories themselves, not a script.

`evidence/redaction.py` finished at exactly 100% (acceptance criterion 2, S4); the rest of
`evidence/` finished at 94–100% per module (`writer.py`/`manifest.py`/`export.py`/`verify.py`
100%, `reader.py` ~98%, `index.py` ~94%) — all comfortably above the 90% bar TESTING.md sets for
modules without a stated bar, the same category `providers/` fell into at M5.

**M7 — Analysis, findings and the confidence gate.** All five acceptance criteria demonstrated.
Delivered: `analysis/authority.py` (`resolve_cell` — unanimity per ADR-012, all-`ALLOWED` ⇒
`ALLOWED`, mixed-kind denials ⇒ `DENIED_UNATTRIBUTED`, mixed-anything-else ⇒ `INDETERMINATE`;
`aggregate_observations`/`build_observed_authority`/`populate_observed_authority` — F1, F2,
AUTH-1: `ObservedAuthority` holds only `ALLOWED` cells, everything else lands in `excluded` with
an `ExclusionReason`); `analysis/divergence.py` (`analyze_graph` — a thin, testable wrapper
gluing the M1 `graph/divergence.py` and `graph/paths.py` algorithms to a populated graph);
`analysis/confidence.py` (`gate_confidence`/`confidence_rationale`, AUTHORIZATION_MODEL §6's
formula exactly — an empty cell list is unconditionally `INSUFFICIENT` regardless of claimed
coverage); `analysis/timing.py` (`compute_revocation_window` — `t_last_allow`, `t_first_deny`,
the interval-with-jitter transition window, `NON_MONOTONIC_TRANSITION`,
`NO_TRANSITION_OBSERVED_WITHIN_WINDOW`; `classify_stale_authority` — the six-row table with
paired-fresh-credential disambiguation); `analysis/rules.py` (thirteen rule functions, one per
non-derived `FindingType`, each funneled through a single `_build` helper that centralizes F3's
confidence gating and F8's content-derived `finding_id`; every `Finding` carries `observation`,
`expected_state`, `observed_state` and `security_interpretation` as separate fields per
ADR-006, with `security_interpretation` always a static template with substituted values, never
free text built from bundle content, per S2); `analysis/detector.py` (`check_negative_control` —
F7, comparing a negative control's declared `expect_finding` against what the rules actually
produced, emitting `DETECTOR_FAILURE` on mismatch); `analysis/pipeline.py` (`analyze`/
`analyze_bundle` — F8: a pure function of bundle content, deriving `analyzed_at` from the
bundle's own `manifest.completed_at` rather than a wall-clock read, and refusing to produce
findings for a bundle that fails integrity verification unless `--allow-unsealed` is passed).
`core/models.py` gained `CompiledExpectation` (wired into `scenarios/compiler.py`) so a
scenario's `revocation_within`/other declared expectations survive compilation for
`rule_revocation_delay` to compare against. `cli/analyze.py` was rewritten and `chainbreak
analyze <run-id> [--runs-root] [--allow-unsealed]` now runs for real instead of exiting 2.
`analysis/pipeline.py`'s own docstring states its scope precisely: the authority/divergence
family (per phase, from `observations.jsonl`) and the revocation-timing family (from
`POLICY_MUTATION_APPLIED` events paired with post-mutation polls) are extracted from any bundle
automatically; `rule_stale_authority`, `rule_expired_credential_accepted`, `rule_silent_narrowing`
and `rule_configuration_error` are implemented and directly callable but not yet wired into the
automatic pipeline, since the deferred-execution and task-worker machinery that would produce
their inputs from a bundle belongs to M13/M14 and does not exist yet.

Six genuine findings, not design choices:

1. **`finding_id` was wall-clock-seeded, breaking F8 idempotence.** The first pass called
   `core.ids.new_finding_id()` (a ULID) inside `_build`, so calling `analyze` twice on the
   identical bundle produced two `findings.json` files that differed in every finding's id.
   Caught immediately by
   `test_analyze_is_idempotent_on_a_diverging_bundle` — the first genuinely diverging bundle run
   through the pipeline twice, not a synthetic idempotence check. Fixed with
   `_deterministic_finding_id`: a SHA-256 digest over the finding's own content (type, subject
   kind, identity/edge id, hop index, sorted observation refs), so the id is a pure function of
   what the finding says, never of when it was computed.
2. **AUTHORIZATION_MODEL §6's confidence formula, applied uniformly, forced every
   non-authority finding to `INCONCLUSIVE`.** The formula is defined over `ProbeCellResult`
   coverage and unanimity; `EXECUTION_ERROR`, `LIFETIME_CAPPED` and the timing/stale-authority
   families are not built from probe cells at all, so an empty `cells=()` was — correctly, per
   the formula's own `INSUFFICIENT` rule for zero coverage — downgrading every one of them
   before any rule-specific test could see its intended finding type. Resolved by adding
   `confidence_override` to `_build`: the coverage/unanimity gate remains the only path for the
   five authority-axis rules (`EXPECTED_BEHAVIOR`, `AUTHORITY_EXPANSION`, `AUTHORITY_NARROWING`,
   `DELEGATION_DRIFT`, `AUTHORITY_SURVIVAL`), while the rest supply a confidence value derived
   from their own domain-appropriate evidentiary strength, documented at each call site rather
   than silently bypassing F3.
3. **`AUTHORITY_EXPANSION` and `DELEGATION_DRIFT` firing together at the same node looked like
   a contradiction until `nc-non-monotone-chain.yaml` settled it.** The negative control's own
   `expect_finding` names `DELEGATION_DRIFT` at a node that is also the origin of an
   unexpected gain — exactly the node `rule_authority_expansion` fires on. Rather than making
   the two rules mutually exclusive by guesswork, the resolution follows AUTHORIZATION_MODEL
   §7's worked example directly: the origin of a gain at a non-root hop is *both* the
   `AUTHORITY_EXPANSION` (the gain itself) and, for a `DELEGATION_DRIFT` classified
   `ORIGINATED`, the start of the drift chain that downstream `PROPAGATED`/`AMPLIFIED` nodes
   cite by `finding_id` — `rule_delegation_drift`'s docstring records this reasoning so it does
   not look like an oversight on the next read.
4. **Non-monotonic transition detection was mathematically dead code.** The first
   implementation tested `any(t > t_first_deny for t in allowed_ns)`, but `t_last_allow` is
   defined as `max(allowed_ns)`, so no allowed sample can ever exceed it — the branch could
   never evaluate `True` regardless of input. A coarse, 100ms-grid-sampled test passed by
   accident (the seed used never landed a sample on the second flip); rewriting
   `test_oscillation_preserved_not_smoothed` to sample at the schedule's own recorded
   `oscillation_flips_ms` (the same fix M5's own oscillation bug required, see the M5 entry
   above) exposed it immediately. Fixed with a direct chronological scan counting state
   transitions across the ordered samples; `non_monotonic = transitions > 1`.
5. **The revocation-timing pipeline looked up poll data by the mutation's target identity,
   missing the case `nc-no-revocation.yaml` exists to test.** That negative control mutates one
   identity's policy while polling a *different*, unrelated identity — the point being that a
   harness watching the wrong cell must not fabricate a transition. The first pass indexed
   `polls_by_cell` and then queried it by the event's own target, finding nothing to measure
   and silently producing no finding at all — the wrong reason. Fixed in `_revocation_findings`
   by iterating every cell that was actually polled and measuring each against the run's one
   mutation (ADR-011: concurrent mutations would destroy the timing measurement), regardless of
   which identity the mutation itself named — matching what
   `test_defect_present_watching_unaffected_identity_detector_ok` and its fixed-variant
   counterpart in `test_negative_controls.py` require.
6. **`@app.callback(invoke_without_command=True)` misparsed `run_id` when combined with an
   option.** The first `cli/analyze.py` used the same callback pattern `cli/scenario.py`
   established at M4, but Typer's callback dispatch does not compose with a required positional
   argument the way a plain subcommand does: `chainbreak analyze <id> --runs-root <path>` exited
   2 with "Missing parameter: run_id" even though the argument was present on the command line.
   Caught by `test_analyze_a_sealed_bundle` before any fixture was adjusted to work around it.
   Fixed by converting `analyze` to a plain function registered directly via
   `app.command("analyze")(analyze.analyze)` in `cli/main.py`, not a sub-`Typer` app — the
   pattern M4's other single-purpose commands (`run`, `report`) already used, which `scenario`
   and `runs`, both genuinely multi-subcommand groups, did not need to follow.

`evidence/`'s golden and tampered fixtures needed regenerating for a seventh, smaller reason
worth recording alongside the six above even though it surfaced no defect in `analysis/` itself:
M6's fixture generator wrote placeholder dicts for `scenario.json`/`graph.json`, which M6's own
reader never validated against `CompiledScenario`/`AuthorizationGraph`. M7's `read_scenario`/
`read_graph` do validate, so the committed fixtures failed to load before a single rule ever ran.
Regenerated by compiling a real scenario (`scope-attenuation/basic.yaml`) through the actual
`compile_scenario()` against a synthetic AWS registry, and by switching the tampered fixture's
byte-flip from `"trial":1` → `"trial":9` (which broke `Observation`'s own `trial <= trial_count`
validator before the sealing check under test ever ran) to flipping
`"preconditions_verified":true` → `false` — a change that still breaks the sealed hash without
breaking the record's own schema validity.

`analysis/` had no dedicated tests before M7 (the package did not exist). Delivered:
`test_authority_aggregation.py`, `test_confidence_gate.py`, `test_finding_rules.py`,
`test_revocation_math.py`, `test_stale_classification.py`, `test_detector.py`,
`test_cli_analyze_command.py` (unit); `test_known_truth_divergence.py` (C-9: a configured
authority mismatch against the fake produces exactly the expected findings at exactly the
expected confidence), `test_known_truth_timing.py` (the fake's `eventual` profile's known
2000ms `propagation_delay_ms`; the measured transition window is asserted to contain it — a
differential no AWS run could supply, since AWS's real propagation delay is exactly what a real
run would be trying to measure), `test_analyze_idempotence.py`, `test_negative_controls.py` (all
six `nc-*` scenarios against the real fake provider, both directions per acceptance criterion 3:
the defect present produces the declared finding and `DETECTOR_OK`; the same scenario with the
defect "fixed" produces `DETECTOR_FAILURE` instead) (integration). `tests/fixtures/
mini_orchestrator.py` is the test-only stand-in for M10's not-yet-built orchestrator: compile a
scenario, delegate along its edges through the real `FakeProviderAdapter`, probe or mutate-and-
poll, and write a real, sealable bundle via the real `BundleWriter` — every M7 integration test
runs against genuine fake-provider output, not hand-built fixtures.

`analysis/` finished at 97% (acceptance criterion 5's 95% bar), unevenly distributed by design:
`authority.py`, `divergence.py` and `detector.py` are effectively 100% (detector.py's one
uncovered branch is a defensive `except` on a malformed `expect_finding` shape schema validation
already prevents from reaching it); `pipeline.py` is 93%, its own lowest module — the uncovered
lines are glue-code branches no shipped scenario's fake-provider walk happens to trigger (an
unrecognized `mutation_kind` string, a bundle with no mutation event at all, a node that
produces `EXPECTED_BEHAVIOR` with no sibling expansion/narrowing in the same phase, a bundle
whose revocation measurement clears the delay threshold), not the stale-authority/
silent-narrowing/configuration-error rules, which the module docstring already states are not
called from `pipeline.py` at all yet and so do not appear in its coverage report either way.

### Implemented ahead of its milestone (design verification, not milestone completion)

The following exists and passes tests, but the corresponding milestone is **not** complete
because the milestone's full scope and acceptance criteria have not been met.

None currently. (`schemas/*.json` and `schemas/run-index.sql`, listed here through M6, are now
simply part of M6, which is complete.)

### Completed acceptance refresh

**M8 — AWS provider adapter.** Complete; offline verification and dedicated-account acceptance
passed all 21 AWS tests, the wrong-account call-log gate, and the fixed-role contract setup.
Delivered:
`providers/aws/preflight.py` (`TerraformOutputs` + `load_terraform_outputs` — P5's loader,
validating all sixteen required output names from AWS_PROVIDER_SPEC section 8; `run_preflight`
— P1–P11 in order, P1/P2 raising immediately with no further AWS call, P8/P9 producing
`ConfigurationError` rather than a `SecurityInvariantError` abort since a missing marker or a
stray production tag is an infrastructure gap, not a security violation); `session.py`
(`assume_role` — the 3600s chained-role cap applied *before* calling STS, never discovered as
an AWS-side rejection, matching the precedent `providers/fake/session.py` set at M5;
`boto3_session_from_credential` — the one call site besides `TemporaryCredential.__init__`
itself that calls `.reveal()`, per SI-1's own documented exhaustive list); `bindings.py` (real
`ProviderCapabilityBinding`s for all 10 capabilities with correct IAM action names — including
two real AWS action/operation-name divergences this milestone had to get right, see finding 1
below — plus `next_hop_role_arn`, resolving `identity.delegate`'s real probe target from the
fixed, Terraform-provisioned six-role agent chain rather than any one scenario's logical graph);
`probes.py` (all ten capability probes with content verification — a read is `ALLOWED` only if
the returned digest matches; preconditions verified with the bootstrap identity's own clients);
`disambiguation.py` (explicit-vs-implicit denial message classification, matched on AWS's own
"with an explicit deny in a(n) ..." prefix rather than an enumerated policy-kind suffix — see
finding 2; Lambda `FunctionError` vs `AccessDeniedException`; the S3 403/404 shape); `mutation.py`
(the choke point — namespace assert, benchmark-agent assert (SI-12), one named inline policy per
purpose so repeated mutations overwrite rather than accumulate, read-after-write polling; all six
`MutationKind`s implemented, including `DELETE_SESSION_POLICY_SCOPE`'s correct no-AWS-call
no-op); `policy.py` (`snapshot_policy_state` fingerprinting every inline policy *and* the trust
policy on a role, not only the ones this adapter's own mutations write); `retry.py` (full-jitter
backoff, transient-only, `AccessDenied`-shaped codes never retried, always returns rather than
raising so `ProbeTiming.attempt_number`/`.retries` are known even on final failure);
`policy_synthesis.py` (session-policy JSON built from binding metadata only, the 2048-char STS
limit asserted with a clear error); `adapter.py` (`AwsProviderAdapter` — wires all of the above
behind the `ProviderAdapter` Protocol, including a botocore `before-call` hook feeding
`OperationAllowlist` (SI-3) with the same operation-name/IAM-action mapping finding 1 required).

Six genuine findings, not design choices:

1. **Two real AWS operation-name/IAM-action divergences would have broken `OperationAllowlist`
   (SI-3) silently.** `HeadObject` (the write-confirmation call `objectstore.write` makes)
   requires the `s3:GetObject` IAM action — S3 defines no separate `s3:HeadObject` action — and
   `ListObjectsV2` requires `s3:ListBucket`, not a same-named action. The first binding draft
   declared `s3:HeadObject` as a real action, which does not exist; caught by re-deriving each
   action name from AWS's actual IAM reference rather than assuming operation name equals action
   name, before any test could paper over it with a mock that doesn't enforce real names. Fixed
   in `bindings.py`, with the reasoning recorded in a comment so a future capability addition
   does not repeat the assumption. The same two exceptions are handled again in
   `adapter.py::_iam_action` for the botocore hook, since the hook sees the *operation* name
   (`"HeadObject"`, `"ListObjectsV2"`), not the binding's declared action.
2. **The explicit-deny regex, matched narrowly on a trailing "...policy" noun, missed
   "permissions boundary" — the one AWS explicit-deny phrase that does not end in the word
   "policy."** Caught immediately by
   `test_explicit_deny_recognized_across_every_documented_policy_kind[permissions boundary]`,
   parametrized over all five policy-kind nouns AWS_PROVIDER_SPEC section 6.1 names. Fixed by
   matching on the "with an explicit deny in a(n) ..." *prefix* alone — itself AWS's distinctive,
   documented phrase — rather than requiring a specific trailing noun, so a policy kind AWS adds
   later is still recognized without a code change.
3. **Retry logic originally re-raised the final exception on exhaustion, losing the attempt/retry
   count `ProbeTiming` needs for a probe that ultimately failed.** `call_with_retry` was redesigned
   to always return a 3-tuple (`result, exception, RetryOutcome`) rather than raising, so
   `adapter.py` learns how many attempts a probe took whether it succeeded or not — discovered
   while wiring `adapter.probe()`, before any test was written against the raising version, by
   working through what `ProbeTiming.attempt_number`/`.retries` would need to be populated from
   on the failure path.
4. **Every AWS resource/role name in the first draft double-prefixed "cb-".** `Namespace`-typed
   values already carry their own "cb-" prefix (the type's real pattern is
   `^cb-[0-9a-f]{8}$`, and `providers/fake/adapter.py` already established the convention of
   using it directly with no further literal "cb-"), but `bindings.py`, `probes.py` and
   `session.py`'s first drafts each prepended a second, literal `"cb-"` when building ARNs,
   object keys and session names. Caught immediately by the first moto integration test —
   `PutRolePolicy`/`CreateRole` calls citing role names like `cb-cb-a1b2c3d4-agent-b` that could
   never match a real Terraform-provisioned role. Fixed across all three modules; a comment at
   each fix site now states the convention explicitly.
5. **The first `UPDATE_TRUST_POLICY` mutation attempt failed against real IAM semantics moto
   correctly enforces:** a trust-policy statement carrying a `Resource` field is rejected outright
   (`MalformedPolicyDocumentException: Has prohibited field Resource`) — trust policies only ever
   have `Principal`/`Action`/`Effect`/`Condition`. `mutation.py`'s shared `_statement` helper
   originally always included `Resource`; fixed by making it optional (`None` omits the field
   entirely), which is itself evidence that testing against moto's real policy-validation model
   catches mistakes a hand-rolled stub would not.
6. **The fixed-role AWS setup is explicit in the shared contract architecture.**
   `ProviderContractSuite` keeps the behavioral assertions common and exposes setup hooks for
   allowed, denied, empty-control, and snapshot identities. The AWS test subclass maps those
   hooks to Terraform-provisioned roles and waits for authorization-data-plane convergence
   after its deny mutation; it does not override contract behavior assertions.

`providers/aws/` had no tests before M8 (the package did not exist). Delivered, all offline:
`test_disambiguation.py` (24 — message/response-shape classification pinned against literal,
hand-copied AWS strings, the canary AWS_PROVIDER_SPEC's own "Risks" section names), `test_retry.py`
(28 — transient classification, full-jitter bounds, `call_with_retry`'s success/exhaustion/
non-transient-immediate paths), `test_terraform_outputs.py` (6 — `load_terraform_outputs` against
valid/wrapped/missing/malformed/incomplete fixtures), `test_policy_synthesis.py` (5 — statement
shape, the always-present whoami grant, the 2048-char limit), `test_adapter_moto.py` (52 — every
module exercised against real boto3 clients hitting moto's in-memory AWS emulation: preflight
P1–P4/P6/P7/P8/P9/P10, all five delegation mechanisms, all ten probes' success and error-shape
paths, all six mutation kinds, policy snapshotting, and a full register→delegate→probe→mutate→
snapshot walk through `AwsProviderAdapter` itself) (unit); `test_adapter_real.py` (21 — the
inherited `ProviderContractSuite` plus eight IAM-semantics tests named in M8's own spec: role-chain
capping by real STS, session-policy-cannot-grant, explicit-deny-wins, the denial-message-wording
canary, the S3 403/404 precondition proof, missing-marker-is-`CONFIGURATION_ERROR`,
whoami-never-denied, out-of-namespace-refused, and the wrong-account call-log gate —
**executed: 21 passed** in the dedicated account, gated behind the `aws` marker and this
module's own `CHAINBREAK_AWS_TEST_TERRAFORM_OUTPUTS` environment variable) (aws-marked).

`providers/aws/` finished at 93% (`retry.py`/`session.py`/`policy.py`/`policy_synthesis.py`/
`bindings.py` 100%, `disambiguation.py` 100%, `probes.py` 95%, `mutation.py` 92%,
`preflight.py` 94%, `adapter.py` 85% — its own lowest module, the thin Protocol-dispatch glue
layer, already exercised end to end by the register→delegate→probe→mutate→snapshot walk above),
comfortably above the 90% bar M5 set as precedent for a provider package (`providers/fake/`
finished at ~99.7%; `providers/aws/`'s real ceiling is necessarily lower, since real IAM
semantics — IAM IS the ground truth ADR-009 chose over policy simulation — cannot be exercised
without a real account no matter how much offline test-writing happens).

**M9 — Terraform AWS sandbox.** Local and dedicated-account acceptance criteria are complete:
the scoped IAM inspection permission is present, the cleanup contract is `2 passed`, and the
second apply and both destroys are no-ops where required. Delivered: `modules/benchmark-account`
(namespace generation, `data.aws_caller_identity` with a `lifecycle.postcondition` enforcing F2's
"fail at plan time, not apply time" requirement, a conditional `aws_budgets_budget`, the sha256
`infrastructure_fingerprint`); `modules/resources` (S3 bucket + marker + lifecycle + SSE +
public-access block, DynamoDB table + digest item, Lambda via `data.archive_file` — no
`local-exec`, satisfying S3 — with an execution role scoped to its own log group rather than the
AWS-managed wildcard-resource policy, SQS queue); `modules/identities` (bootstrap, principal, and
the six agent roles with chained trust policies carrying `ExternalId`/`RoleSessionName`
conditions, bootstrap's explicit-ARN-list mutation policy, three conditional negative-control
roles gated on `enable_negative_controls` per F6); `modules/delegation` (a customer-managed IAM
policy per agent role — not inline, so `policy_arns` has real ARNs to output — mirroring
`bindings.py::_ACTIONS`, prefix/`LeadingKeys` conditions on writes, three negative-control
policies with the exact `Sid`s `resources/CONTRACT.md`'s own example names); `modules/observability`
(conditional CloudTrail, S3 trail bucket, CloudWatch Logs delivery role); both environments
composing all five modules in the documented order (`benchmark-account → resources → identities →
delegation → observability`), resolving a genuine Terraform circularity — the provider's own
`default_tags` needing a namespace value that itself requires a data source call through that
same provider — with an aliased bootstrap `provider "aws"` block used solely for that one lookup;
`cli/infra.py` (`plan`/`apply`/`destroy`/`status` as thin `terraform` subprocess wrappers streaming
real stdio, `apply` capturing `terraform output -json` atomically to a gitignored
`outputs.json` per F4, removing stale outputs after a failed apply or successful destroy,
and `status` rejecting a captured file that differs from current Terraform state). `verify-clean`
uses service-specific, fail-closed enumerators for every provisioned service, including IAM
roles and policies, and requires exact `Project=CHAINBREAK` plus namespace tags; it remains
independent of local state when the operator supplies the exact namespace explicitly.

Two genuine findings, not design choices:

1. **M8's `function.invoke` probe expected the Lambda to echo a per-call random nonce; M9's own
   `resources/CONTRACT.md` (and, on closer reading, `capabilities/catalog.yaml`'s own
   `function.invoke` description) specify a *fixed* payload, `{"ok": true, "nonce": <namespace>}`,
   with no per-call echo at all.** Caught while writing `modules/resources`' Lambda source against
   the contract, before any real invocation could have surfaced the mismatch as a spurious
   probe failure. Fixed by removing the `nonce` parameter from `probe_function_invoke` entirely
   (`providers/aws/probes.py`) and comparing against `outputs.namespace` instead; `adapter.py`'s
   `_build_call` and both moto test call sites updated to match. This is an M8 defect discovered
   during M9, not an M9 defect — recorded here rather than silently folded into M8's already-closed
   entry.
2. **`chainbreak infra verify-clean` originally required `infra/terraform/environments/<name>/`
   to exist on disk, contradicting F5's own stated purpose** ("stays meaningful even if local
   state were ever lost or corrupted"). `_region_hint` raised on a missing directory instead of
   treating a missing region hint as normal; fixed by making it take the environment name and
   return `None` for any reason the hint isn't available (missing directory, missing file,
   malformed content) rather than raising, with a regression test
   (`test_works_even_when_the_environment_directory_was_never_checked_out`) locking in the fix.

`tests/aws/test_terraform_outputs.py` was extended (not duplicated — M9's own file list names it,
but M8 had already created it for `preflight.py::load_terraform_outputs`) with a
`TestOutputShapeValidation` class (8 tests: malformed namespace/account-id/role-ARN/digest/
queue-URL shapes, including a wrapped output missing its value, each rejected individually, and
together). `tests/unit/test_cli_infra_command.py` exercises `plan`/`apply`/`destroy`'s argument
handling, atomic/stale-output lifecycle, and `status`/`verify-clean` against `mock_aws()` —
including an IAM-role leftover that prevents a clean result.
`tests/aws/test_cleanup_contract.py` (`e2e`-marked, per M9's own "Tests" section: "applies,
destroys, destroys again, then runs verify-clean") drives the real `chainbreak infra` CLI
commands end to end against `aws-sandbox` — **executed: 2 passed** in the dedicated account,
gated behind `CHAINBREAK_ALLOW_AWS_TESTS=1`.

**M9 acceptance evidence:** criterion 1 (`terraform validate`/`fmt -check`) is met; criterion 2
(`checkov`/`tflint` clean) is met by the recorded Checkov result (`138 passed, 0 failed, 30
documented skips`) and TFLint pass; criterion 3 (apply → P1–P11 → destroy → verify-clean) is
met; criterion 4's negative-control resources appeared in the real apply outputs; and criterion
5's second apply and repeated destroy were no-ops. The final service enumeration and AWS Console
cross-check showed zero remaining benchmark resources.

**M8 acceptance evidence:** criterion 1 is met by the shared M5 behavioral contract assertions
with explicit fixed-role AWS setup hooks. Criterion 2 is met with `21 passed`; criterion 3 is
met by the scrubbed, provenance-labeled response-shape fixtures; criterion 4 is met by the live
wrong-account call-log assertion; and criterion 5 (no `boto3`/`botocore` import outside
`providers/aws/`) is met. No behavioral assertion was weakened.

**M10 — Scope attenuation benchmark (Family A).** All four acceptance criteria met, against the
fake provider only — **never run against AWS**, per M10's own definition of done. Delivered:
`execution/orchestrator.py` (F1's preflight → materialize → walk-plan → cleanup loop, written
against the *full* `PhaseKind` enum — `PROBE` implemented, `SNAPSHOT` a documented no-op until a
scenario auto-inserts one around a mutation, `MUTATE`/`POLL`/`WAIT`/`DEFERRED_EXECUTION`/`TASK`
each raise naming the milestone that implements them, never a silent skip); `execution/matrix.py`
(C-2 precondition check once per matrix, C-1 calibration before the shuffled loop, C-6 order
shuffled with a sha256-derived per-(matrix, identity) seed — deliberately not Python's own
per-process-randomized `hash()` — recorded as a `PROBE_ORDER_SHUFFLED` event, trial repetition);
`execution/control.py` (`identity.whoami` probed first per identity; a non-`ALLOWED` result raises
`ControlCapabilityFailedError`, caught by the orchestrator to discard the *whole* matrix, not one
identity's row); `execution/delegation.py` (materializes the graph — root registered directly,
every edge delegated in compiled hop order — and F6's re-delegation: a credential re-delegated,
with a recorded `CREDENTIAL_REDELEGATED` event, once its remaining lifetime drops under 2x the
matrix's own conservatively-estimated duration); `execution/preconditions.py` (resolves every
precondition a matrix's capabilities require against a `PreconditionRegistry`, by the provisioning
identity, before any probe in the matrix runs). `cli/run.py` implemented for real (`--provider
fake` end to end and `--provider aws` through the validated Terraform-output factory) — registered
as a plain root-app
command (`app.command("run")(run.run)`), not a sub-`Typer` app, the same fix `cli/analyze.py`
already documents: a sub-app's `@app.callback(invoke_without_command=True)` misparses a required
positional once an option follows it, exactly this milestone's own verification command's shape.

Two real defects found and fixed during implementation, not design choices:

1. **`ProviderAdapter` (`providers/base/protocol.py`) had no `register_identity` method**, even
   though both `FakeProviderAdapter` and `AwsProviderAdapter` already implement one (the AWS
   adapter's own docstring already frames its `allow` parameter as "accepted for surface
   compatibility" with the fake's) — `execution/delegation.py` needs it to materialize a graph's
   root generically, without reaching into either adapter's private internals. Added to the
   Protocol; both existing adapters already satisfy it structurally, confirmed by
   `isinstance(adapter, ProviderAdapter)` under `@runtime_checkable` and by mypy's own structural
   check at every call site.
2. **F6's credential-lifetime check initially compared a fake credential's `expires_at` against
   real wall-clock time.** `FakeProviderAdapter`'s `CredentialRecord` timestamps are computed from
   its own virtual clock (`providers/fake/session.py`'s fixed `2024-01-01` epoch, never the system
   clock — a deliberate M5 design choice for determinism), so `datetime.now(UTC)` reads every
   real fake credential as already expired regardless of its actual granted duration, making F6
   fire on *every* matrix instead of only when genuinely warranted. Caught by
   `test_ensure_fresh_credential_is_a_no_op_for_a_healthy_credential` failing unexpectedly during
   its first run. Fixed in both `cli/run.py` and every test that drives `orchestrate()`: `now` is
   `virtual_ms_to_datetime(adapter.clock.now_ms)` for a fake-provider run, never
   `datetime.now(UTC)`.

**Resolved** (P1 documentation pass): ARCHITECTURE.md section 3.7 originally described
`delegation/` as its own top-level package; M10's own milestone file
(`docs/implementation/milestones/M10-scope-attenuation.md`) and `docs/implementation/
NEXT_PROMPTS.md`'s S2 prompt both named it `execution/delegation.py` instead, and — being the
more specific, more recently written source for this exact milestone — were followed here. The
tension was recorded above rather than resolved unilaterally at the time. It has since been
closed: the empty `src/chainbreak/delegation/` and `src/chainbreak/observation/` placeholder
packages were deleted, ARCHITECTURE.md §3.7/§3.12 were rewritten to describe where delegation
planning and outcome classification actually live (`execution/delegation.py`;
provider-side classification plus `execution/_records.py`), and the decision is recorded in
`docs/DECISIONS.md`.

Test files: `tests/integration/test_scope_attenuation.py` (7 — the full basic scenario end to end
via the real orchestrator, both scope-attenuation negative controls in both directions [defect
present → `DETECTOR_OK`, defect fixed → `DETECTOR_FAILURE`] via the same fake-side defect
injection `test_negative_controls.py` already established, acceptance criterion 4's seed
reproducibility); `tests/integration/test_control_capability.py` (4); `tests/integration/
test_probe_matrix_execution.py` (9); `tests/integration/test_orchestrator_error_paths.py` (9 —
every `PhaseKind` branch, a failed preflight, F6 actually firing mid-run); `tests/integration/
test_cli_run_command.py` (7); `tests/unit/test_cli_run_command.py` was not needed as a separate
file since the CLI happy path is itself an `integration`-tier test by this project's own marker
definition. Coverage on `execution/` is 99% (two genuinely unreachable defensive branches —
"identity not yet materialized" in both `matrix.py` and `orchestrator.py` — marked
`# pragma: no cover` with a comment naming G-2's own reachability guarantee: an unreachable
identity is a compile-time `ScenarioSemanticError`, never a compiled matrix, so the branch cannot
fire from any scenario that actually compiled).

Verification commands run for real:

```
$ chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake --seed 11
chainbreak run: COMPLETED -> runs\01KZJQVX1S1RGT68VZ1EJ49MSR      (0.79s wall clock)

$ chainbreak analyze 01KZJQVX1S1RGT68VZ1EJ49MSR
chainbreak analyze: 3 finding(s), 0 detector check(s) -> runs\...\findings.json
EXPECTED_BEHAVIOR / EXPECTED_BEHAVIOR / EXPECTED_BEHAVIOR

$ chainbreak run scenarios/_negative-controls/nc-scope-expansion.yaml --provider fake --seed 11
chainbreak run: COMPLETED -> runs\01KZJQVYQVDE068KVVAE4NY4N9

$ chainbreak run scenarios/_negative-controls/nc-surviving-authority.yaml --provider fake --seed 11
chainbreak run: COMPLETED -> runs\01KZJQVZKR6FA11BSYSAHR1NG5

$ pytest -m integration tests/integration/test_scope_attenuation.py -q
7 passed in 0.97s
```

(The two bare CLI negative-control runs above complete cleanly because `chainbreak run` has no
way to inject the fake-side defect a real Terraform-provisioned role would carry — that defect
injection is a Python-level test concern, exercised by `test_scope_attenuation.py` above, exactly
as `test_negative_controls.py` already established for M7's own negative controls.)

**M11 — Delegation drift benchmark (Family B).** All five acceptance criteria met, against the
fake provider only — **never run against AWS**. Delivered: `execution/chain.py`
(`materialize_chain`: S1's redundant, execution-layer depth check — G-5 already refuses this at
compile time, so this can only fire for a graph that reached here some other way — plus S2's
credential scrubbing, actually implemented in `execution/delegation.py`'s `materialize_graph`/
`ensure_fresh_credential`, which now call `TemporaryCredential.scrub()` on every hop's raw secret
immediately after extracting its safe `CredentialRecord` projection, not only chain ones);
`analysis/drift.py` (F6: `DepthResult`/`DepthSweepReport`, divergence reported as a rate per hop
and an exclusion rate per depth, never a raw count, `summarize_depth_sweep` reporting the sweep
`INCONCLUSIVE` by name — not asserting a depth effect — when both rates rise together across
depth); four new depth-sweep scenarios (`two`/`three`/`five`/`six-hop.yaml`, mirroring
`four-hop.yaml`'s monotone capability-narrowing structure, same start and end capability sets at
every depth so depth is the one thing that actually varies); `role-chain-five-hop.yaml`, a
test-support fixture using plain `ROLE_CHAIN` throughout (see below for why); `chainbreak analyze
--aggregate --scenario-family <family>` (F6's CLI surface).

Most of M11's core algorithms already existed before this milestone started: per-edge divergence,
first-divergence-per-path and `classify_drift`'s `ORIGINATED`/`PROPAGATED`/`AMPLIFIED`/`CORRECTED`
table were all built at M1 (`graph/divergence.py`, `graph/paths.py`), and `analysis/rules.py`'s
`rule_delegation_drift` (with cause citation) plus `analysis/pipeline.py`'s wiring of both into
findings were built at M7. M11's actual new work was narrower than its own milestone file's list
suggested — and trying to prove its acceptance criteria against a real, deeper chain than any
existing test used surfaced two real defects in that already-existing M7-era code, not design
choices this milestone made:

1. **`pipeline.py`'s citation ever only reached the origin's immediate child.**
   `_origin_finding_id` looked up only a node's *immediate parent's own* `AUTHORITY_EXPANSION`
   finding — correct for the four-hop worked example (exactly one propagated hop exists to test)
   but silently drops the citation past that, since a `PROPAGATED`/`AMPLIFIED` node never gets its
   own `AUTHORITY_EXPANSION` finding (`rule_authority_expansion`'s predicate excludes both).
   Fixed by threading an `origin_by_identity: dict[IdentityId, str]` map forward through the node
   walk: a node with its own `AUTHORITY_EXPANSION` records itself as the origin; a node that only
   gets a `DELEGATION_DRIFT` finding inherits its parent's origin instead; a `CORRECTED` node gets
   no entry at all, which is what correctly resets the chain for any later, independent gain.
   Caught by a new depth-5 test (`role-chain-five-hop.yaml`, since none of the depth-sweep
   scenarios can carry an identity-policy-level defect past a session-policy-scoped hop — see
   below) proving citation survives three propagated hops past the origin, which no existing test
   exercised.
2. **`graph/paths.py`'s `analyze_all_paths` (F3, already correct and already unit-tested for
   branching graphs at M1) was never called from `analysis/pipeline.py` at all.** Path-level
   output — first divergence per root-to-leaf path — was computed, tested, and then never reached
   `findings.json`. Wired into `analyze_bundle`, computed by progressively accumulating observed
   authority across phases in chronological order (a node with no observations in a later phase
   keeps whatever an earlier phase already measured for it, rather than being reset to
   unmeasured) instead of recomputing fresh per phase — necessary because a scenario's own
   baseline phase is typically the only phase that re-probes the root, so a strictly per-phase
   view reported the root `UNMEASURED` for every later phase's own path analysis, masking the
   real divergence deeper in the chain. Caught the same way: a real run, not a hand-built graph.

One test-fixture decision worth recording: `role-chain-five-hop.yaml` exists because a
session-policy-scoped hop's effective authority is intersected with *that hop's own declared*
`intended_capabilities` (PROV-1 — a session can only narrow, never grant), which makes it
structurally impossible to observe an identity-policy-level defect injected downstream of a
`ROLE_CHAIN_WITH_SESSION_POLICY` hop — exactly why `nc-scope-expansion.yaml` and
`nc-non-monotone-chain.yaml` both use plain `ROLE_CHAIN` throughout already. None of the
depth-sweep scenarios could be reused for the worked-example/citation tests for the same reason
(their later hops are deliberately session-policy-scoped, to test *attenuation* correctness, which
is the opposite property).

Test files: `tests/unit/test_drift_aggregation.py` (9 — `analysis/drift.py`'s pure aggregation
logic: hop/divergence/exclusion counting, the confound verdict in both directions);
`tests/unit/test_chain.py` (2); `tests/integration/test_delegation_drift.py` (6 — the
AUTHORIZATION_MODEL section 7 worked example end to end [`ORIGINATED` at hop 3, `PROPAGATED` at
hop 4, citation present], the `CORRECTED` case, citation surviving three propagated hops, path
analysis wired end to end, `nc-non-monotone-chain` in both directions);
`tests/integration/test_depth_sweep.py` (10 — all five depths run and yield correct
`DepthResult`s, the clean sweep is not inconclusive, a confounded sweep built from two real
bundles plus one synthetic high-divergence result is correctly flagged, the `--aggregate` CLI
path end to end including its own error paths). Coverage on `execution/` + `analysis/` combined is
98% (`execution/chain.py`'s depth-exceeded branch now covered by `test_chain.py`; the remaining
gaps are pre-existing M7-era revocation/execution-error paths unrelated to M11, out of scope until
M12).

Verification commands run for real:

```
$ for d in two three four five six; do
    chainbreak run scenarios/delegation-drift/$d-hop.yaml --provider fake --seed 23 || break
  done
chainbreak run: COMPLETED -> runs\01KZJW6Z5B9VPEYHFQ721KWRVE      (0.88s wall clock)
chainbreak run: COMPLETED -> runs\01KZJW701T7AR986PHZ71D5T4F      (0.92s wall clock)
chainbreak run: COMPLETED -> runs\01KZJW710RB3RP458QHCJ5ND3F      (1.03s wall clock)
chainbreak run: COMPLETED -> runs\01KZJW71YY1V3VVYMF5FCPEWEX      (1.05s wall clock)
chainbreak run: COMPLETED -> runs\01KZJW72ZD151MAX2V0N5WCB4R      (0.93s wall clock, depth 6)

$ chainbreak analyze --aggregate --scenario-family delegation-drift
chainbreak analyze --aggregate: delegation-drift depth sweep (5 depth(s))
  depth 2: divergence 0.000/hop (0/2 hops), exclusions 0.000 (0/16 cells) -- delegation-drift-two-hop
  depth 3: divergence 0.000/hop (0/3 hops), exclusions 0.000 (0/24 cells) -- delegation-drift-three-hop
  depth 4: divergence 0.000/hop (0/4 hops), exclusions 0.000 (0/32 cells) -- delegation-drift-four-hop
  depth 5: divergence 0.000/hop (0/5 hops), exclusions 0.000 (0/40 cells) -- delegation-drift-five-hop
  depth 6: divergence 0.000/hop (0/6 hops), exclusions 0.000 (0/48 cells) -- delegation-drift-six-hop
chainbreak analyze --aggregate: no divergence/exclusion confound detected (F6)

$ pytest -m integration tests/integration/test_depth_sweep.py -q
10 passed in 2.87s
```

Depth-6's own non-functional requirement (under 15s) is met by roughly an order of magnitude — the
whole five-scenario sweep completes in under 5s, not just the single deepest run.

**M12 — Revocation propagation benchmark (Family C).** All five acceptance criteria met, against
the fake provider only — **never run against AWS**. Delivered: `execution/mutation.py`
(`apply_mutation`: builds a `PolicyMutation` from the compiled `MutationPlan`, calls
`adapter.apply_policy_mutation`, aborts via `MutationNotConfirmedError` when a receipt-required
mutation comes back unconfirmed — F4 — and writes the `POLICY_MUTATION_APPLIED` event
`analysis/pipeline.py`'s pre-existing `_revocation_findings` already reads); `execution/polling.py`
(`run_poll_phase`: serial polling advancing the adapter's virtual clock by the compiled
`interval_ms`, `STABLE_DENIAL`/`STABLE_ALLOW`/`TIMEOUT` stability detection via `stability_count`
consecutive matching outcomes, one `Observation` per poll tagged `PlanPhase.POST_MUTATION`
regardless of which side of the mutation it fell on — F2/F3); `execution/revert.py`
(`build_revert_plan`/`build_revert_log_event`/`revert_mutation`: reverting means restoring an
identity's *declared* authority via `REPLACE_INLINE_POLICY`, never replaying an adapter's internal
pre-mutation state, since that would mean carrying an unredacted policy document through the
evidence pipeline; `REVOKE_OLDER_SESSIONS` is honestly reported as unrevertable — a revoked
session can only be replaced, not un-revoked — and `UPDATE_TRUST_POLICY`/
`DELETE_SESSION_POLICY_SCOPE` correctly report nothing to revert, since neither ever touches a
live session's authority — F8/F9/S3); two new core domain models, `MutationPlan`/`PollPlan`
(`core/models.py`), compiled by two new `scenarios/compiler.py` functions
(`_build_mutation_plans`/`_build_poll_plans`) mirroring `_build_probe_matrices`'s existing
"strip the scenario-layer spec down to exactly what execution needs" discipline — required because
`execution/` sits below `scenarios/` in ARCH-1's layering and may not import the `MutationSpec`/
`PhaseSpec` types those phases are declared with; `execution/orchestrator.py`'s `MUTATE`/`POLL`
branches (previously named-milestone stubs) and its `SNAPSHOT` branch (previously a documented
no-op) now call these for real, and the run's `finally` block reverts every mutation that actually
succeeded, in reverse order, regardless of whether the run completed, raised a `ChainbreakError`,
or an uncaught exception propagated out; a `--fake-profile` flag on `chainbreak run`
(deterministic/eventual/hostile, dispatching to `providers/fake/profiles.py`'s three named
configurations — previously hardcoded to `deterministic_profile`); three new scenario files
completing the five-mechanism corpus (`remove-policy.yaml`, `revoke-older-sessions.yaml`,
`delete-session-scope.yaml` — `inline-deny.yaml` and `trust-policy-null-condition.yaml` already
existed).

The revocation-window interval math (`analysis/timing.py`'s `compute_revocation_window`) and the
finding rules that consume it (`analysis/rules.py`'s `rule_no_transition_observed`/
`rule_revocation_delay`, wired into `analysis/pipeline.py`'s `_revocation_findings`) already
existed from M7, already unit-tested at the known propagation delays 0/500/2000/10000ms
(`tests/unit/test_revocation_math.py`). M12's actual new work was the execution layer that
produces the real events and polled observations that math consumes — nothing in the interval
math itself needed to change. One real gap the milestone's own research surfaced and left
correctly unaddressed rather than silently assumed: `RevocationMeasurement.mutation_receipt_confirmed`
is threaded all the way through the data model but no rule currently *acts* on it (an unconfirmed
receipt does not yet downgrade a finding to `INCONCLUSIVE`) — the fake adapter's own
`apply_policy_mutation` never actually produces an unconfirmed receipt (`confirmed` is hardcoded
`True`), so `MutationNotConfirmedError`'s abort path is exercised only at the unit level, against a
stub adapter (`tests/unit/test_mutation.py`), not through a real fake-provider run. This is a
faithful reflection of the fake laboratory's own design (a real AWS control-plane write is the only
place a genuinely unconfirmed receipt would occur), not an oversight to fix later without cause.

Test files: `tests/integration/test_revocation.py` (15 — all five mechanisms execute and record
their kind with a confirmed receipt and a revert log; the three positive mechanisms observe a
`STABLE_DENIAL` transition; `inline-deny.yaml`'s mutation is actually reverted, restoring
`objectstore.read` on the live adapter, while `revoke-older-sessions.yaml`'s is correctly reported
unrevertable; both negative controls report `NO_TRANSITION_OBSERVED`; the measured window contains
the true propagation delay at all four M12-named settings — 0/500/2000/10000ms — through the real
orchestrator, not the `mini_orchestrator` fixture; a forced `REVOCATION_DELAY` finding's
`transition_window` is a `{low, high}` pair, never a bare scalar — F5's hard requirement);
`tests/integration/test_polling.py` (5 — `STABLE_ALLOW`/`STABLE_DENIAL`/`TIMEOUT` stopping exactly
at the right poll count, a `stop_on: TIMEOUT` phase running its full budget even though every poll
happens to match what `STABLE_ALLOW` would have accepted, the not-materialized guard);
`tests/unit/test_revert.py` (9 — every `MutationKind`'s actionability and action text, the log
event shape, an actionable revert actually restoring engine state, a non-actionable one calling
the adapter not at all); `tests/unit/test_mutation.py` (3 — the SI-2 materialized-target guard,
`MutationNotConfirmedError` firing only when `record_receipt` is true). Coverage on the five new/
modified `execution/` modules is 95-100% (`mutation.py`/`revert.py` 100%, `orchestrator.py`/
`polling.py` 99%, `cli/run.py`'s new `--fake-profile` branches fully covered — its few remaining
gaps are pre-existing settings-fallback paths unrelated to M12).

Verification commands run for real:

```
$ chainbreak run scenarios/revocation/inline-deny.yaml --provider fake --fake-profile eventual --seed 5
chainbreak run: COMPLETED -> runs\01KZKABDX5688VDVQZW8A0CZG4

$ chainbreak analyze 01KZKABDX5688VDVQZW8A0CZG4
chainbreak analyze: 2 finding(s), 0 detector check(s) -> runs\...\findings.json
$ jq '.findings[]|select(.type=="REVOCATION_DELAY")' runs\...\findings.json
                                       # empty: inline-deny.yaml's own expectation is
                                       # severity: informational by design (SCORING_MODEL.md) --
                                       # CHAINBREAK does not assert a normative propagation time
                                       # without justification, so no finding is the correct result

$ chainbreak run scenarios/revocation/trust-policy-null-condition.yaml --provider fake --seed 5
chainbreak run: COMPLETED -> runs\01KZKABFR3AYBJ1NEM6X52XZQ6      (NO_TRANSITION_OBSERVED on analyze)

$ chainbreak run scenarios/_negative-controls/nc-no-revocation.yaml --provider fake --seed 5
chainbreak run: COMPLETED -> runs\01KZKABGQV5DCZP85S5PVV5WXF      (NO_TRANSITION_OBSERVED on analyze)

$ pytest -m integration tests/integration/test_revocation.py -q
15 passed in 2.48s
```

**M13 — Stale-authority benchmark (Family D).** All five acceptance criteria met, against the
fake provider only — **never run against AWS** (out of scope by the milestone's own definition).
Delivered: `execution/credential_store.py` (`CredentialStore` — a per-`(phase_name, identity_id)`
registry the orchestrator populates every time a `PROBE`-kind matrix actually runs against an
identity, letting a later `credential_source: phase:<name>` resolve back to "the credential
minted at that phase" without re-delegating — F1); `execution/deferred.py` (`run_wait_phase` —
F2, advances the provider's virtual clock via the same `advance_clock` escape hatch
`execution/polling.py` already established, with an untested real-sleep fallback for a future
real-time adapter, M17; `run_deferred_execution_phase` — probes every capability in the compiled
universe using the pinned credential *without* calling `delegation.ensure_fresh_credential`
first, tags those `PlanPhase.DEFERRED_EXECUTION`, then **unconditionally** mints a new credential
— never gated by remaining lifetime the way `ensure_fresh_credential`'s own F6 threshold is,
since a comfortably-valid pinned credential would otherwise silently reuse the same session for
the "fresh" leg and defeat F3 entirely — and probes again, tagged
`PlanPhase.PAIRED_FRESH_CREDENTIAL`); `analysis/stale.py` (`stale_authority_measurements` — pairs
`DEFERRED_EXECUTION`/`PAIRED_FRESH_CREDENTIAL` observations by `(identity_id, capability_id)`,
reads `DELETE_SESSION_POLICY_SCOPE`-kind `POLICY_MUTATION_APPLIED` events for
`session_scope_removed` rather than inferring it from any observed outcome, and calls M7's
pre-existing `classify_stale_authority`); two new compiled-plan types mirroring M12's own
`MutationPlan`/`PollPlan` precedent, `WaitPlan`/`DeferredExecutionPlan` (`core/models.py`,
compiled by two new `scenarios/compiler.py` functions,
`_build_wait_plans`/`_build_deferred_execution_plans`, the latter sharing a new
`_capability_universe` helper with `_build_probe_matrices` rather than duplicating F3's
probe-universe selection a third time); new `PhaseSpec` validation (`WAIT` requires a positive
`wait_seconds`; `DEFERRED_EXECUTION` requires `target_identity`, not only `credential_source`) and
a new `PlanPhase.PAIRED_FRESH_CREDENTIAL` enum member; `execution/orchestrator.py`'s `WAIT`/
`DEFERRED_EXECUTION` branches (previously named-milestone stubs since M10) now call these for
real, and every `PROBE`-kind matrix records its identity's current credential into the run's one
`CredentialStore` as it runs; three new scenario files (`stale-authority/short-defer.yaml`,
`long-defer.yaml`, `post-expiry.yaml`, F6's {30, 120, 600}s-plus-expiry set) and
`nc-stale-credential-reuse.yaml` (already committed since M3-era scaffolding) simplified to drop
a redundant trailing `PROBE`-kind "paired-fresh-credential" phase once `DEFERRED_EXECUTION` grew
its own paired-probe machinery — see finding 3 below for why that scaffolded design would not
have worked as originally sketched.

Four genuine findings, not design choices:

1. **The fake's own mutation-visibility model cannot, by construction, ever produce a genuine
   `STALE_AUTHORITY_LIVE_CREDENTIAL` result.** `providers/fake/adapter.py`'s pending-transition
   window (M5) is keyed purely by *identity* and *wall-clock time since the mutation*, never by
   which credential is asking — so a credential minted before a mutation and one minted
   immediately after it, probed at the same instant, always observe the *identical* pre/post
   state. Every M10-M12 scenario needs exactly this (the revocation family's whole measurement is
   the *same* session watching a live transition over time), but it means the paired
   fresh-credential probe F3 requires can never disagree with the pinned one on identity-policy
   grounds alone — the classifier would only ever see "not propagated yet" or "already current",
   never genuine staleness, regardless of how the scenario's deferral interval was tuned against
   `propagation_delay_ms`. Fixed with a new, strictly opt-in mechanism
   (`FakeProviderAdapter.enable_authority_caching`, an adapter-specific escape hatch matching
   `advance_clock`'s own precedent, never in the `ProviderAdapter` Protocol): every `delegate()`
   call now captures a snapshot of the issuing identity's *live* (allow, deny) at that exact
   moment, keyed by the new credential's own id; once `execution/deferred.py` calls
   `enable_authority_caching` for the one identity it is about to run a deferred/paired-fresh
   probe against, that identity's probes consult *its currently-held credential's own* snapshot
   instead of live/pending state. An old (pre-mutation) pinned credential's snapshot never
   changes; a freshly re-delegated one captures a brand-new snapshot reflecting whatever is
   currently true (`apply_policy_mutation` always writes to live engine state synchronously,
   regardless of the separate propagation-delay window) — which is what makes the divergence
   deterministic and independent of deferral length or fake profile, rather than a race. Checked
   before the pending-transition branch, never touched by M10-M12 scenarios (the set defaults
   empty and only `execution/deferred.py` ever populates it), so none of their existing tests
   changed behavior.
2. **The snapshot must be captured at each credential's own issuance, not lazily when caching is
   enabled.** The first implementation called `enable_authority_caching` (which ran well after
   the scenario's `MUTATE` phase) and had *it* capture the snapshot from current engine state —
   which is already post-mutation by the time `DEFERRED_EXECUTION` runs, so the "pinned" probe
   incorrectly observed the *new* policy instead of the old one it was minted under. Caught
   immediately by the very first hand-run of `short-defer.yaml` (the deferred-execution
   observation for `objectstore.read` came back `DENIED_EXPLICIT`, not the expected `ALLOWED`),
   before any test had been written to hide it. Fixed by moving snapshot capture into
   `delegate()` itself, unconditionally for every credential regardless of whether caching is
   enabled yet (cheap, harmless for the identities that never opt in — nothing ever reads it),
   keyed by credential id rather than identity id so an old and a new credential for the same
   identity each keep their own.
3. **`nc-stale-credential-reuse.yaml`'s own scaffolded design (a separate trailing `kind: PROBE`
   phase literally named `paired-fresh-credential`) would not have produced a genuinely fresh
   credential.** The generic `PROBE` branch always calls `delegation.ensure_fresh_credential`,
   whose F6 threshold only re-delegates if the *remaining* lifetime is under 2x the estimated
   matrix duration — for the 3600s-lifetime credentials these scenarios use, a 20-30s-old
   credential is nowhere near that threshold, so the "paired" phase would have silently reused
   the *same* session, defeating F3 entirely. `execution/deferred.py` instead performs both
   probes internally, with an unconditional re-delegation between them; the scenario's own
   redundant trailing phase (and the matching, now-dead `PHASE_NAME_TO_PLAN_PHASE["paired-fresh-
   credential"]` table entry in `orchestrator.py`) were removed rather than worked around.
4. **The "ambiguous / not yet propagated" case (AUTHORIZATION_MODEL §5.2's `INDETERMINATE` row)
   is reached for free, with no dedicated fixture needed.** `_build_deferred_execution_plans`
   probes the *full* declared capability universe, not only the one capability a scenario's own
   `MUTATE` phase targets (F3's own "you cannot detect expansion by testing only what you
   expect" logic, reused here) — so `identity.whoami`, never touched by any mutation in any of
   the three shipped scenarios, always shows the pinned and fresh probes agreeing (`ALLOWED`),
   which `classify_stale_authority` already correctly reports as `INDETERMINATE`, never
   `STALE_AUTHORITY_LIVE_CREDENTIAL` — exercised directly by
   `tests/integration/test_stale_authority.py::TestShortDefer::test_unmutated_capability_classifies_indeterminate_not_stale`
   against a real run, not only `test_stale_classification.py`'s pure-function unit test from M7.

`CURRENT_AUTHORITY` and `SESSION_SCOPE_CACHED` (the two rows the three shipped scenarios do not
naturally reach) are exercised directly against `execution/deferred.py` and a real
`FakeProviderAdapter` without a full YAML scenario, matching `test_mutation.py`'s own precedent
for testing one `execution/` module's specific branch directly. `EXPIRED_CREDENTIAL_HONORED` (the
one row that would contradict documented behavior) cannot be produced by a *correctly behaving*
fake by construction — its classification is covered at the pure-function level by
`test_stale_classification.py` (M7); `tests/integration/test_stale_authority.py`'s
`TestExpiredCredentialHonoredWiring` additionally proves `analysis/pipeline.py`'s own wiring
around it fires correctly, by corrupting one real `post-expiry.yaml` observation the way only a
genuine provider defect could and re-sealing a bundle from the corrupted data — the one thing the
fake's own correctness cannot demonstrate on its own. `analysis/pipeline.py`'s `analyze_bundle`
now extracts stale-authority findings automatically from any bundle (closing the stale-authority
half of former known issue 13 below; silent-narrowing remains M14's).

Test files: `tests/integration/test_stale_authority.py` (11 — short-defer/long-defer/post-expiry
all run for real; `STALE_AUTHORITY_LIVE_CREDENTIAL` for the mutated capability and `INDETERMINATE`
for the untouched one from the *same* run; `CREDENTIAL_EXPIRED` with no mutation involved at all;
`CURRENT_AUTHORITY`/`SESSION_SCOPE_CACHED` driven directly against `execution/deferred.py`;
`EXPIRED_CREDENTIAL_HONORED`'s pipeline wiring via a corrupted, re-sealed bundle);
`tests/integration/test_credential_pinning.py` (3 — acceptance criterion 2: the deferred
observation's `credential_id` equals the `after-delegation`-phase credential's, read from
`observations.jsonl`/`credentials.jsonl`, never asserted against the code path; the paired
observation's differs); `tests/integration/test_post_expiry.py` (4 — acceptance criterion 4);
`tests/unit/test_credential_store.py` (3), `tests/unit/test_deferred.py` (2 — the no-edge/root
guard, and a stand-in adapter with no `enable_authority_caching` hook, proving
`execution/deferred.py` still runs correctly against a future real-time adapter without it);
`tests/unit/test_scenario_schema_extra.py` gained the two new `PhaseSpec` validator cases.
`tests/integration/test_negative_controls.py`'s `nc-stale-credential-reuse` section, previously
rule-level only (no deferred-execution engine existed), now runs end to end through the real
orchestrator in both directions — defect present (a real `ATTACH_INLINE_DENY` mutation) reports
`DETECTOR_OK`; the "fix" (the same compiled scenario with its `MUTATE` step and `MutationPlan`
stripped via `model_copy`, so the pinned and fresh probes have nothing to disagree about) reports
`DETECTOR_FAILURE`, following the exact pattern `TestNoRevocation` already established for
`nc-no-revocation` at M12.

Coverage: every M13-proper module (`execution/deferred.py`, `execution/credential_store.py`,
`analysis/stale.py`, `providers/fake/session.py`, `scenarios/schema.py`) finished at 100%;
`scenarios/compiler.py` 98% (two pre-existing, unrelated gaps); `execution/orchestrator.py`/
`providers/fake/adapter.py` 99% (a couple of pre-existing branch-coverage partials, not M13's
own new code). One piece of dead code from an earlier iteration of finding 1 above
(`SessionStore.issued_at_ms`, superseded by the credential-keyed snapshot dict before it was ever
called from anywhere) was found and deleted rather than left behind.

Verification commands run for real:

```
$ chainbreak run scenarios/stale-authority/short-defer.yaml --provider fake --fake-profile eventual --seed 13
chainbreak run: COMPLETED -> runs\01KZN4T8H2EETY19HTZ8S6QVMT

$ chainbreak analyze 01KZN4T8H2EETY19HTZ8S6QVMT
chainbreak analyze: 2 finding(s), 0 detector check(s) -> runs\...\findings.json
$ jq '.findings[]|select(.type=="STALE_AUTHORITY")' runs\...\findings.json
                                       # classification: STALE_AUTHORITY_LIVE_CREDENTIAL, agent-c,
                                       # security_interpretation names it documented bearer-token
                                       # behavior in the same paragraph as the result (AC5)

$ chainbreak run scenarios/_negative-controls/nc-stale-credential-reuse.yaml --provider fake --seed 13
chainbreak run: COMPLETED -> runs\01KZN4TZAGFYCGM8SQSPJP49SG

$ pytest -m integration tests/integration/test_stale_authority.py -q
11 passed in 1.83s
```

**M14 — Silent-narrowing benchmark (Family E).** All five acceptance criteria met, against the
fake provider only — **never run against AWS** (out of scope by the milestone's own definition;
LLM workers are v0.4, also out of scope). Delivered: `execution/workers/base.py` (`TaskWorker` —
a `Protocol` defined purely over `CapabilityInvoker`/`InvocationResult`/`TaskStep` and a returned
`TaskOutcome`, nothing about how a worker decides anything — F1/ADR-007, so a future LLM-backed
worker implements the identical interface with no downstream change);
`execution/workers/deterministic.py` (four workers — `sequential`, the honest one, honoring
`on_failure` including a genuine one-shot retry; `always-complete`, the negative-control liar that
never invokes anything at all yet reports a fully self-consistent `COMPLETE`; `substituting`,
which invokes `identity.whoami` in place of its declared last step; `redelegating`, which attempts
`identity.delegate` mid-task in addition to its real steps — plus a `WORKERS` registry and
`resolve_worker`); `execution/task_runner.py` (`run_task` — builds the one capability-invoker
every worker is confined to, S1, wrapping `adapter.probe()` exactly as `matrix.py`/`deferred.py`
already do so SI-2/SI-3 apply to task actions unchanged; refuses every `identity.delegate`
invocation structurally, before it could ever reach the provider, and counts the attempt in its
own log rather than the worker's; computes `substituted_capabilities` by comparing the objective
invocation log against the plan's declared steps, collapsing consecutive same-capability repeats
first so an honest `on_failure: retry` is never mistaken for a substitution; records the output
marker only when the declared *last* step was genuinely the last thing invoked, under its own
capability, and it succeeded); `execution/side_effects.py` (`verify_output_marker` — F4, reads the
same store the runner wrote to, via a `provisioning_ref` parameter kept for a future real-adapter
bootstrap read even though the fake's own escape hatch does not need it); `analysis/task_contract.py`
(`task_contract_findings` — extracts `TaskOutcome`s from `TASK_OUTCOME_RECORDED` events and calls
three rule functions per task, each gated by that task's own declared `completion_contract`); two
new `analysis/rules.py` functions, `rule_capability_substituted`/`rule_redelegation_attempted`,
and two new `FindingType` members, `CAPABILITY_SUBSTITUTED`/`REDELEGATION_ATTEMPTED`
(AUTHORIZATION_MODEL §6 updated) — F5's "reported distinctly" requirement needed genuinely
distinct types, not just distinct text under the one pre-existing `SILENT_NARROWING`, since a
single task can trigger more than one contract violation at once and `Finding.subject_kind` is
regex-constrained to a fixed vocabulary that has no room for a per-violation tag; a new
`PlanPhase.TASK_EXECUTION` tag (excluded from the generic per-node authority-findings pass, the
same reasoning `POST_MUTATION`/`DEFERRED_EXECUTION`/`PAIRED_FRESH_CREDENTIAL` already established);
`execution/orchestrator.py`'s `TASK` branch (the last named-but-stubbed `PhaseKind`, and its own
trailing `else` is now structurally unreachable through any current enum value, kept only to fail
loudly if a future member is ever added without a branch); a new `TaskPlan`/`TaskStepPlan` pair
(`core/models.py`, `scenarios/compiler.py::_build_task_plans`, mirroring `MutationPlan`/`PollPlan`/
`DeferredExecutionPlan`'s established "compiled analogue, never import the scenario-layer spec
type" discipline); the fake adapter's `record_scratch_marker`/`scratch_marker_exists` escape
hatches (matching `advance_clock`/`enable_authority_caching`'s own precedent — simulated write-then-
independently-verify storage the fake has no other way to model, since it is a pure policy-decision
engine with no real object content).

Four genuine findings, not design choices:

1. **`redelegation_attempts`/`substituted_capabilities` must be computed by the executor, never
   trusted from a worker's own returned `TaskOutcome`, or the entire family's core guarantee
   collapses.** The Protocol lets a worker return anything in those two fields; if
   `execution/task_runner.py` had simply forwarded them, a dishonest worker could self-report zero
   substitutions and zero redelegation attempts regardless of what it actually did, and nothing
   downstream would ever know better — exactly the class of defect F4's marker-verification
   requirement exists to prevent, just for a different pair of fields. Fixed by keeping both fields
   entirely runner-owned: the invoker maintains its own call log (every real capability invoked,
   plus a separate counter for intercepted `identity.delegate` attempts) and `run_task` overwrites
   whatever the worker returned via `model_copy` after the fact, unconditionally. None of the four
   shipped workers needs to (or does) set either field meaningfully as a result.
2. **A naive "compare invoked capability to declared step, position by position" substitution
   check would misclassify a legitimate `on_failure: retry`.** A denied step retried once adds a
   second, same-capability entry to the invocation log at that step's own position, shifting every
   later position by one relative to the declared plan — the next real step would then appear to
   have been "substituted" by whatever the retry actually was, even though nothing dishonest
   happened. Caught by `tests/integration/test_task_workers.py::TestRetryDoesNotFalselyLookLikeSubstitution`
   before it ever reached the negative-control scenarios. Fixed by collapsing consecutive repeats
   of one capability in the invocation log (keeping the latest outcome) before the positional
   comparison runs, in `_collapse_consecutive_repeats`.
3. **The `substituting` worker's first implementation (reusing an earlier declared step's own
   capability as its substitute) would have been silently absorbed by finding 2's own fix.** If
   step 0 is `objectstore.read` and the substitute for the last step is also `objectstore.read`,
   the two adjacent same-capability log entries collapse into one exactly the way a legitimate
   retry does, erasing the substitution before the comparison ever sees it. Fixed before it shipped
   (caught while designing the collapse helper, not by a failing test) by having the worker
   substitute with `identity.whoami` instead — a control capability no legitimate declared step
   would plausibly name, so it can never collide with retry-collapsing.
4. **`scenarios/silent-narrowing/two-step-pipeline.yaml` and `scenarios/stale-authority/
   deferred-execution.yaml` were both already fully written, committed since M0, in the same
   "written as if the milestone had already landed" style M3/M5/M10 each left an instance of --
   and this milestone's own first attempt at authoring `two-step-pipeline.yaml` overwrote one of
   them with different content before noticing.** The original's premise (Agent B delegated one
   capability short of what its task needs, run with the *honest* `deterministic.sequential`
   worker) is EXPERIMENT_PROTOCOL.md section 5's own main procedure (steps 1-6) — a task failing
   loudly and correctly as `PARTIAL`/`EXPECTED_BEHAVIOR`, distinct from both
   `nc-silent-success.yaml`'s dishonest-worker case and F7's positive control. Reverted via `git
   checkout --` before it was ever committed; the positive control (F7, full authority, same task
   shape) now lives in its own new file, `two-step-pipeline-full-authority.yaml`, alongside the
   restored original.

Test files: `tests/integration/test_silent_narrowing.py` (10 — the restored `two-step-pipeline.yaml`
reports `PARTIAL`/`reported_insufficient_authority=True` and no `SILENT_NARROWING` finding, since
failing loudly is the desired outcome; `two-step-pipeline-full-authority.yaml` (F7) reports
`COMPLETE` with an independently verified marker; `nc-silent-success.yaml` end to end, `DETECTOR_OK`
at `HIGH` confidence, every finding's `caveats` naming the worker synthetic per AC5);
`tests/integration/test_task_workers.py` (10 — AC1, all four workers driven directly against a real
one-hop graph; the milestone's own explicit "reported distinctly" requirement — substituting and
redelegating each produce their own `FindingType`, never `SILENT_NARROWING` alone, and every
finding keeps a distinct `finding_id`); `tests/integration/test_side_effect_verification.py` (8 —
the milestone's own stated core case: `always-complete`'s self-report is internally consistent
(`steps_succeeded == steps_total`) yet independent verification still catches it, since it never
invoked anything at all; run-and-task-scoping; the no-escape-hatch fallback for a future real
adapter); `tests/unit/test_deterministic_workers.py` (5 — `on_failure: abort`, an all-denied
`FAILED` status, a non-final step also denied under `substituting`/`redelegating`, the unknown-
worker-id error). `tests/integration/test_negative_controls.py`'s `nc-silent-success` section,
previously rule-level only, now runs end to end through the real orchestrator in both directions —
the "fix" is the same compiled scenario with its `TaskPlan.worker` swapped to
`deterministic.sequential` via `model_copy`, following the exact migration pattern
`nc-stale-credential-reuse` used at M13.

Coverage: every M14-proper module (`execution/workers/base.py`, `execution/workers/
deterministic.py`, `execution/task_runner.py`, `execution/side_effects.py`,
`analysis/task_contract.py`) finished at exactly 100%. The scenario corpus grew by one file net
(24, from 23) — `scenarios/stale-authority/deferred-execution.yaml`'s and this milestone's own
`two-step-pipeline.yaml` M0-era scaffolds are both counted in every prior total already; only
`two-step-pipeline-full-authority.yaml` is genuinely new.

Verification commands run for real:

```
$ chainbreak run scenarios/silent-narrowing/two-step-pipeline.yaml --provider fake --seed 17
chainbreak run: COMPLETED -> runs\01KZNJP4H69J0ME94PEDEB8728

$ chainbreak analyze 01KZNJP4H69J0ME94PEDEB8728
chainbreak analyze: 2 finding(s), 0 detector check(s) -> runs\...\findings.json
                                       # both EXPECTED_BEHAVIOR: the honest worker's PARTIAL,
                                       # insufficient-authority report is not a finding -- failing
                                       # loudly is the desired outcome, per EXPERIMENT_PROTOCOL.md

$ chainbreak run scenarios/_negative-controls/nc-silent-success.yaml --provider fake --seed 17
chainbreak run: COMPLETED -> runs\01KZNJPG06ABPDY3SRWXH4E9GS
$ chainbreak analyze 01KZNJPG06ABPDY3SRWXH4E9GS
chainbreak analyze: 2 finding(s), 1 detector check(s) -> runs\...\findings.json
                                       # SILENT_NARROWING at HIGH confidence, DETECTOR_OK

$ pytest -m integration tests/integration/test_side_effect_verification.py -q
8 passed in 0.17s
```

**M15 — Per-category scoring.** All five acceptance criteria met. Delivered:
`scoring/categories.py` (`score_categories`, six evaluators — `_delegation_integrity`,
`_scope_attenuation`, `_revocation_responsiveness`, `_authority_freshness`,
`_failure_transparency`, `_credential_hygiene` — every one funnelled through a shared
`_finalize` that applies F2/F3/F4/S2 identically; `score_bundle(run_dir)` mirroring
`analysis/drift.py`'s bundle-reading convenience pattern; `not_measured_notice`, the literal
"NOT_MEASURED is not a pass." sentence SCORING_MODEL.md section 4's report shape requires, kept
as a standalone pure string function rather than pulled forward from M16); `scoring/coverage.py`
(`coverage_ratio`, `is_exercised` — the two decisions every evaluator shares: zero applicable
cells is `NOT_MEASURED` never `CONSISTENT`, and the model itself, not just this module, enforces
`coverage < 0.7` forcing `PARTIAL`); `scoring/confidence.py` (`category_confidence`, `min()`
across a coverage-tier baseline and every contributing finding, reusing `core/models.py`'s
already-existing `min_confidence` primitive rather than reimplementing aggregation);
`scoring/aggregate.py` (`aggregate_runs`, `RunScoreSet`, `score_set_from_bundle` — F7 refuses
runs whose `compiled_hash`/`adapter_version`/`catalog_version` differ unless
`allow_heterogeneous=True`, which only ever marks the result `heterogeneous=True`, never raises
confidence; F8's n/median/IQR/min/max with `iqr=None` below n=5, and excluded runs counted by
reason rather than dropped).

Two of the four required files' hardest design decisions turned out to already be half-answered
by earlier milestones: `min_confidence` (F4) already existed in `core/models.py` since M1, and
`CategoryResult`'s own model validator already enforced F3's coverage-forces-PARTIAL rule —
M15's job for both was wiring a category-level *evaluator* around primitives that already
existed, not inventing the primitives. What did not already exist, and needed real design work
building `scoring/categories.py`: (1) "applicable cells" per category is not one uniform
concept — `DelegationEdge`/`EdgeDivergence` (via `graph/divergence.py::analyze_graph`, which
already restricts to edges with *both* endpoints measured, reused directly rather than
re-derived) for Delegation Integrity and Scope Attenuation, `PollPlan` count *after excluding a
scenario's own pre-mutation warm-baseline poll* for Revocation Responsiveness (a naive
`len(scenario.poll_plans)` double-counted the warm-up poll AUTHORIZATION_MODEL.md section 5.1
itself recommends, understating coverage on every correctly-authored revocation scenario — caught
by actually running `scenarios/revocation/inline-deny.yaml` end to end and seeing coverage 0.5
where it should have been 1.0, not by reasoning about the model in the abstract), capability
count × trials for Authority Freshness (`DeferredExecutionPlan.capabilities` is a *set*, unlike
`PollPlan`'s single capability — a naive `len(deferred_execution_plans)` undercounted by exactly
that multiplier and crashed `coverage_ratio`'s own measured-exceeds-applicable guard the first
time a real short-defer.yaml run was scored, which is exactly the kind of bug `coverage_ratio`
raising instead of silently returning >1.0 exists to catch immediately rather than downstream);
(2) Credential Hygiene's "a credential remained usable after its stated expires_at" check is
deliberately broader than Authority Freshness's `EXPIRED_CREDENTIAL_ACCEPTED` finding — scanned
across *every* observation using a credential, not only `DEFERRED_EXECUTION` ones, since the two
categories measure genuinely different things even though both can fire from the same underlying
fact; (3) refactored `analysis/pipeline.py::_revocation_findings` to split out a new public
`revocation_measurements()` (the same measurement list `rule_revocation_delay`/
`rule_no_transition_observed` were already built from, now reusable by scoring without
re-parsing `events`/`observations` a second time) and added `AnalysisResult.populated_graph`
(the final accumulated graph, `None` when no authority-axis phase ran at all) — both additive,
zero existing tests touched.

Running the real scenario corpus end to end through the actual `scoring/` code (not just unit
tests against hand-built fixtures) surfaced two genuine findings, neither a scoring defect: three
of the six negative-control scenarios (`nc-scope-expansion`, `nc-non-monotone-chain`,
`nc-surviving-authority`) inject their defect only through `tests/fixtures/mini_orchestrator.py`'s
test-only `adapter.engine.apply_allow(...)` hook or a Terraform infrastructure profile that has
no fake-provider equivalent — a genuine `chainbreak run --provider fake` on any of the three never
triggers the defect, so `chainbreak analyze` correctly reports `DETECTOR_FAILED` for each,
exactly what S2 exists to surface; this is flagged as a follow-up rather than fixed here (a
fake-provider extension or scenario-language addition, out of M15's own file list — see the
new known issue below). Separately, the former stale-window gap is resolved: `analysis/stale.py`
receives the mutation send instant and `scoring/categories.py::_authority_freshness` consumes
the resulting `stale_window_seconds` rather than approximating it from `deferral_seconds`.

`cli/analyze.py` now writes `scores.json` alongside `findings.json` on every
`chainbreak analyze <run-id>` (via `scoring.categories.score_bundle`), echoes each category's
status/coverage/confidence, and prints the NOT_MEASURED notice when applicable; a new
`--aggregate-scores --scenario-id <id> [--allow-heterogeneous]` mode wraps
`scoring.aggregate.aggregate_runs` the same way `--aggregate --scenario-family <family>` already
wraps M11's depth-sweep aggregation. `evidence/writer.py` gained `write_scores`, structurally
identical to `write_findings` (redact-then-write, not part of the sealed `ARTIFACT_NAMES` root,
since both are regenerable from the sealed bundle alone).

Verification commands run for real:

```
$ chainbreak run scenarios/delegation-drift/four-hop.yaml --provider fake --seed 29
chainbreak run: COMPLETED -> runs\01KZNP8EH3DY2M14B2N5Q1GHYN

$ chainbreak analyze 01KZNP8EH3DY2M14B2N5Q1GHYN
chainbreak analyze: 5 finding(s), 0 detector check(s) -> runs\...\findings.json
chainbreak analyze: 6 categories scored -> runs\...\scores.json
  DELEGATION_INTEGRITY: CONSISTENT coverage 1.00 confidence HIGH
  SCOPE_ATTENUATION: CONSISTENT coverage 1.00 confidence HIGH
  REVOCATION_RESPONSIVENESS: NOT_MEASURED coverage 0.00 confidence INSUFFICIENT
  AUTHORITY_FRESHNESS: NOT_MEASURED coverage 0.00 confidence INSUFFICIENT
  FAILURE_TRANSPARENCY: NOT_MEASURED coverage 0.00 confidence INSUFFICIENT
  CREDENTIAL_HYGIENE: CONSISTENT coverage 1.00 confidence HIGH
NOT_MEASURED is not a pass. 3 of 6 categories were not exercised by this scenario.

$ pytest -m unit tests/unit/test_scoring.py -q
31 passed in 0.23s

$ grep -rn "composite\|overall_score\|total_score" src/
src/chainbreak/core/enums.py:270:    """Six independent categories. There is no composite score (ADR-010)."""
src/chainbreak/scenarios/export_schema.py:72:        "Per-category result. There is no composite score (ADR-010).",
src/chainbreak/scoring/categories.py:8:``composite``/``overall_score``/``total_score`` and expects to find nothing.
src/chainbreak/scoring/categories.py:482:    that section's own order. No composite: this function's return type is
                              # every hit is a docstring/comment *stating* ADR-010's decision, the
                              # same self-matching-grep shape M0's history already documents --
                              # confirmed by grep -rn "def.*score\b" src/chainbreak/scoring/*.py
                              # returning nothing, and by test_scoring.py's own module-introspection
                              # and return-type-annotation checks, which are the real assertion
```

Full suite: 1607 passed, 9 skipped, 23 deselected (was 1548 before M15 — +59 tests: `test_scoring.py`
31, `test_coverage.py` 12, `test_cross_run_aggregation.py` 12, `test_scoring_categories.py` 4).
`ruff`/`mypy` both clean across the full tree.

**M16 — Reporting and visualisation.** All five acceptance criteria met. Delivered:
`reporting/language.py` (EXPERIMENT_PROTOCOL.md section 7's rules as an actually-enforced lint,
not a style guide — `lint()`/`lint_report()` check forbidden phrases, a timing value with no
interval indicator on its line, a percentage with no denominator, the limitations section and
the literal "NOT_MEASURED is not a pass." sentence; `enforce_report()` is what every renderer
calls immediately before returning, applying the full lint to the report's own authored prose
and a narrower forbidden-phrases-only check to a `Finding`'s own evidence-derived free text — see
below for why); `reporting/figures.py` (seven evidence-derived figures — authorization graph,
per-hop intended-vs-effective, excess/missing capabilities per hop, revocation timeline with the
transition window shaded, stale-authority window, trial repeatability, cross-run scenario
comparison — hand-built inline SVG rather than Plotly, a deliberate deviation recorded in the
module's own docstring, see below); `reporting/data.py` (`gather_report_data`, one bundle-read
per report shared by all three renderers) and `reporting/render_context.py` (the one template
context `markdown.py`/`html.py` both render from, including the "blank every finding field and
re-render" trick that gives `enforce_report` a structural-text lint target with zero
evidence-derived prose without fragile output-parsing); `reporting/format.py` (`format_timing_result`,
the one function every renderer calls to print a timing result with n, interval, mechanism and
region — the four EXPERIMENT_PROTOCOL §7 names explicitly — and the shared `LIMITATIONS` text, so
the exact wording (and therefore `LIMITATIONS_TERMS`'s substring match against it) cannot drift
between formats); `reporting/terminal.py` (`rich`, rendered to plain text via
`Console(record=True)` rather than printed directly, so it is testable by string assertion and
the CLI decides how it reaches the terminal); `reporting/markdown.py` and `reporting/html.py`
(Jinja2, `templates/report.md.j2` and `templates/report.html.j2` — HTML with autoescape on and no
`|safe` anywhere in either template, verified by a grep-based test; Markdown deliberately
`autoescape=False`, since it is plain text, not an HTML injection surface, with a `noqa`/`nosec`
recording that as a reviewed decision, not an oversight). `cli/report.py` is now a real
implementation (`chainbreak report <run-id> --format {terminal,markdown,html} [-o path]
[--allow-unsealed]`), moved from a sub-`Typer` app to a plain function on the root app —
the exact `--format` misparse `cli/analyze.py`/`cli/run.py` had already documented and fixed,
reproduced directly against this module before switching.

Three things worth recording as genuine findings, not just design choices:

1. **Plotly cannot actually satisfy this milestone's own non-functional requirement.** The spec
   names Plotly for `figures.py`, but its only two paths to a self-contained, no-CDN report each
   violate a *harder* requirement stated in the same breath: `include_plotlyjs="inline"` embeds a
   multi-megabyte minified library before a single data point is drawn, alone exceeding "HTML
   report under 2 MB"; static image export (`kaleido`) needs a headless-browser binary this
   offline development environment cannot download, which would violate "no network fetches" at
   *build* time instead of render time. Hand-built inline SVG, generated programmatically from the
   same evidence Plotly would have been fed, satisfies F3's actual requirement (structured,
   evidence-derived charts, never hand-written numbers) without either conflict, and is
   additionally readable without JavaScript — the same category of judgment call M4's
   `rich_markup_mode` finding recorded, applied here to a harder constraint conflict.
2. **The language lint, applied naively to the whole rendered report, would have failed on
   already-shipped, already-tested M7/M13 finding text.** `analysis/rules.py`'s stale-authority
   caveat said "Not a vulnerability" (a literal forbidden-word hit, negation notwithstanding — the
   milestone's own instruction describes a blunt grep, not a negation-aware parser) and
   `rule_lifetime_capped`'s observation ("requested 3600s, granted 3600s") has no interval
   indicator the timing-heuristic would accept. Fixing every such pre-existing sentence across
   three earlier milestones' finding-rule text was out of this milestone's scope and risked
   breaking finding-wording assertions those milestones' own tests already lock in. The bounded
   fix: `enforce_report()` applies the full lint only to text the reporting layer itself authored,
   and a narrower forbidden-phrases-only check to verbatim `Finding` fields (ADR-006/F4 already
   requires rendering them under their own headings, unmodified) — plus the one real hit
   (`analysis/rules.py`'s "vulnerability") is fixed regardless, since no scoping decision makes a
   forbidden word in a rendered report acceptable.
3. **A real, reproducible crash, not a design decision.** `typer.echo()` on a native Windows
   console (cp1252, no UTF-8 code page) raises `UnicodeEncodeError` on any character outside that
   encoding — reproduced directly against this module's own en-dash usage before switching every
   generated string to ASCII (`-` instead of `–`) and, since evidence content itself is not
   guaranteed ASCII (an identity id, say), making `cli/report.py`'s stdout path write UTF-8 bytes
   directly with `errors="replace"` rather than trusting `typer.echo`'s console-codepage-dependent
   encoding. Caught only because this session ran the CLI for real against a real bundle rather
   than trusting the renderer unit tests (which run under pytest's own captured-output encoding
   and would never have surfaced it).

The former provenance gaps are resolved in the current run path: `cli/run.py` records the
environment region plus `git_commit` and `git_dirty` in the bundle provenance, and the report
layer consumes those fields. The response-shape fixtures remain documented transcriptions, not
live captures, with provenance files documenting that boundary.

Negative controls, all three performed for real: (1) a `ReportData` built with a `Finding` whose
`security_interpretation` contains `<script>alert('xss')</script>` renders the literal
`<script>` nowhere in the HTML output and `&lt;script&gt;` instead
(`TestXssEscaping` in `test_report_generation.py`); (2) `report.html.j2` was hand-edited to add
`AWS is vulnerable.` before the `<h1>`, `pytest
tests/integration/test_report_generation.py::TestAllThreeFormatsRender::test_html` failed with
`ReportLanguageError: 1 report-language violation(s)`, and the edit was reverted (confirmed by a
clean `grep -c "AWS is vulnerable"` afterward); (3) every figure's caption and the report header
carry `FAKE-PROVIDER APPARATUS CHECK` for a `provider: fake` run, asserted by
`TestFakeProviderStamp` counting occurrences against `1 + len(figures)`, not just checking `>= 1`.

A sample HTML report is committed at
[examples/reports/sample-scope-attenuation-fake.html](examples/reports/sample-scope-attenuation-fake.html),
generated for real via `chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake
--seed 1729`, `chainbreak analyze`, `chainbreak report --format html` — 21 KB, header and every
figure caption stamped `FAKE-PROVIDER APPARATUS CHECK`.

Verification commands run for real:

```
$ chainbreak report 01KZNVRCY521JN2YR886MN025N --format terminal
*** provider: fake -- FAKE-PROVIDER APPARATUS CHECK. This is not a measurement of any real
provider. ***
CHAINBREAK -- run 01KZNVRCY521JN2YR886MN025N
scenario scope-attenuation-basic v1.0.0    provider fake (adapter 0.1.0)
status COMPLETED    bundle_root_verified True
                          CATEGORY RESULTS
┌───────────────────────────┬──────────────┬──────────┬────────────┐
│ category                  │ status       │ coverage │ confidence │
├───────────────────────────┼──────────────┼──────────┼────────────┤
│ DELEGATION_INTEGRITY      │ CONSISTENT   │ 1.00     │ HIGH       │
│ SCOPE_ATTENUATION         │ CONSISTENT   │ 1.00     │ HIGH       │
│ REVOCATION_RESPONSIVENESS │ NOT_MEASURED │ --       │ --         │
│ AUTHORITY_FRESHNESS       │ NOT_MEASURED │ --       │ --         │
│ FAILURE_TRANSPARENCY      │ NOT_MEASURED │ --       │ --         │
│ CREDENTIAL_HYGIENE        │ CONSISTENT   │ 1.00     │ HIGH       │
└───────────────────────────┴──────────────┴──────────┴────────────┘
NOT_MEASURED is not a pass. 3 of 6 categories were not exercised by this scenario.

$ chainbreak report 01KZNVRCY521JN2YR886MN025N --format html -o /tmp/r.html && du -h /tmp/r.html
20K     /tmp/r.html

$ grep -rn '|safe' src/chainbreak/reporting/templates/ && echo FAIL || echo "no unsafe filters"
no unsafe filters

$ pytest -m unit tests/unit/test_report_language.py -q
32 passed in 0.09s
```

Historical M16 snapshot: 1744 passed, 9 skipped, 23 deselected (was 1607 before M16 — +88 new tests across
`test_report_language.py` (32), `test_no_unsafe_template_filters.py` (5),
`test_cli_report_command.py` (9), `test_report_figures.py` (18), `test_report_terminal.py` (11)
and `test_report_generation.py` (12), minus one `test_cli_commands.py` case moved out of the
generic "not yet implemented" sweep now that `report` has real behavior — net +86). `ruff`,
`mypy`, `lint-imports` (6/6 contracts kept) and `bandit -r src/ -q` all clean across the full tree.
`reporting/` itself: 99% coverage (`data.py`/`format.py`/`html.py`/`language.py`/`markdown.py`/
`render_context.py`/`terminal.py` all 100%; `figures.py` 99%, its one uncovered branch a
defensive guard against an edge referencing an identity outside `graph.nodes` that
`AuthorizationGraph`'s own validator already makes unreachable, marked `pragma: no cover` with
that reasoning inline rather than left unexplained).

**M18 — Reproducibility and hardening.** Offline portion complete (F1-F6, S1-S3); the milestone's
own file lists M17 as a dependency, and this pass deliberately did not attempt anything requiring
a real AWS account, per its own scoping note — see "Blocked" below for what that leaves open.
Delivered:

`analysis/compare.py` (F1-F3): `compare_bundles(RunSnapshot, RunSnapshot, ...)` classifies every
comparable measurement between two runs into REPRODUCIBILITY.md section 1's three levels.
Set-valued findings (everything except `REVOCATION_DELAY`/`NO_TRANSITION_OBSERVED`) are compared
by exact-multiset content fingerprint, excluding `finding_id` and `evidence.*_refs` — both are
salted per run (ADR-013) and therefore provably unique across any two independently-produced
runs even when the measured behavior is identical, so including them would report every finding
DIVERGENT on every cross-run comparison. Timing (`RevocationMeasurement`, read directly rather
than through `findings.json` — most transition windows never produce a `REVOCATION_DELAY`
finding at all, since that rule only fires past an *assertive* expectation) is compared by
interval overlap, never bit-exact equality, per REPRODUCIBILITY.md's own "anyone claiming exact
timing reproducibility... is mistaken." Refuses (`HeterogeneousComparisonError`, reusing the
exact error class and message shape `scoring/aggregate.py::aggregate_runs` already established
for the identical F7 refusal) across differing `compiled_hash`/`adapter_version`/`catalog_version`
without `--allow-heterogeneous`, and across differing `infrastructure_fingerprint` without
`--cross-operator`, both prominently noted rather than silently downgrading a verdict.

One deliberate wording deviation from M18's own shorthand, recorded here because it is a genuine
interpretation call, not an oversight: the milestone's negative-controls bullet paraphrases
"same scenario, same seed, twice" as "must report identical." REPRODUCIBILITY.md section 1's own,
more careful text reserves "identical" (Level 1) for *the same evidence bundle re-analyzed*; two
independently-produced runs — even with the same seed — are Level 2 at best, since their
`finding_id`/`observation_refs` differ by construction (ADR-013 again). `compare_bundles`
therefore reports `STRUCTURALLY_IDENTICAL` for two different runs whose content matches exactly,
reserving `IDENTICAL` for literal self-comparison (`run_a.run_id == run_b.run_id`), and never
reports a cross-run timing match as `IDENTICAL` even on a bit-exact coincidence. Verified for
real: `scenarios/scope-attenuation/basic.yaml --seed 42` run twice → 3/3 comparisons
`STRUCTURALLY_IDENTICAL`, 0 divergent; `scenarios/revocation/inline-deny.yaml` run at
`--fake-profile eventual --seed 1` and `--seed 2` → the two structural (non-timing) findings both
`STRUCTURALLY_IDENTICAL`, the revocation timing comparison `DISTRIBUTIONALLY_CONSISTENT` with real
overlapping-but-different windows (`[1.500, 2.000]s` vs `[2.000, 2.500]s`), never `IDENTICAL` —
exactly M18's own negative-controls intent, in the vocabulary REPRODUCIBILITY.md section 1
actually defines.

`evidence/archive.py` (F4, S1): `create_archive` builds on `evidence/export.py::export_public`
directly — scrubbing into a temporary staging directory (not `export_public`'s own permanent
`<run_id>-public` sibling; `--archive` promises exactly one artifact, the tarball) — so there is
no code path that produces an unscrubbed archive; S1 is structural, not a flag check. Refuses
(rather than silently mislabeling) if the `catalog.yaml` on disk does not match the run's own
recorded `capability_catalog_version`, or if no `schemas/` directory is found. That second refusal
is a real, documented limitation: `schemas/` is not shipped as installed package data (verified by
inspecting a built wheel — it is entirely absent), so `--archive` only works from a repository
checkout today, not a wheel install; noted in both the module docstring and REPRODUCIBILITY.md
section 8. New writer primitives `write_bytes_artifact`/`create_tar_archive` in
`evidence/writer.py` keep S1's "only writer.py opens a file for writing inside evidence/" lint
rule literally true rather than adding archive.py to its exemption list. Self-containment verified
by extracting a real archive with `tarfile` into an isolated directory and confirming every
artifact `ARTIFACT_NAMES` names, `catalog.yaml`, every `schemas/*.schema.json`, and `REPRODUCE.md`
are all present with no reference back to the source repository.

`evidence/migrate.py` (F5): a migration registry (`register_migration`/`migrate_bundle`) rather
than a concrete transformation — `BUNDLE_FORMAT_VERSION` has been 1 since M6 and has never
changed, so there is genuinely nothing to migrate from yet. Tests register a synthetic v1→v99
migration through the module's own public API to prove the mechanism (registry, dispatch, and
F5's "preserving the original" guarantee, checked by hashing the source tree before and after and
asserting byte-for-byte equality) rather than inventing a fictitious real transformation.

`Provenance.seed` (`core/models.py`) and `cli/run.py`'s provenance dict both gained a `seed`
field — REPRODUCIBILITY.md section 2 already documented "every seed used" as something every run
records, but the top-level `--seed` was not actually threaded into `manifest.json` anywhere before
this (only a sha256-derived *per-matrix* shuffle seed was, in `PROBE_ORDER_SHUFFLED` events, which
cannot be inverted back to the original `--seed`). `schemas/experiment-run.v1.schema.json`
regenerated and diffed clean (`python -m chainbreak.scenarios.export_schema`).

`Dockerfile`/`.dockerignore` (F6, S2): multi-stage build (wheel build stage, then a slim runtime
stage installing only the base package plus the `report` extra — no `aws`/`dev`/`analysis`, so
boto3 never enters the image and there is no code path inside it that could reach AWS even by
accident), non-root user, 68 MB (budget 500 MB). Byte-identical determinism verified the way
ADR-013 actually permits: `graph.json`, `scenario.json`, `policy_states.jsonl` and
`credentials.jsonl` sha256-matched exactly between a container run and a host run of the same
scenario+seed; `observations.jsonl`/`events.jsonl` did **not** match byte-for-byte, because both
embed `identity_ref_hash` and similar identifiers salted per `run_id` (ADR-013) — a property of
any two independently-invoked runs, container or not, never something the container introduced.
`chainbreak compare` between the two bundles reported 3/3 `STRUCTURALLY_IDENTICAL`, 0 divergent,
which is the correct, ADR-013-respecting statement of "the container's fake provider behaves
identically to the host's" — a literal byte-diff of the salted streams would have been a
misleading test, not a stronger one.

`requirements.lock` + `scripts/lock_from_report.py` (S3, T-14): 90 third-party packages pinned
with sha256 hashes, covering `.[dev,aws,report,analysis]`'s full resolved closure (chainbreak
itself excluded — installed separately, `--no-deps`, since it is the local package under test,
not a pinned download). Generated inside a Linux `python:3.12-slim` container (matching CI's
`ubuntu-latest`/cp312 target), not on the resolving Windows host, and not with pip-tools: pip-tools
7.6.0 raises `ImportError` on `pip._internal.utils.compat.stdlib_pkgs` against the pip version in
this environment (a pip-internal API pip-tools depends on that has since moved), so
`lock_from_report.py` instead reshapes `pip install --report`'s own JSON output — pip's stable,
already-hash-bearing resolution record — into the `--require-hashes` format. `ci.yml`'s `security`
job gained a step that installs `requirements.lock` with `--require-hashes` into a fresh, isolated
venv (a job's already-populated venv would prove nothing, since `--require-hashes` only demands
hashes for what it is *about to install*, not what is already present), then `pip install --no-deps
.` on top and an import smoke test — verified passing in a from-scratch Linux container before
being committed to CI.

Two genuine, pre-existing bugs found and fixed while doing this work, neither hypothetical:

1. **`pyproject.toml`'s `moto[...]` dev extra named a nonexistent extra, `lambda`.** Silently
   tolerated by every `pip install` so far (pip warns "does not provide the extra" and proceeds
   anyway when it can otherwise resolve from a warm cache), but it turned an ordinary
   dependency resolution into `pip`'s `resolution-too-deep` failure the moment a fresh,
   cross-platform, no-cache resolution actually needed to backtrack across moto versions
   looking for one that satisfied it. moto's real extra is `awslambda`
   (`importlib.metadata.distribution("moto").metadata.get_all("Provides-Extra")` confirmed it
   directly). Fixed; `requirements.lock`'s own successful generation is the regression test.
2. **`tests/unit/test_import_boundaries.py`'s `_AWS_SERVICE_STRING_RE` had no word boundary**,
   so it matched "sts:" inside any ordinary English word ending "...sts:" — exists:, consists:,
   lists:, tests:, costs:, resists:, persists:, and more — not just genuine AWS action strings.
   Found because `evidence/migrate.py`'s own error message ("migration target already exists:")
   tripped it for real the first time this check ran against that file. Fixed with a
   `(?<![A-Za-z])` lookbehind; added `test_regex_does_not_false_positive_on_ordinary_english_words`
   and `test_regex_still_detects_real_aws_service_strings` (parametrized, both directions) so a
   future edit to this regex cannot silently reintroduce either failure mode.

Coverage: `analysis/compare.py` 97% (two uncovered branches: `_finding_label`'s `edge_id` arm,
untested because no test fixture constructs an edge-kind `Finding`; and the defensive
`AnalysisError` raised when `transition_observed=True` but `transition_window` is `None`, which
`RevocationMeasurement`'s own validator already makes unreachable); `evidence/archive.py` 94%
(the "no schemas/ directory" and "schemas/ directory present but empty" refusal branches,
untested because this development environment's `schemas/` always exists and is non-empty);
`evidence/migrate.py` and the extended `evidence/writer.py` both 100%.

```
$ pytest -m "unit or integration" -q
Historical M18 snapshot: 1744 passed, 9 skipped, 23 deselected
$ ruff check . && mypy
All checks passed! / Success: no issues found in 120 source files
$ lint-imports
Contracts: 6 kept, 0 broken.
```

The pre-M18 historical suite was 1693; +51 net (test_compare.py 24, test_archive.py 7,
test_migrate.py 10, test_compare_negative_controls.py 2, test_cli_runs_command.py's two new
`--archive` cases, test_import_boundaries.py's two new regex-regression cases, minus one
`test_cli_commands.py` case retired now that `compare`'s own real behavior has a dedicated test
class — the same "generic stub sweep loses a case, a real test file gains one" pattern M6/M7/M9/
M10/M16 each went through).

### Blocked

M18's `--cross-operator`/`--allow-heterogeneous` refusal paths are unit-tested directly (hand-built
`RunSnapshot`s with differing versions) rather than exercised via two real, differently-versioned
runs, since this repository only ever ships one catalog/adapter version at a time — nothing to
block on here, just noted for completeness. What genuinely remains for M18 is real-AWS Level 2/3
comparison (two real AWS runs of the same scenario, `compare`d against each other) and real-AWS
archive/migrate exercise, both pending on the separate M17 evidence bar rather than on account
provisioning.

M8 and M9 dedicated-account criteria are complete. M18's real-AWS comparison and archive/migrate
exercise remain pending on a valid M17 evidence bar.

### Not started

M19 has not started. M17 has only invalid/incomplete attempts and zero valid/publishable blocks;
M18's offline portion is complete and its real-AWS comparison remains pending. See
[docs/implementation/MILESTONES.md](docs/implementation/MILESTONES.md).

---

## Tests

```
Historical pre-current-refresh snapshot: 1744 passed, 9 skipped, 23 deselected in ~90s   (Python 3.12.7, pytest -m "unit or integration")
23 skipped, 1752 deselected                     (Python 3.12.7, pytest -m "aws or e2e" -- gated by CHAINBREAK_ALLOW_AWS_TESTS)
```

| Suite | Tests | Covers |
|---|---|---|
| `tests/unit/test_domain_contract.py` | 41 | Set algebra, secret non-serializability, safety envelope rejection, graph invariants G-1/G-2, divergence at node level, outcome classification, interval ordering, min-confidence, lifetime capping, catalog integrity, binding validation, SI-11 literal-infrastructure rejection, ULID monotonicity |
| `tests/scenarios/test_scenario_corpus.py` | 52 | Every scenario validates; capability closure (G-4); negative controls are correctly located and marked; all six defect kinds covered; all five families present (parametrized per scenario, so this grows with the corpus — 24 scenarios as of M14) |
| `tests/unit/test_import_boundaries.py` | 14 | ARCH-1: core imports nothing internal, graph imports only core, boto3 confined to `providers/aws/`, AWS service strings confined to `providers/` and `AWS_PROVIDER_SPEC.md`, plus two planted-violation negative controls and a third proving a denied teardown unlink warns rather than fails the test and is caught as leftover debris (S1); M18 added two parametrized regression tests (both directions) for `_AWS_SERVICE_STRING_RE`'s word-boundary fix, after the unfixed regex false-triggered on `evidence/migrate.py`'s own "already exists:" |
| `tests/aws/test_placeholder.py` | 1 (skipped by default) | F5: proves the `aws`/`e2e` marker gate in `tests/conftest.py` actually skips, and actually un-gates under `CHAINBREAK_ALLOW_AWS_TESTS=1` |
| `tests/aws/test_disambiguation.py` | 24 | Explicit-vs-implicit denial message classification against literal AWS strings across all five documented policy-kind nouns; Lambda `FunctionError` vs not; S3 403/404 shape; recognized/unrecognized access-denied codes |
| `tests/aws/test_retry.py` | 28 | Transient-code classification including the never-retry-wins-over-503 ordering; full-jitter bounds with a seeded RNG; `call_with_retry`'s success, non-transient-immediate, transient-then-succeeds and exhaustion paths, each reporting the correct attempt/retry count |
| `tests/aws/test_terraform_outputs.py` | 6 | `load_terraform_outputs` against a valid bare-value document, a valid `terraform output -json`-wrapped document, a missing file, malformed JSON, a non-object document, and missing required names |
| `tests/aws/test_policy_synthesis.py` | 5 | One statement per intended capability plus the always-present whoami grant, never duplicated when requested explicitly, the empty-intent case, the 2048-char STS limit (this is `providers/aws/policy_synthesis.py`, the real session-policy JSON; `tests/unit/test_policy_synthesis.py` below is the unrelated provider-neutral placeholder of the same name in `scenarios/`) |
| `tests/unit/test_policy_synthesis.py` | 7 | `scenarios/policy_synthesis.py`'s size-checked, fingerprinted placeholder policy: deterministic fingerprint/size for a repeated capability set, the empty-capability-set case still synthesizes rather than erroring, the size-limit error path raises `ScenarioSemanticError` naming the identity, edge (present and absent) and both sizes (S1 — previously exercised only incidentally through `compiler.py`, never on its own error path) |
| `tests/aws/test_adapter_moto.py` | 68 | Every AWS adapter module against real boto3 clients hitting moto's in-memory AWS: preflight P1–P4/P6/P7/P8/P9/P10 pass/fail paths, all five delegation mechanisms including the 3600s chain cap and session-policy attachment, all ten probes' success and denial/error-shape paths, all six mutation kinds, policy snapshot fingerprinting and change detection, a full register→delegate→probe→mutate→snapshot walk through `AwsProviderAdapter` itself, and (S1) the remaining eight `_build_call` dispatch arms `TestAdapterEndToEnd` didn't reach, `_build_call`'s own unresolved-capability fallback, `delegate()`'s no-live-session guard, the allowlist before-call hook's both branches against a stub client, and `_call_and_classify`'s three post-retry paths (apparatus-fault re-raise, non-`ClientError` re-raise, `ClientError` classified) via a monkeypatched `call_with_retry` |
| `tests/aws/test_adapter_real.py` | 21 (skipped by default) | The shared `ProviderContractSuite` behavioral assertions with AWS fixed-role setup hooks, plus IAM-semantics tests named in M8's own spec — role-chain capping by real STS, session-policy-cannot-grant, explicit-deny-wins, the denial-message-wording canary, the S3 403/404 precondition proof, missing-marker-is-`CONFIGURATION_ERROR`, whoami-never-denied, out-of-namespace-refused, and the wrong-account call-log gate. **Executed in the dedicated account: 21 passed**. |
| `tests/unit/test_cli_infra_command.py` | 21 | `plan`/`apply`/`destroy`'s argument handling against an unknown environment and a missing `terraform` binary; `status` against no captured outputs, valid outputs, and malformed outputs; `verify-clean` against `mock_aws()` — nothing tagged, something tagged, no region available, a captured region used automatically, independence from a never-checked-out environment directory (F5), and a malformed captured `outputs.json` falling back past `_region_hint`; and (S1) `plan`/`apply`/`destroy`'s real command bodies against a mocked `subprocess.run` — an init failure, a missing-tfvars-style plan failure, apply success capturing outputs, apply failure never capturing them, an output-capture failure after a successful apply, and a destroy that partially fails propagating its exit code |
| `tests/aws/test_cleanup_contract.py` | 2 (skipped by default) | M9's own "Tests" section verbatim: apply → preflight passes → destroy → destroy again (no-op) → verify-clean reports nothing remaining; a second apply is also a no-op. **Executed in the dedicated account: 2 passed** after the scoped IAM inspection permission and CLI no-op-summary fix |
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
| `tests/unit/test_scenario_loader.py` | 26 | All 17 shipped scenarios compile; each of the four invalid fixtures yields its documented exit code (2/3/4/5); an orphaned (never-delegated-to) identity; `load_and_compile`'s exception and success paths |
| `tests/unit/test_scenario_compiler.py` | 8 | `compiled_hash` determinism across two calls and two independent subprocess interpreters, and that it changes with catalog version; F2 expected-authority derivation against the worked example; auto-inserted `SNAPSHOT`s around a real `MUTATE` phase; one `SynthesizedPolicy` per delegation; negative controls compile without errors |
| `tests/unit/test_probe_matrix.py` | 7 | `identity.whoami` in every universe; the `scenario` universe includes capabilities a node must *not* hold (the point of the default); `declared` is per-target-identity; `catalog` is everything; one matrix per `PROBE`/`DEFERRED_EXECUTION` phase; trials from the execution block |
| `tests/unit/test_scenario_safety.py` | 15 | Literal ARN/account-id/region/URL rejection (with `example`/`localhost` exempted); oversized documents; custom and `!!python/object` YAML tags rejected; invalid YAML syntax; non-mapping documents; excessive node count and nesting depth |
| `tests/unit/test_export_schema.py` | 7 | Every registered schema export is valid draft 2020-12; `main()` writes one file per export with the default and an explicit output directory |
| `tests/unit/test_scenario_schema_extra.py` | 42 | Every `ScenarioSpec` sub-model validator failure branch: timing/concurrency, root/agent capability declarations, session-policy source exclusivity, delegation mechanism and self-delegation checks, all seven `PhaseSpec` kind requirements (M13 added `WAIT`'s positive-`wait_seconds` and `DEFERRED_EXECUTION`'s `target_identity` checks), all `ExpectationSpec` kind requirements, `ScenarioSpec`'s full referential-integrity sweep, negative-control id marking |
| `tests/unit/test_config_layering.py` | 18 | All four config layers individually and combined, later-wins semantics, a partial layer never clobbering an untouched field, env tuple/int/bool coercion, a `None` CLI override not overwriting an earlier layer, `resolve_safety_envelope` success/failure, fingerprint determinism |
| `tests/unit/test_safety_gate.py` | 16 | Missing envelope; wildcard account and duration-over-14400s both collapsing to the envelope-construction-refusal path; account/region/namespace checks (SI-2, SI-5, S1); cost within/over ceiling; `estimate_cost` conservatism (S4) against a real compiled scenario |
| `tests/unit/test_clock.py` | 12 | `RunClock` before/at/past its deadline via an injected fake monotonic source, `elapsed_seconds`/`remaining_seconds`/`expired`, the real `time.monotonic_ns` default path, `no_offset_estimator` |
| `tests/unit/test_logging_filter.py` | 14 | AKIA/ASIA keys, a simulated botocore DEBUG record with a JSON-quoted session token (acceptance criterion 3), key=value and JSON-quoted spellings, `install()` idempotence, third-party loggers covered even with `propagate = False` set on themselves |
| `tests/unit/test_cli_surface.py` | 5 | S1: no option anywhere in the real command tree matches a bypass keyword; `--auto-approve` deliberately not flagged (documented exception); the negative-control detector both catches a planted `--skip-safety` fixture and stays silent on a clean one |
| `tests/unit/test_cli_commands.py` | 17 | F3: each of `validate`'s six checks at the function level, plus an end-to-end `CliRunner` pass on a correct config (text and `--json`) and an informative failure on a missing one; F4: the remaining not-yet-implemented command (`compare` — `runs`/`evidence export --public` resolved by M6, `analyze` resolved by M7, `infra {plan,apply,destroy,status,verify-clean}` resolved by M9, `run --provider fake` resolved by M10, `report` resolved by M16 — see `test_cli_infra_command.py`, `test_cli_run_command.py` and `test_cli_report_command.py` respectively) exits 2 with "not implemented until M\<n\>", never a stack trace; AWS-provider wiring is implemented and acceptance-tested separately |
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
| `tests/integration/test_fake_scenario_compatibility.py` | 73 | Acceptance criterion 4: every one of the 24 real shipped scenarios (12 at M5; M11 added the four missing delegation-drift depths plus `role-chain-five-hop.yaml`; M12 added `remove-policy`/`revoke-older-sessions`/`delete-session-scope`; M13 added `short-defer`/`long-defer`/`post-expiry`; M14 added `two-step-pipeline-full-authority.yaml`), compiled for real and walked (register, delegate along every edge, probe every matrix cell) through all three fake profiles, crash-free (72 parametrized cases) plus a corpus-count guard |
| `tests/unit/test_redaction.py` | 369 | Reflection-discovers every `DomainModel` subclass and every unconstrained-free-text field on it; property sweep over a six-shape secret corpus per field asserting `redact()` raises or the secret appears in no output byte; SecretMaterial/bare-frozenset/opaque-value branches; `redact_message()`'s in-place ARN substitution; the S1 no-unsafe-file-write grep |
| `tests/unit/test_evidence_schema.py` | 5 | The golden bundle's manifest and per-record artifacts validate against `schemas/*.json`; the embedded SQLite schema stays in sync with `schemas/run-index.sql` |
| `tests/unit/test_sealing.py` | 13 | Golden bundle verifies, tampered bundle fails verification, sealing refuses an incomplete bundle, the writer's full lifecycle (duplicate dir, context manager on normal/exceptional exit, double close, write-after-close, `manifest.verify()`'s unsealed and artifact-set-mismatch branches), F2's leave-a-partial-bundle guarantee |
| `tests/unit/test_bundle_ingest_safety.py` | 9 | T-10: oversized/malformed `.jsonl` lines and single-document JSON artifacts rejected with a bounded, named exception; the exact-boundary case accepted; a structurally invalid `findings.json` entry refused |
| `tests/unit/test_public_export_scrub.py` | 8 | F6: a bundle seeded with an ARN, account ID, hostname and policy document in several places has all four stripped and reported in the diff; `--dry-run` writes nothing; `--include-policy-documents` opts back in; a clean bundle strips nothing; unsealed and tampered bundles are refused |
| `tests/unit/test_evidence_index.py` | 10 | F5: schema creation/idempotence, upsert-and-get (including on-conflict update), `index_findings` populating `findings`/`detector_checks` from a hand-built fixture, `reindex` rebuilding from disk (skipping a manifest-less directory) including against the committed golden bundle |
| `tests/unit/test_evidence_reader.py` | 8 | Reader-side validation-error paths for each of `read_manifest`/`read_findings`/`read_observations`/`read_policy_states`/`read_credentials`; `read_events`' bare-dict pass-through |
| `tests/unit/test_evidence_verify_cli.py` | 3 | `python -m chainbreak.evidence.verify` against a verified bundle, a tampered one, and bad usage |
| `tests/unit/test_cli_runs_command.py` | 6 | `runs reindex`\`then\`list\`/\`show\` against a real indexed bundle, an empty runs root, a missing run, `evidence export --public --dry-run`, and the documented non-`--public` stub |
| `tests/unit/test_authority_aggregation.py` | 17 | F1 unanimity: all-`ALLOWED`, unanimous denial, mixed-kind denial → `DENIED_UNATTRIBUTED`, each excluded-outcome reason; `aggregate_observations` grouping and trial ordering; F2/AUTH-1: allowed capability included, denial excluded but classified, never-probed vs. error exclusion reasons, coverage; `populate_observed_authority` against a real graph including the wrong-phase-ignored and unexpected-gain-detected cases |
| `tests/unit/test_confidence_gate.py` | 13 | AUTHORIZATION_MODEL §6's formula: coverage thresholds, unanimity requirement, policy-snapshot failure, an empty cell list forced to `INSUFFICIENT` regardless of claimed coverage, `confidence_rationale`'s text for each gate outcome |
| `tests/unit/test_finding_rules.py` | 38 | Every rule function's predicate, both firing and non-firing branches; `_build`'s deterministic `finding_id` and `confidence_override` bypass; the `INSUFFICIENT` → `INCONCLUSIVE` type substitution |
| `tests/unit/test_revocation_math.py` | 12 | `compute_revocation_window`'s interval-with-jitter math, `NO_TRANSITION_OBSERVED_WITHIN_WINDOW`, `test_oscillation_preserved_not_smoothed` and `test_clean_transition_is_not_flagged_non_monotonic` locking in the chronological-scan fix |
| `tests/unit/test_stale_classification.py` | 9 | The six-row stale-authority table, each row with a fixture naming it, paired-fresh-credential disambiguation |
| `tests/unit/test_detector.py` | 6 | `check_negative_control` against a matching finding (`DETECTOR_OK`), a missing one (`DETECTOR_FAILURE`), and `_capabilities_satisfied`'s matching logic |
| `tests/unit/test_cli_analyze_command.py` | 4 | `chainbreak analyze` against a sealed golden bundle, a tampered bundle refused without `--allow-unsealed`, the same bundle accepted with it, a missing run id |
| `tests/integration/test_known_truth_divergence.py` | 2 | C-9: a fake adapter configured with a known authority mismatch produces exactly the expected `AUTHORITY_EXPANSION`/`DELEGATION_DRIFT` findings at exactly the expected confidence |
| `tests/integration/test_known_truth_timing.py` | 2 | The `eventual` profile's known 2000ms `propagation_delay_ms`; the measured transition window is asserted to contain it, both through the finding layer and directly against the interval math |
| `tests/integration/test_analyze_idempotence.py` | 2 | F8: `analyze` run twice against the same real (diverging, then clean) bundle produces byte-identical `findings.json` and identical `finding_id`s |
| `tests/integration/test_negative_controls.py` | 12 | Acceptance criterion 3: all six `nc-*` scenarios against the real fake provider produce their declared finding and `DETECTOR_OK`; the same six with the defect "fixed" produce `DETECTOR_FAILURE` instead — `nc-stale-credential-reuse` joined this real-orchestrator group at M13 (a `MUTATE`-step-stripped `model_copy` for its "fix"), `nc-silent-success` at M14 (a `TaskPlan.worker`-swapped `model_copy`, dishonest worker replaced with `deterministic.sequential`) |
| `tests/integration/test_scope_attenuation.py` | 7 | M10 acceptance criteria, through the real `execution/orchestrator.py`: `scope-attenuation/basic.yaml` end to end producing a sealed bundle and findings with no `AUTHORITY_EXPANSION` (criterion 1); both scope-attenuation negative controls in both directions via the same fake-side defect injection `test_negative_controls.py` established (criterion 2); the probe-order seed recorded and replaying it reproducing the identical order, a different seed producing a different one (criterion 4) |
| `tests/integration/test_control_capability.py` | 4 | C-1/acceptance criterion 3: `calibrate_matrix` succeeds and returns one observation per control capability; a throttled apparatus (every call including `identity.whoami`'s own fails) raises `ControlCapabilityFailedError` naming the identity and matrix; the full orchestrator discards every matrix in the run (not just one identity's row) and writes zero observations for any of them, only a `MATRIX_DISCARDED` event each |
| `tests/integration/test_probe_matrix_execution.py` | 9 | Trial repetition (every non-control capability gets exactly `matrix.trials` observations, trial numbers `1..trials`); C-6's shuffle reproducing identically for the same `(seed, matrix, identity)` and differing for a different seed; C-2's precondition check raising before any probe runs, naming the failed marker, and passing cleanly when all markers are present; F6's `needs_redelegation` threshold math, `ensure_fresh_credential` actually re-delegating and recording a `CREDENTIAL_REDELEGATED` event, being a no-op for a healthy credential, and never firing for the root identity (no edge, no expiring credential) |
| `tests/integration/test_orchestrator_error_paths.py` | 9 | An unmapped scenario phase name raising a named `ExecutionError` rather than guessing; a failed preflight aborting before `finalize()` runs (F2: partial evidence left on disk, no `manifest.json`); F6 re-delegation actually firing mid-run and being recorded; historical coverage of the former `WAIT`/`DEFERRED_EXECUTION`/`TASK` milestone errors; a synthetic `MUTATE`/`POLL` step with no matching compiled `MutationPlan`/`PollPlan` correctly reported as a compiler invariant violation, not "not implemented" (M12: both are real now); `SNAPSHOT` a harmless no-op when reached |
| `tests/integration/test_cli_run_command.py` | 9 | `chainbreak run`'s CLI-level argument handling (missing/unknown scenario, unknown provider, implemented `--provider aws` wiring, an unknown `--fake-profile`, a structurally invalid scenario exiting 1 not a stack trace), the `--fake-profile eventual` happy path, and the fake-provider happy path through a real `CliRunner` invocation, including `chainbreak analyze` consuming the bundle it produced |
| `tests/unit/test_drift_aggregation.py` | 9 | M11 F6: `build_depth_result`'s hop/divergence/exclusion counting against a hand-built graph (root never counted as a hop); `DepthResult`'s rate properties guard against division by zero; `summarize_depth_sweep`'s confound verdict in both directions (stable or divergence-only-rising rates are not inconclusive; both rates rising together is, and names why) plus depth-order-independent input |
| `tests/unit/test_chain.py` | 2 | `materialize_chain`'s S1 depth guard: within bound delegates to `delegation.materialize_graph` normally; over bound raises a named `ExecutionError` before any delegation happens |
| `tests/integration/test_delegation_drift.py` | 6 | M11 acceptance criteria, through the real `execution/orchestrator.py` (via `execution/chain.py`): AUTHORIZATION_MODEL section 7's worked example end to end (hop 3 `ORIGINATED`, hop 4 `PROPAGATED` citing hop 3's finding, first divergence at hop 3 reaching real path-analysis output); hop 4 `CORRECTED` when it drops hop 3's gain, with no finding raised at all; citation surviving three propagated hops past the origin (the bug M11 found and fixed); `nc-non-monotone-chain` in both directions. Uses `role-chain-five-hop.yaml`, a test-support fixture (plain `ROLE_CHAIN` throughout — see its own docstring for why the depth-sweep scenarios can't carry an identity-policy-level defect past their session-policy-scoped hops) |
| `tests/integration/test_depth_sweep.py` | 10 | M11 acceptance criteria 1 and 4: each of depths 2–6 runs end to end and yields a `DepthResult` with the correct depth, hop count and cell count; a clean five-depth sweep built from real bundles is not inconclusive; a sweep with one synthetic high-divergence/high-exclusion result appended is correctly flagged inconclusive; `chainbreak analyze --aggregate --scenario-family` end to end via `CliRunner`, including its own `--scenario-family`-missing and no-matching-runs error paths |
| `tests/integration/test_revocation.py` | 15 | M12 acceptance criteria, through the real `execution/orchestrator.py`: all five mechanisms complete and record their kind with a confirmed receipt and a revert log; the three positive mechanisms (`ATTACH_INLINE_DENY`, `REMOVE_INLINE_POLICY`, `REVOKE_OLDER_SESSIONS`) reach `STABLE_DENIAL`; `inline-deny.yaml`'s mutation is actually reverted (`objectstore.read` restored on the live adapter), `revoke-older-sessions.yaml`'s is correctly reported unrevertable; both negative controls (`trust-policy-null-condition.yaml`, `nc-no-revocation.yaml`) report `NO_TRANSITION_OBSERVED`; the measured window contains the true propagation delay at 0/500/2000/10000ms through the real orchestrator (not `mini_orchestrator`); a forced `REVOCATION_DELAY` finding's `transition_window` is a `{low, high}` pair, never a bare scalar (F5) |
| `tests/integration/test_polling.py` | 5 | `execution/polling.py`'s `STABLE_ALLOW`/`STABLE_DENIAL`/`TIMEOUT` stopping conditions exactly at the right poll count against a real compiled graph and adapter; a `stop_on: TIMEOUT` phase running its full budget even when every poll would have satisfied `STABLE_ALLOW`; the not-materialized-identity guard |
| `tests/unit/test_revert.py` | 9 | `execution/revert.py`: every `MutationKind`'s actionability and human-readable action text (`ATTACH_INLINE_DENY`/`REMOVE_INLINE_POLICY`/`REPLACE_INLINE_POLICY` actionable, `REVOKE_OLDER_SESSIONS` honestly unrevertable, `UPDATE_TRUST_POLICY`/`DELETE_SESSION_POLICY_SCOPE` nothing to revert); the log event's exact shape; an actionable revert restoring engine state for real; a non-actionable one calling the adapter not at all |
| `tests/unit/test_mutation.py` | 3 | `execution/mutation.py`'s SI-2 guard (mutation target not materialized in this run); F4's `MutationNotConfirmedError` firing only when `record_receipt` is true, against a stub adapter that always returns an unconfirmed receipt (the real fake adapter never does) |
| `tests/integration/test_stale_authority.py` | 11 | M13 acceptance criteria 1/3/5, through the real `execution/orchestrator.py`: `short-defer.yaml`/`long-defer.yaml` classify `STALE_AUTHORITY_LIVE_CREDENTIAL` for the mutated capability and `INDETERMINATE` (the ambiguous "not propagated" case) for the untouched one, from the *same* run; `post-expiry.yaml` classifies `CREDENTIAL_EXPIRED` with no mutation involved; `findings.json`'s `STALE_AUTHORITY` finding states the documented-bearer-token-behavior note in the same paragraph as the result; `CURRENT_AUTHORITY`/`SESSION_SCOPE_CACHED` driven directly against `execution/deferred.py` and a real `FakeProviderAdapter`, without a full scenario; `EXPIRED_CREDENTIAL_HONORED`'s pipeline wiring proven by corrupting one real observation the way only a genuine provider defect could |
| `tests/integration/test_credential_pinning.py` | 3 | M13 acceptance criterion 2: the deferred observation's `credential_id` equals the `after-delegation`-phase credential's, read from `observations.jsonl`/`credentials.jsonl`, never the code path; the paired observation's `credential_id` differs; exactly two credentials recorded for the deferred identity, in issuance order |
| `tests/integration/test_post_expiry.py` | 4 | M13 acceptance criterion 4: `post-expiry.yaml`'s deferred probe is denied for every capability; every measurement classifies `CREDENTIAL_EXPIRED`; the paired fresh credential is unaffected (still `ALLOWED`); no `STALE_AUTHORITY`/`EXPIRED_CREDENTIAL_ACCEPTED` finding is produced (expected lifetime behavior, not a finding) |
| `tests/unit/test_credential_store.py` | 3 | `execution/credential_store.py::resolve`'s two failure paths (unknown phase; a phase that ran but recorded no credential, e.g. a root) and the success path |
| `tests/unit/test_deferred.py` | 2 | `execution/deferred.py` against a target with no delegation edge (F3 requires a delegated identity, never the root); against a stand-in adapter with no `enable_authority_caching` hook, proving the module still runs correctly against a future real-time adapter without it (M17) |
| `tests/integration/test_silent_narrowing.py` | 10 | M14 acceptance criteria, through the real `execution/orchestrator.py`: the restored `two-step-pipeline.yaml` (honest worker, insufficient authority) reports `PARTIAL`/`reported_insufficient_authority=True` and no finding -- failing loudly is `EXPECTED_BEHAVIOR`; `two-step-pipeline-full-authority.yaml` (F7) reports `COMPLETE` with an independently verified marker; `nc-silent-success.yaml` end to end at `DETECTOR_OK`/`HIGH`; every finding's `caveats` name the worker synthetic (AC5); `TASK_EXECUTION` observations excluded from generic authority findings |
| `tests/integration/test_task_workers.py` | 10 | M14 acceptance criterion 1, driving `execution/task_runner.py` directly against a real one-hop graph: all four deterministic workers; F5's "reported distinctly" requirement -- `substituting`/`redelegating` each produce their own `FindingType`, never collapsed into `SILENT_NARROWING` alone, every finding its own `finding_id`; a permitted substitution (`must_not_substitute: false`) produces no finding; a same-capability `on_failure: retry` is never mistaken for a substitution |
| `tests/integration/test_side_effect_verification.py` | 8 | The milestone's own stated core case: `execution/side_effects.py::verify_output_marker` directly (absent/present/run-and-task-scoped/no-escape-hatch); `deterministic.always-complete`'s self-report is internally consistent (`steps_succeeded == steps_total`, no observations at all) yet independent verification still catches it; an honest worker's claim and the independent check agree |
| `tests/unit/test_deterministic_workers.py` | 5 | `execution/workers/deterministic.py` against a stub invoker: `on_failure: abort` stopping before the next step, an all-denied task reporting `FAILED`, a non-final step also denied under `substituting`/`redelegating`, `resolve_worker`'s unknown-id error |
| `tests/unit/test_report_language.py` | 32 | EXPERIMENT_PROTOCOL §7's lint: forbidden phrases caught and cleared after removal, a bare timing value without an interval indicator flagged (`window`/`n=`/a dash range all accepted indicators), a percentage without a `(x/y)`/`of y` denominator flagged, the limitations section's five required terms, the NOT_MEASURED sentence present iff required, `enforce`/`enforce_report` raising `ReportLanguageError` on a violation and passing once removed, `enforce_report`'s narrower forbidden-phrases-only bar for finding text (a bare timing value there does not raise) |
| `tests/unit/test_no_unsafe_template_filters.py` | 5 | S1/T-10: no `\|safe` (in any whitespace spelling) anywhere in the template directory; three planted spellings each caught by the same regex the real scan uses |
| `tests/unit/test_cli_report_command.py` | 9 | `chainbreak report`'s CLI-level argument handling: missing run_id, unknown `--format`, unknown run id, a real terminal render to stdout, each format written to a file with `-o`, a tampered bundle refused without `--allow-unsealed` and accepted with it |
| `tests/unit/test_report_figures.py` | 18 | Each of the seven figure builders' not-applicable and applicable branches driven against hand-built evidence objects (the worked-example graph's own injected divergence appears as an "excess" bar; a non-monotonic revocation transition is labeled; a populated vs. unpopulated stale window; unanimous vs. disagreeing trial repeatability; a cross-run comparison mapping) |
| `tests/unit/test_report_terminal.py` | 13 | `reporting/terminal.py` against hand-built `ReportData`: the fake-provider banner present/absent by provider, `git_dirty`/`bundle_root_verified` warnings rendering prominently and staying silent when clean, an empty findings list rendering "none", a finding's caveats line, a NOT_MEASURED category's dashes, the MEASUREMENTS section's n/interval/mechanism text present only when revocation or stale measurements exist |
| `tests/integration/test_report_generation.py` | 12 | M16 acceptance criteria, through a real orchestrated `delegation-drift/four-hop.yaml` bundle: all three formats render (criterion 1); the fake-provider stamp in the header and in every one of `1 + len(figures)` occurrences in the HTML output (criterion 4); all five limitations terms present in every format (criterion 5); the NOT_MEASURED sentence; a hand-built `ReportData` with a `<script>` in `security_interpretation` escaped in HTML, not present unescaped (criterion 3); the HTML report under 2 MB and under 3 s to generate |
| `tests/unit/test_compare.py` | 24 | M18 F1-F3: set-valued content matching across different run-specific ids (`STRUCTURALLY_IDENTICAL`) vs. self-comparison (`IDENTICAL`); content differences and missing-on-one-side findings reported `DIVERGENT` rather than raised; revocation window overlap/non-overlap/no-transition-on-both-sides/transition-observed-mismatch/polled-on-one-side-only; a cross-run timing match never reporting `IDENTICAL`; `HeterogeneousComparisonError` for differing compiled_hash/adapter_version/catalog_version and for differing `infrastructure_fingerprint`, `--allow-heterogeneous`/`--cross-operator` letting each through with a note and never upgrading a `DIVERGENT` verdict; `snapshot_from_bundle`'s missing-findings.json error; the `chainbreak compare` CLI's missing-args and unknown-run paths |
| `tests/integration/test_compare_negative_controls.py` | 2 | M18's own negative controls, through the real `execution/orchestrator.py`: the same fake scenario run twice with the same seed compares with zero divergence, every comparison `STRUCTURALLY_IDENTICAL`; the same revocation scenario run at two different seeds under `--fake-profile eventual` reports its timing comparison `DISTRIBUTIONALLY_CONSISTENT` (never `IDENTICAL`) while its structural (non-timing) findings still match exactly |
| `tests/unit/test_archive.py` | 7 | M18 F4/S1: a real tarball produced with the expected suffix, catalog version and schema count; an explicit `--output` path respected; no permanent scrubbed staging directory left behind; catalog version and same-version catalog-content mismatches refused; extraction into an isolated directory with every `ARTIFACT_NAMES` file, `catalog.yaml`, every schema, and a `REPRODUCE.md` naming the run id and the exact commands all present; an ARN seeded into the bundle absent from the archived copy even without an explicit `--public` flag |
| `tests/unit/test_migrate.py` | 10 | M18 F5, against a synthetic v1→v99 migration registered through the module's own public API (no real migration exists yet -- `BUNDLE_FORMAT_VERSION` has never changed): registration/double-registration-refused/registry listing; already-at-target-version and no-registered-path both refused; a migrated bundle lands in a new directory; the original bundle is byte-for-byte unchanged after migration (hashed before and after); the migrated bundle's content matches the original's; an explicit target directory respected; `copy_bundle_verbatim` refuses an existing target |

**Execution status:** `tests/aws/test_adapter_real.py` executed with `21 passed`, and
`tests/aws/test_cleanup_contract.py` executed with `2 passed`. The scrubbed
`tests/fixtures/provider_responses/` record and live wrong-account call-log gate are complete;
the remainder of the e2e layer (M17) has not started;
and the rest of the unit suite described in [TESTING.md](TESTING.md) that covers modules later
milestones will add (`scoring/`, `reporting/`). CI was green on GitHub Actions through M6 (see the
M0 entry under "Completed" for
the four real defects the first three runs found and the fixes that followed, the M1 entry for
its own clean first-try run, the M4/M5 entries for runs
[31211555428](https://github.com/KubixDesiney/chainbreak/actions/runs/31211555428) and
[31216636287](https://github.com/KubixDesiney/chainbreak/actions/runs/31216636287), and the M6
paragraph below for its own three-iteration path to green). **M7 was pushed at commit
`30e81eb` and was observed green on all ten jobs on the first try**
([run 31245421173](https://github.com/KubixDesiney/chainbreak/actions/runs/31245421173)) — unlike
M6, no fix iteration was needed. **M8's offline portion was pushed at commit `ed0fa3b` and
needed one fix iteration to go green.** The `security` job's `bandit -r src/` step failed on
`adapter.py`'s `assert result is not None` (B101: bandit flags any bare `assert` in `src/`,
since asserts are stripped under Python's `-O` optimization) — a real gap in local verification,
since `bandit` is not among this project's own documented verification commands and had never
been run against this code before the push. Fixed by replacing the assert with an explicit
`if result is None: raise AssertionError(...)`, matching the precedent `retry.py`'s own
"unreachable" branch already set earlier in the same milestone; commit `38bc329` was observed
green on all ten jobs
([run 31255480917](https://github.com/KubixDesiney/chainbreak/actions/runs/31255480917)).
`bandit -r src/ -q` is now added to this file's own pre-push habit for any future milestone
touching `src/`, even though it is not yet listed in any milestone's own verification commands.
**M9 was pushed at commit `707df1d` and needed one fix iteration to go green** — the same
one-iteration pattern M8 hit, and for the same underlying reason: a local verification gap.
`pytest -m "unit or integration"`, `ruff`, `mypy`, `lint-imports` and `bandit -r src/ -q` all
passed locally before the push (this file's own pre-push habit, set by M8's fix), and
`terraform fmt -check -recursive`/`terraform validate` passed for every module and environment
against a locally downloaded Terraform 1.9.8 binary — but `checkov` itself had never run
anywhere in this development environment (known issue 18, at the time unresolved), so its own
CI job ([run 31260482863](https://github.com/KubixDesiney/chainbreak/actions/runs/31260482863))
was the first time it ran against this code at all, and it failed with 22 findings across 7
resources. Two were genuine, cheap fixes applied for real: `aws_sqs_queue.queue` gained
`sqs_managed_sse_enabled = true` (CKV_AWS_27), and the objectstore S3 lifecycle configuration
gained a second, unscoped rule aborting incomplete multipart uploads (CKV_AWS_300 — checkov's
own check only credits an `abort_incomplete_multipart_upload` block on a rule with no scoping
`filter`, so folding it into the existing prefix-scoped rule does not satisfy it; the
observability module's trail bucket got the equivalent fix, since its lifecycle rule already
carries an empty-prefix filter). The remaining 20 findings are checkov's own production-hardening
defaults (customer-managed KMS keys, cross-region replication, VPC-bound Lambda, a Lambda DLQ,
code-signing, 1-year CloudWatch log retention, S3 access logging, S3/DynamoDB versioning and
point-in-time recovery) that actively contradict this benchmark's actual design — every flagged
resource exists for one run (minutes) and is destroyed with the rest of the stack, cost is
budgeted under $0.10/suite (AWS_PROVIDER_SPEC section 9), and no secret ever reaches Terraform
state (SI-1) — so each was documented with a `#checkov:skip=CKV_XXX:<specific reason>` comment
naming exactly which of those three facts makes the check inapplicable, discovered the hard way
that checkov only honors a skip comment placed *inside* the resource block it names, not one
preceding it (an initial attempt placing the comments before each resource silently did nothing).
`checkov` was then installed locally for the first time (resolving part of known issue 18) and
run directly (`Checkov(argv=[...]).run()` — its console-script entry point does not work under
this environment's Git Bash) to confirm the fix before repushing: 138 passed, 0 failed, 30
skipped, exit 0. Commit `baa1459` was observed green on all ten jobs on the first try
([run 31261194217](https://github.com/KubixDesiney/chainbreak/actions/runs/31261194217)).

**M6 needed three iterations to go green**, none of them hypothetical — each was a defect a
from-scratch review had a real chance of missing, caught by the exact mechanism designed to
catch it, the same pattern the M0 entry's four defects followed:
run [31240770166](https://github.com/KubixDesiney/chainbreak/actions/runs/31240770166) failed
`test` (both 3.12 and 3.13) on a Windows/Linux line-ending mismatch in the sealed golden
fixture and failed `security` on a synthetic secret that wasn't EXAMPLE-exempted (the M6
"Completed" entry's finding 3 above describes both in full); the fix for the second failure
then reproduced the literal EXAMPLE-shaped string in this file's own prose, outside `tests/`,
which run [31241489948](https://github.com/KubixDesiney/chainbreak/actions/runs/31241489948)
caught in turn — the exact trap the M0 entry already describes hitting once, now hit a second
time. Once `security`'s remaining failure turned out to be `git log -p --all` finding the
original non-EXAMPLE string permanently baked into an earlier commit's diff (run
[31241577278](https://github.com/KubixDesiney/chainbreak/actions/runs/31241577278)), the three
M6 commits were squashed into one clean commit on top of M5 and force-pushed — a history
rewrite done only after explicit operator sign-off, per this project's own operating rules for
destructive git operations — landing at commit `830b419`. That push was observed green on all
ten jobs on the first try
([run 31241854761](https://github.com/KubixDesiney/chainbreak/actions/runs/31241854761)).

Coverage: `core/` ~99%, `graph/` ~99%, `capabilities/` 100%, `scenarios/` ~98% (`policy_synthesis.py`
100%, its size-limit error path directly tested — S1; `compiler.py` 98%, its two new M12 functions
`_build_mutation_plans`/`_build_poll_plans` themselves fully covered by the five revocation
scenarios compiling — the two remaining gaps are pre-existing, unrelated to M12), `config/`
~99%, `cli/` ~95% (`infra.py` 100%, up from 69.4% — S1; `run.py` 88%, its new `--fake-profile`
validation and `eventual`-profile dispatch both covered — the remaining gaps are pre-existing
settings-fallback branches), `providers/base/` 100%, `providers/fake/` ~99.7%, `evidence/` ~94–100% per
module (`redaction.py`/`writer.py`/`manifest.py`/`export.py`/`verify.py` 100%, `reader.py`
~98%, `index.py` ~94%), `analysis/` 98% under `pytest -m "unit or integration"` (`authority.py`
100%, `divergence.py` 100%, `confidence.py` 100%, `drift.py` 100% — M11 — `detector.py` ~95%,
`rules.py` ~97%, `timing.py` ~98%, `pipeline.py` ~96% — up from ~93% at M7, the citation-chaining
fix and path-analysis wiring both fully covered by M11's own tests; the remaining gaps are
pre-existing M7-era revocation/execution-error paths that M12's execution wiring does not touch —
`analysis/timing.py` and `analysis/rules.py` themselves needed no changes at all this milestone,
only real evidence to consume; see the M7 entry above for the fuller original accounting),
`providers/aws/` ~97% offline-only (`retry.py`/`session.py`/`policy.py`/
`policy_synthesis.py`/`bindings.py`/`disambiguation.py`/`adapter.py` 100%, `probes.py` ~95%, `mutation.py`
~92%, `preflight.py` ~94%; `adapter.py` was ~85% and the module floor as of the M8 entry above —
S1 raised it to 100% by dispatching every `_build_call` match arm (only two of ten were ever
driven through `adapter.probe()` before), covering `delegate()`'s no-live-session guard, testing
the allowlist before-call hook's both branches directly against a stub client, and reaching
`_call_and_classify`'s three post-retry paths via a monkeypatched `call_with_retry` rather than
relying on moto's approximate IAM enforcement to reproduce a specific failure shape on demand;
`mutation.py`'s and `preflight.py`'s remaining gaps are still genuinely real-AWS-only, per the
M8 entry) (all exceed their TESTING.md bars, where one is stated — 95%, 95%, 90%, 90%,
**100%**, 95% respectively; `config/`, `cli/` and `providers/` have no stated bar in TESTING.md's
per-module table, so M5's own 90% acceptance criterion is the one actually gating `providers/`).
`execution/` ~99% (M10/M11/M12; `control.py`, `delegation.py`, `preconditions.py`, `_records.py`,
`chain.py`, `mutation.py`, `revert.py` all 100% — `chain.py`'s S1 depth-guard branch covered by
`test_chain.py`; `matrix.py`'s one genuinely unreachable branch — G-2's own reachability
guarantee: an unmeasured identity is a compile-time `ScenarioSemanticError`, never a compiled
matrix — is marked `# pragma: no cover` rather than counted against coverage; `orchestrator.py`
and `polling.py` are each 99%, a couple of branch-coverage partials on the MUTATE/POLL/SNAPSHOT
paths M12 added, not a functional gap — every line those branches guard is exercised by
`tests/integration/test_revocation.py`'s and `test_polling.py`'s combined 20 tests, just not
every arc of every branch from a single test), comfortably over M10's own 90% acceptance
criterion.
`core/safety.py` is exactly 100%, its own acceptance criterion. The SI-1 redaction
`--cov-fail-under=100` gate is now active and passing — the first CI push to activate it will be
the first time this gate has run for real, the same way M4's push was the first real run of the
SI-5 SafetyGate gate. Coverage is otherwise not enforced project-wide.

---

## Measured experiments

**No valid or publishable M17 measurement exists.** "Run against fake" below means the execution
engine actually runs that family end to end against the deterministic fake provider — an
apparatus check, not an AWS measurement. Invalid/incomplete AWS attempts are retained in the lab
log as superseded/excluded apparatus evidence; none is a result.

| Family | Implemented | Run against fake | Run against AWS |
|---|---|---|---|
| Scope attenuation | yes (M10) | yes | 0 valid/publishable M17 blocks |
| Delegation drift | yes (M11) | yes | 0 valid/publishable M17 blocks |
| Revocation propagation | yes (M12) | yes | 0 valid/publishable M17 blocks |
| Stale authority | yes (M13) | yes | 0 valid/publishable M17 blocks |
| Silent narrowing | yes (M14) | yes | 0 valid/publishable M17 blocks |

Negative controls authored: 6 of 6. Executed against fake: 6 of 6 (`nc-scope-expansion`,
`nc-surviving-authority`, `nc-non-monotone-chain` via `tests/fixtures/mini_orchestrator.py`'s
real-fake-adapter-calls-without-the-real-orchestrator stand-in; `nc-no-revocation`,
`nc-stale-credential-reuse` and `nc-silent-success` via the real `execution/orchestrator.py`
directly — M12 moved `nc-no-revocation` there first, M13 added `nc-stale-credential-reuse`, M14
added `nc-silent-success`).
Executed in a valid/publishable AWS block: 0 of 6.

[docs/research/lab-log.md](docs/research/lab-log.md) contains the historical invalid/incomplete
M17 apparatus entries and their exclusions; no valid block has been published.

---

## Current known issues

1. **No valid/publishable M17 block exists.** The historical attempts in
   `docs/research/lab-log.md` are invalid/incomplete apparatus evidence and remain excluded from
   measurement claims. A valid five-family/six-control M17 block is still pending.
2. **The real-AWS portion of M18 is pending.** Offline compare/archive/migration and dependency
   hardening are complete; real-AWS comparison and archive/migration exercise must follow a valid
   M17 block.
3. **M19 has not started.** The results write-up, release artifacts, tag, and publication remain
   gated on M17 and M18.

The following ledger is historical milestone context, not the active issue list. Resolved entries
are retained only where they explain a past apparatus repair; they are not current blockers.

Resolved and retired from the active list: the AWS `run` path is implemented; preflight order is
fail-closed with only `GetCallerIdentity` before an account mismatch; cleanup enumerates the IAM
blind spot; bundle provenance records region, commit, and dirty state; AWS sessions refresh and
close with secret state scrubbed; stale-window population is wired; and P8
`CONFIGURATION_ERROR` findings are wired through the preflight/analysis path. CI still does not
run TFLint or a documentation-link job.

## Historical known-issue ledger

1. **Resolved by M18 offline hardening.** `requirements.lock` is committed and the hash-locked
   install path is exercised by the CI security job.
2. ~~`BindingRegistry` and `PreconditionRegistry` are empty at runtime, outside tests.~~
   **Half-resolved by M5, for the fake provider.** `providers/fake/bindings.py` and
   `providers/fake/probes.py` register real, production bindings and precondition verifiers
   for all 10 catalog capabilities into `FakeProviderAdapter.bindings`/`.preconditions` at
   construction time — not a test fixture, the actual adapter callers use. The AWS half is now
   supplied by the production adapter factory and passed dedicated-account acceptance.
3. ~~G-4's provider-binding half is not enforced.~~ **Resolved by M3.** `scenarios/compiler.py`
   calls `resolve_bindings` (M2) against the graph `graph/builder.py` (M1) already built,
   which is what full G-4 enforcement actually needed — a component able to import both
   `graph/` and `capabilities/`, which neither of those packages may do to each other
   (ARCH-1). All of G-1 through G-5 are now enforced for any scenario compiled against a
   populated registry (known issue 2 above is what "populated" depends on).
4. ~~`OperationAllowlist` is not wired to anything yet.~~ **Resolved by M5.**
   `providers/fake/adapter.py`'s `probe()` wraps every call in `OperationAllowlist`, recording
   the binding's declared action(s) — the first real (non-test) caller since M2 built the
   mechanism. The AWS adapter's botocore `before-call` hook (M8) is now the other production
   caller; the fake's own call pattern always records exactly its own
   binding's actions, so today's wiring cannot itself observe a *cross-capability* mismatch
   (a caller passing a binding for one capability alongside a different declared
   `capability_id`) — worth a defensive assertion if that ever turns out to matter in
   practice, not added now since it is out of M5's scope.
5. ~~`chainbreak scenario validate` (the CLI) does not exist yet.~~ **Resolved by M4.**
   `cli/scenario.py`'s `validate` command wraps `scenarios.loader.validate_scenario` directly.
   Scenario validation now resolves against the same synthetic non-network registry used by the
   runtime compilation path, so the shipped scenarios validate offline without Terraform or AWS.
6. ~~No `.tf` files exist. Only contracts. `chainbreak infra *` will not work until M9.~~
    **Resolved by M9 and dedicated-account acceptance.** All five modules and both environments are implemented and
   `terraform fmt -check -recursive`/`terraform validate` pass against a Terraform 1.9.8 binary
   downloaded for this milestone specifically (not committed — it lives outside the repo, in the
   local temp directory the CI runner would install its own copy into instead), using a
   filesystem-mirrored AWS provider plugin to work around this sandbox's slow direct-registry
   throughput. `chainbreak infra plan/apply/destroy/status/verify-clean` are all implemented and
   unit-tested (`status`/`verify-clean` for real against `mock_aws()`; `plan`/`apply`/`destroy`
   only for argument handling in the offline suite). Dedicated-account acceptance covered the
   real apply/destroy path; Checkov and TFLint passed in that acceptance environment.
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
10. ~~`chainbreak run` still exits 2 (M4's stub); `execution/orchestrator.py` does not
    exist.~~ **Resolved by M10.** M5's own verification command (`chainbreak run
    scenarios/scope-attenuation/basic.yaml --provider fake --seed 1729`) named a command that
    was not implementable until M10, per `docs/implementation/MILESTONES.md`'s dependency
    graph and M10's own file list (`execution/orchestrator.py`, `execution/matrix.py`,
    `execution/delegation.py`) — see the M5 entry under "Completed" for how acceptance
    criteria 3 and 4 were verified instead, at the provider layer that existed at the time.
`execution/orchestrator.py` now exists and `chainbreak run` drives the full phase loop
against the fake provider for all five benchmark families (M10–M14); `--provider aws` is
implemented through the validated Terraform-output factory. M17 has produced no valid result.
11. **`Manifest.block_id` is always `None` today.** Added at M6 for schema symmetry with
    `ExperimentRun` and because `schemas/run-index.sql`'s `runs.block_id` column already exists,
    but nothing populates it until the orchestrator (M10+) and control C-7's block randomization
    (M17) exist to set it. Harmless: every M6 code path treats it as optional.
12. **The SQLite index path (`<runs_root>/index.db`) is a hardcoded CLI default, not a
    `Settings` field.** `cli/runs.py` accepts `--runs-root` per-invocation but there is no
    `chainbreak.toml`/env-var layer for it yet, unlike every other path `config/settings.py`
    resolves. Deliberately out of M6's scope (the milestone's file list is `evidence/` plus
    tests, not `config/`); worth folding into `Settings` if a later milestone's CLI surface
    needs it configured once rather than passed on every invocation.
13. ~~`analysis/pipeline.py` does not automatically extract `STALE_AUTHORITY`,
    `EXPIRED_CREDENTIAL_ACCEPTED`, `SILENT_NARROWING` or `CONFIGURATION_ERROR` findings from a
    bundle.~~ **`STALE_AUTHORITY`/`EXPIRED_CREDENTIAL_ACCEPTED` resolved by M13; `SILENT_NARROWING`
    (plus the two new `CAPABILITY_SUBSTITUTED`/`REDELEGATION_ATTEMPTED` types) resolved by M14.**
    `analysis/stale.py::stale_authority_measurements` extracts `DEFERRED_EXECUTION`/
    `PAIRED_FRESH_CREDENTIAL` observation pairs from any bundle and `analyze_bundle` now calls
    `rule_stale_authority`/`rule_expired_credential_accepted` on the result automatically, the
    same way `_revocation_findings` already did for the timing family since M12;
    `analysis/task_contract.py::extract_task_outcomes` extracts `TASK_OUTCOME_RECORDED` events the
    same way, and `task_contract_findings` calls all three task-contract rules automatically.
`CONFIGURATION_ERROR` wiring is resolved: preflight P8 classifies missing-marker infrastructure
as configuration failure, and the analysis path preserves that classification.
14. **Resolved by the dedicated-account acceptance.** The AWS adapter's live P1–P11, IAM
    semantics, wrong-account call-log, Terraform apply/destroy, service enumeration, and exact
    cleanup paths were exercised. This does not constitute a valid M17 five-family measurement.
15. **`AwsProviderAdapter.register_identity` cannot satisfy the shared `ProviderContractSuite`
    unmodified.** AWS's identities are fixed by Terraform provisioning (`bootstrap`, `principal`,
    `agent-a`..`agent-f`); the suite's own fake-oriented tests invent ad hoc names
    (`"agent-denied"`, `"agent-empty"`) no real account has a role for. `test_adapter_real.py`
    overrides the two affected tests to exercise equivalent behavior against real identities
    instead — a permanent, documented adaptation, not a temporary workaround to later remove.
16. **`tests/fixtures/provider_responses/` contains documented response-shape fixtures, not
    live account captures.** The fixtures are explicitly provenance-labeled and contain no
    account identifiers, ARNs, hostnames, credentials, or request IDs; live IAM semantics are
    validated separately by the real adapter suite.
17. **Resolved by the current AWS adapter.** The bootstrap session refreshes before expiry and
    `AwsProviderAdapter.close()` clears the cached session/credential state; the acceptance suite
    covers both behaviors.
18. ~~`checkov`/`tflint` (M9 acceptance criterion 2) have not run anywhere in this development
    environment.~~ **`checkov` half-resolved.** A first `pip install checkov` attempt had
    stalled on this network's own throughput (the same constraint that required downloading the
    Terraform provider plugin directly rather than through `terraform init`'s normal registry
    flow — see known issue 6's resolution above); a second attempt completed, and `checkov`
    (3.3.9) now runs clean locally (138 passed, 0 failed, 30 documented skips) and in CI
    ([run 31261194217](https://github.com/KubixDesiney/chainbreak/actions/runs/31261194217), one
    fix iteration after the first M9 push — see the "Tests" section for the full story).
    TFLint passed in the dedicated-account M9 acceptance environment; CI's current `terraform`
    job runs Checkov but not TFLint. The historical pre-acceptance note is retired.
19. **Resolved by M9 acceptance.** Terraform apply/destroy, repeated no-op operations, and
    service-specific exact cleanup were exercised in the dedicated account; no LocalStack claim
    is made.
20. ~~`test_import_boundaries.py`'s planted-violation teardown called `planted.unlink()`
    unconditionally.~~ **Resolved by S1 (2026-08-09).** On a filesystem where the removal is
    denied, the bare `unlink()` raised from the `finally` block, failing the test for the wrong
    reason (its own detection assertion had already passed) and leaving the planted file behind
    under `src/chainbreak/core/` or `src/chainbreak/graph/` — which the *next* run's
    `_iter_source_files()` scan would then pick up silently and misreport as a genuine ARCH-1
    violation, with nothing pointing at stale test debris as the actual cause. Fixed with a
    `_safe_unlink` helper that warns instead of raising on `OSError`, plus a
    `_warn_on_leftover_planted_violations` check run at module-collection time that loudly names
    any surviving planted file before the ordinary boundary checks run. Verified by monkeypatching
    `os.unlink` to raise `PermissionError` and asserting both the original detection assertion and
    the leftover-file warning still fire (`test_denied_unlink_warns_instead_of_failing_and_leftover_is_reported`).
21. **Three of the six negative-control scenarios cannot be triggered by a real
    `chainbreak run --provider fake` invocation.** `nc-scope-expansion.yaml`,
    `nc-non-monotone-chain.yaml` and `nc-surviving-authority.yaml` each declare their injected
    defect as an out-of-band extra grant on the target's role (an infrastructure-level policy,
    per each scenario's own `negative_control.rationale`) — the only place that currently
    simulates this is `tests/integration/test_negative_controls.py`'s use of
    `tests/fixtures/mini_orchestrator.py`, which calls a test-only
    `adapter.engine.apply_allow(identity, capability)` hook directly, bypassing
    `execution/orchestrator.py` entirely. A genuine end-to-end run of any of the three (verified
    directly while building M15 — see the M15 entry above) produces only `EXPECTED_BEHAVIOR`
    findings, so `chainbreak analyze` correctly reports `DETECTOR_FAILED` for each — S2 doing its
    job, not a scoring defect, but it means these three negative controls are currently only
    exercised through a test-only shortcut, never through the real orchestrator, against the fake
    provider. `nc-no-revocation`, `nc-stale-credential-reuse` and `nc-silent-success` do not have
    this problem — their defects (an unrelated identity being polled, natural WAIT/DEFERRED_EXECUTION
    timing, and the `always-complete` deterministic worker, respectively) are all things the real
    execution path produces on its own. Fix is either extending the fake provider with a
    scenario-declared "extra grant"/infrastructure-profile injection mechanism, or explicitly
    documenting these three as AWS/M17-only; a follow-up task was spawned for this rather than
    fixed inline, since it is a different, larger scope than M15's own file list.
22. **Resolved by the current analysis wiring.** `analysis/stale.py` receives the mutation send
    instant and populates `StaleAuthorityMeasurement.stale_window_seconds`; the Authority
    Freshness evaluator consumes it rather than approximating from `deferral_seconds`.
23. **Resolved by the current run path.** `cli/run.py` records the environment region in
    `Manifest.provenance`, so timing reports no longer use `REGION_NOT_CAPTURED` for a run that
    provides the value.
24. **Resolved by the current run path.** `cli/run.py` records `git_commit` and `git_dirty`; the
    reporting layer renders those provenance fields as designed.

---

## Technical debt

Recorded now so it is deliberate rather than discovered later.

- **`AuthoritySet` is a Pydantic model wrapping a `frozenset`.** Slightly heavier than a bare
  frozenset. Kept deliberately: canonical ordering is what makes evidence diffable and
  hashable. Do not "optimize" it.
- ~~`ProbeCellResult.resolved` returns `self.trials[0]` for mixed denial attributions.~~
  **Checked at M7, not actually fragile.** Re-reading the property while building
  `analysis/authority.py::resolve_cell` (which sits directly on top of it) found it already
  branches on `len(distinct)`: a unanimous denial returns that shared value, and a *mixed-kind*
  denial already returns `DENIED_UNATTRIBUTED`, never a `trials[0]` guess — locked in by
  `test_mixed_denials_become_unattributed_no_exclusion`. The original note describing this as
  fragile predated that reading; nothing needed to change.
- **JSON Schemas are generated but not yet diffed in CI.** The `schemas` job now runs
  `python -m chainbreak.scenarios.export_schema schemas && git diff --exit-code schemas/` in
  every CI run; whether it correctly blocks a real drifted PR is unverified until GitHub
  Actions runs it against a real drift, which has not happened yet.
- ~~`reporting/figures.py` uses hand-built inline SVG, not Plotly, despite M16's own spec text
  naming Plotly.~~ **Reclassified: this was a stale spec, not open debt.** The mismatch was in
  M16-reporting.md's text, not the code — `include_plotlyjs="inline"` alone exceeds M16's own
  2 MB report budget, a CDN violates the self-contained requirement, and SVG is readable
  without JavaScript where a Plotly `<div>` is not, exactly as the module's own docstring
  argued. M16-reporting.md and ARCHITECTURE.md §3.16 now describe the SVG implementation
  directly, and the rationale is recorded in
  [docs/DECISIONS.md](docs/DECISIONS.md#smaller-decisions) under "Smaller decisions" so a
  reviewer finds it without reading source. The unused
  `plotly>=5.22` dependency and its mypy override have been removed from `pyproject.toml`
  (THREAT_MODEL T-14: minimal dependency surface, and an unused declared dependency is pure
  attack surface).

---

## External resources eventually required

| Resource | Needed from | Notes |
|---|---|---|
| A **dedicated** AWS account, no production workloads | M17/M18 real-AWS exercise | M8/M9 dedicated-account acceptance is complete; the allowlist admits no wildcard |
| An IAM identity able to assume the bootstrap and principal roles | M17/M18 real-AWS exercise | M8/M9 acceptance passed with SSO/OIDC-style fixed-role setup; never use a static key |
| Terraform 1.7+ | M17/M18 real-AWS exercise | A 1.9.8 binary and mirrored provider plugin exist locally (not committed); `fmt`/`validate` and M9 apply/destroy acceptance passed |
| `tflint` | M9 | Dedicated-account acceptance run passed; retain the tool in the verification environment for repeatability |
| AWS spend | M8 | Under $1 for the full suite; Budgets alarm at $5 |
| A GitHub environment `aws-benchmark` with required reviewers | M17 | For the manually-dispatched experiment workflow |
| At least three separate time windows | M17 | Control C-7: timing trials must be distributed across blocks |

M0–M7 were entirely offline. M8's adapter code and M9's Terraform sandbox were verified offline
and then passed dedicated-account acceptance. M10–M16 are complete offline; only the future
real-AWS M17 block and the real-AWS half of M18 still require the account and identity above.

---

## Current next action

**M0–M16 are complete, including dedicated-account acceptance for M8 and M9. M17 has only
invalid/incomplete apparatus attempts, with zero valid/publishable blocks and no measurement.
M18's offline portion is complete; its real-AWS comparison/archive/migration exercise remains
pending. M19 has not started.**

The next action is a future, explicitly approved M17 run that satisfies the complete family,
negative-control, block, timing, and cleanup gates. No result may be inferred from the historical
invalid attempts.

Verification commands for the full offline surface (M0 through M16 plus the current offline
M18 tooling), run for real this session. The pre-pass baseline was 1,772 passed; the current
worktree, including pre-existing source/test changes, produced 1,808 passed:

```bash
pip install -e ".[dev,aws,report,analysis]"
ruff check . && ruff format --check .              # All checks passed! / 315 files already formatted
mypy                                                # Success: no issues found in 122 source files
lint-imports                                        # 6 contracts kept
bandit -r src/ -q                                   # clean
pytest -m "unit or integration" --cov=chainbreak --cov-report=term-missing -q
                                                      # 1,808 passed, 9 skipped, 28 deselected
pytest -m unit tests/unit/test_redaction.py \
  --cov=chainbreak.evidence.redaction --cov-fail-under=100 -q   # 100%
pytest --cov=chainbreak.reporting --cov-report=term-missing -q \
  tests/unit/test_report_* tests/unit/test_no_unsafe_template_filters.py \
  tests/unit/test_cli_report_command.py tests/integration/test_report_generation.py
     # 99% -- every reporting/ module 100% except figures.py's one pragma:no-cover branch
chainbreak --help                                   # ~360ms, under the 500ms budget
chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake --seed 1729
chainbreak analyze <run-id>
chainbreak report <run-id> --format terminal        # renders; stamped FAKE-PROVIDER APPARATUS CHECK
 chainbreak report <run-id> --format html -o /tmp/r.html   # 20K, well under 2MB
 grep -rn '|safe' src/chainbreak/reporting/templates/ && echo FAIL || echo "no unsafe filters"
```

Exact current gate summaries:

```text
408 passed, 9 skipped in 1.70s
16 passed in 0.93s
52 passed in 1.72s
22 skipped, 1823 deselected in 2.10s
Terraform wildcard-resource check: PASS (28 Terraform files checked)
Passed checks: 138, Failed checks: 0, Skipped checks: 30
```

`pip-audit --skip-editable` is the only non-green gate in this environment: it reports 15
known vulnerabilities in installed `aiohttp 3.13.5` and `ecdsa 0.19.2`; no dependency or source
behavior was changed in this documentation pass.

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
