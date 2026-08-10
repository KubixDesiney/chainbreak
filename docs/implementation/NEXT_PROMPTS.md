# Ready-to-run Claude Code prompts — unblocked work only

Every prompt here runs **entirely offline** against the deterministic fake provider. None
needs the AWS account, credentials, spend, or your presence. They can proceed in parallel
with the M8/M9 real-account work.

**State these prompts assume** (verified 2026-08-09): M0–M7 complete, M8 and M9 code-complete
but awaiting a real account, 1,242 tests passing, 96.8% coverage, `ruff`/`mypy` clean,
6/6 import-linter contracts kept, 12 scenarios validating.

**Run them in the listed order.** S1 is independent; S2 through S8 form a dependency chain.
One session per prompt — do not merge two.

Superseded: [CLAUDE_CODE_HANDOFF.md](../CLAUDE_CODE_HANDOFF.md) § M10–M16 were written before
implementation started and describe a repository that no longer exists. Use this file instead.
The handoff's Part 1–4 (invariants, conventions, how the pieces fit) is still current and every
prompt below references it.

---

## S1 — Housekeeping, no dependencies

Do this first. It is short, and it removes two known defects that will otherwise be rediscovered
during a later milestone.

```
Housekeeping session for CHAINBREAK. Two known defects and two coverage gaps. No new features.

Read docs/CLAUDE_CODE_HANDOFF.md Part 2 (invariants) before touching anything. Run
`pytest -m "unit or integration" -q` first and record the baseline count.

1. tests/unit/test_import_boundaries.py plants a violating module under src/ and deletes it in
   teardown. On a filesystem where unlink is denied the delete raises, the test fails for the
   wrong reason, and a stray module is left in src/ that breaks every subsequent run. Make the
   teardown fault-tolerant: the planted file must be removed on a best-effort basis, a failed
   removal must not fail the test that already made its assertion, and a leftover file must be
   detected and reported loudly at session start rather than silently importing. Verify by
   simulating an unlink failure (monkeypatch os.unlink to raise PermissionError) and asserting
   the detection assertion still passes and the failure is surfaced as a warning, not an error.

2. Raise coverage on src/chainbreak/cli/infra.py, currently 69.4% — the lowest module in the
   tree. Do not add tests that assert implementation details to inflate the number. Cover the
   real branches: missing Terraform binary, missing tfvars, a plan that returns a non-zero exit,
   a destroy that partially fails, and verify-clean finding leftover resources. Mock the
   subprocess boundary, not the module's own logic.

3. Raise coverage on src/chainbreak/scenarios/policy_synthesis.py (85.7%). The uncovered
   branches are most likely the size-limit error path and the empty-capability-set case — check
   before assuming.

4. providers/aws/adapter.py is at 85.5%. Some of its paths genuinely cannot be exercised
   without an account. Cover what can be covered with moto or a stubbed client, and for anything
   that truly requires AWS, add an explicit comment naming which aws-marked test covers it.
   Do NOT mock the AWS API so thoroughly that the test proves nothing — if a path can only be
   validated against real IAM, say so rather than faking a pass.

Do not change .gitattributes or .gitignore; both were fixed already.

Preserve every invariant in handoff Part 2. Run the verification commands, paste real output,
and confirm the test count went up and no existing test was weakened. Update PROJECT_STATUS.md
under "Known issues" and "Technical debt". Stop only when ruff, mypy, and the full suite are
green.
```

---

## S2 — M10 scope attenuation

The first benchmark family. Everything M11–M14 adds is a variation on the execution machinery
this builds, so getting the phase loop right here matters more than the family itself.

```
Implement milestone M10 for CHAINBREAK — the scope attenuation benchmark.

Inspect the repository first. Read docs/CLAUDE_CODE_HANDOFF.md (all of Parts 1-4),
docs/implementation/milestones/M10-scope-attenuation.md, EXPERIMENT_PROTOCOL.md section 1, and
RESEARCH_METHODOLOGY.md section 4 (the nine experimental controls). Run
`pytest -m "unit or integration" -q` and confirm the existing suite passes.

M0-M7 are complete. providers/fake/ is a real authorization engine with deny-over-allow
precedence, session-policy intersection, credential lifetimes and an injectable consistency
model — use it, do not rebuild it. analysis/ already produces findings from evidence. Your job
is the execution layer that sits between them.

Implement execution/: orchestrator.py, matrix.py, delegation.py, preconditions.py, control.py.

Design the phase loop against the FULL PhaseKind enum from the start — PROBE, MUTATE, POLL,
WAIT, DEFERRED_EXECUTION, TASK, SNAPSHOT — even though only PROBE is exercised here. Building
orchestration that only handles this family means rewriting it in M12, and the rewrite will be
worse because it will be retrofitted around assumptions PROBE alone let you make.

Four controls are requirements, not nice-to-haves:

- C-6: probe order shuffled with a RECORDED seed. Without it, whichever capability is probed
  last systematically carries more credential age and more accumulated throttling pressure than
  the first, which is a confound that looks exactly like a real finding.
- C-1: identity.whoami probed in every matrix. Its failure raises ControlCapabilityFailedError
  and DISCARDS the matrix. It must never be recorded as a wave of denials — that is the failure
  mode this control exists to prevent.
- C-2: preconditions verified by the provisioning identity before every read matrix.
- Credential lifetime checked before each matrix; re-delegate if the remaining lifetime is under
  2x the estimated matrix duration, and record the re-delegation as an event.

Run both scope-attenuation negative controls. nc-surviving-authority is the one that matters:
it fails if divergence is computed only at node level, because a node's derived expectation can
coincide with its observed set while the EDGE's intent was violated. If your implementation
passes nc-scope-expansion but fails nc-surviving-authority, the edge-level check is missing.

Preserve every invariant in handoff Part 2, especially SI-7 (deadline checked at every phase
boundary) and the rule that write probes are confined to scratch/{run_id}/.

Run the verification commands from the milestone file and paste real output. Update
PROJECT_STATUS.md marking Family A implemented AND explicitly noting it has not been run against
AWS. Stop only when every acceptance criterion passes.
```

---

## S3 — M11 delegation drift

```
Implement milestone M11 for CHAINBREAK — the delegation drift benchmark.

Inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M11-delegation-drift.md, AUTHORIZATION_MODEL.md sections 4.4,
4.5 and 7, and EXPERIMENT_PROTOCOL.md section 2. Run the suite and confirm M10 is green.

Implement execution/chain.py and analysis/drift.py, and author the depth-2, depth-3, depth-5 and
depth-6 scenarios (four-hop already exists). Each depth is a SEPARATE file so compiled_hash
differs and results can never be accidentally pooled — do not parameterise one file.

Reproduce the AUTHORIZATION_MODEL section 7 worked example end to end as a test: divergence at
hop 3 classified ORIGINATED, hop 4 PROPAGATED, first divergence reported as hop 3, and hop 4's
finding citing hop 3 as its cause rather than raising an independent alarm.

Then construct the case a naive implementation gets wrong: hop 3 gains a capability and hop 4
drops it. Hop 4 must classify CORRECTED. A benchmark that reports that as a failure would flag
working defence-in-depth as a problem, which is worse than missing it.

Depth and total probe count are confounded — a depth-6 chain issues more calls, takes longer,
and has more opportunity for transient error than a depth-2 chain. Report divergence as a RATE
PER HOP, not per chain, and report the excluded-trial count per depth alongside it. If deeper
chains show both more divergence and more exclusions, the result is inconclusive and the
analysis must say so rather than reporting a depth effect. This is requirement F6 and it is the
difference between a real finding and an artifact.

Preserve every invariant in handoff Part 2. Run the verification commands, paste real output,
update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

---

## S4 — M12 revocation propagation

The first family whose output is a measurement rather than a comparison. Highest risk of
producing a confident wrong number.

```
Implement milestone M12 for CHAINBREAK — the revocation propagation benchmark.

Inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M12-revocation.md, AUTHORIZATION_MODEL.md section 5.1,
RESEARCH_METHODOLOGY.md sections 6 and 7, EXPERIMENT_PROTOCOL.md section 3, and ADR-011.
Run the suite and confirm M11 is green.

Implement execution/mutation.py, execution/polling.py, execution/revert.py, and the timing
extensions in analysis/timing.py. Author the three remaining revocation scenarios.

These requirements determine whether the numbers mean anything:

- t_M is the monotonic instant the mutation request was SENT. Confirmation latency is recorded
  separately. Using the send instant is the conservative choice — it can only make the measured
  window appear longer, never shorter.
- Warm baseline before mutation: poll to stable allow first, so the first post-mutation poll is
  not systematically slower than the rest because of a cold connection pool.
- The window is [t_last_allow - t_M, t_first_deny - t_M] with a midpoint and a half-width. There
  is NO scalar representation anywhere. Add a test that scans findings.json for a bare timing
  value and fails if it finds one.
- NON_MONOTONIC_TRANSITION preserved with the full timeline. Do not smooth it. Oscillation is
  the most interesting possible result in this family and hiding it would be a research failure
  dressed up as a usability improvement.
- NO_TRANSITION_OBSERVED_WITHIN_WINDOW with the window length — an honest negative, never a pass.
- The revert log is written BEFORE each mutation so a SIGKILL still leaves actionable recovery
  information. Test this by actually killing the orchestrator mid-phase.
- Between trials: revert, confirm, wait for stable allow before the next mutation.

Validate the interval maths against known answers, which is the only place this is possible:
set the fake provider's propagation_delay_ms to 0, 500, 2000 and 10000 in turn, and assert the
measured window contains the true value every time. If it does not, the maths is wrong and no
AWS run will reveal that.

Run nc-no-revocation — it must yield NO_TRANSITION_OBSERVED — and
revocation/trust-policy-null-condition, which must show NO transition at all. The second is
control C-5, the instrument check: a transition there means the apparatus is broken.

Preserve every invariant in handoff Part 2, especially SI-12 (mutations refuse bootstrap and
principal). Run the verification commands, paste real output, and update PROJECT_STATUS.md
stating plainly that no AWS revocation measurement exists yet. Stop only when every acceptance
criterion passes.
```

---

## S5 — M13 stale authority

```
Implement milestone M13 for CHAINBREAK — the stale authority benchmark.

Inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M13-stale-authority.md, AUTHORIZATION_MODEL.md section 5.2, and
EXPERIMENT_PROTOCOL.md section 4. Run the suite and confirm M12 is green.

Implement execution/deferred.py, execution/credential_store.py and analysis/stale.py, and author
the short-defer, long-defer and post-expiry scenarios.

The design element that makes this family interpretable at all is the PAIRED FRESH CREDENTIAL.
After the deferred probe using the pinned pre-mutation credential, immediately probe the same
capability with a freshly minted one. Without the pair, an ALLOWED at t_exec is ambiguous
between "the policy change never propagated" and "the old credential retained old authority" —
two completely different findings with different remediations. Implement this as F3 and test the
ambiguous case explicitly: configure the fake so the change has not propagated at all, and
assert the classification is "not propagated", NOT stale authority.

WAIT phases must not touch the credential. No keepalive, no refresh. The waiting is the
experiment.

Assert credential pinning from the EVIDENCE STREAM — the deferred observation's credential_id
must equal the one recorded for the earlier phase — not from the code path. A refactor must not
be able to silently break it while the test still passes.

STALE_AUTHORITY_LIVE_CREDENTIAL is documented bearer-token behaviour, not a defect. Reports must
say so in the same paragraph as the result. Only EXPIRED_CREDENTIAL_HONORED contradicts
documented behaviour, and that one is genuinely serious.

Use the fake's virtual clock so a 600-second deferral test runs instantly in CI while the
measurement code still goes through the clock abstraction. Confirm the SI-7 run deadline
accounts for deferral time — a 600s deferral inside a 900s run must not silently truncate.

Preserve every invariant in handoff Part 2. Run the verification commands, paste real output,
update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

---

## S6 — M14 silent narrowing

Can run in parallel with S4/S5 — it depends only on M11.

```
Implement milestone M14 for CHAINBREAK — the silent narrowing benchmark.

Inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M14-silent-narrowing.md, SCENARIO_SPECIFICATION.md section 6,
EXPERIMENT_PROTOCOL.md section 5, and ADR-007. Run the suite and confirm M11 is green.
This milestone depends on M11 only — it does not need M12 or M13.

Implement execution/workers/base.py and deterministic.py, execution/task_runner.py,
execution/side_effects.py and analysis/task_contract.py.

Define the TaskWorker Protocol purely in terms of a capability-invoker and a returned
TaskOutcome — nothing about how the worker decides what to do. A v0.4 LLM-backed worker must be
able to implement the same interface with no downstream change. Building the Protocol around the
deterministic implementation would foreclose the comparison that makes this family worth having.

Ship four deterministic workers: sequential (honest), always-complete (the negative-control
liar), substituting, and redelegating.

The core requirement is INDEPENDENT SIDE-EFFECT VERIFICATION. After the task runs, the bootstrap
identity checks whether the output marker the task claims to have written actually exists. The
worker's self-report is never trusted. A task reporting COMPLETE while its output marker is
absent is the purest form of silent failure, and this check catches it even when the worker's
step counts are internally consistent — which is exactly what a dishonest worker would ensure.

Workers invoke capabilities only through the executor's capability-invoker, never a raw provider
client, so SI-2 and SI-3 apply to task actions exactly as they do to probes. A redelegation
attempt is RECORDED and refused, not permitted.

Include a positive control: the same task with full authority must report COMPLETE and the
marker must exist.

Every report including this family must state that v0.1's worker is synthetic, so the family
measures the harness's contract-checking rather than agent behaviour.

Preserve every invariant in handoff Part 2. Run the verification commands, paste real output,
update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

---

## S7 — M15 per-category scoring

```
Implement milestone M15 for CHAINBREAK — per-category scoring.

Inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M15-scoring.md, SCORING_MODEL.md in full, and ADR-010.
Run the suite and confirm M13 and M14 are green.

Implement scoring/: categories.py, coverage.py, confidence.py, aggregate.py.

Six independent category evaluators. There is NO composite score, and no function anywhere may
reduce categories to a single number. Add a test asserting this by module introspection, and
include a grep in the verification step.

The rules easiest to get subtly wrong:

- A category not exercised by the scenario is NOT_MEASURED, never CONSISTENT. Rendered output
  must contain the literal sentence "NOT_MEASURED is not a pass." The most common way a
  benchmark misleads is by letting absence of measurement read as absence of problems.
- coverage < 0.7 forces PARTIAL regardless of what the measured cells showed, and the report
  leads with coverage rather than the result.
- Confidence aggregates with min, never a mean. Averaging would let a pile of easy measurements
  launder one shaky one. Test with five HIGH and one LOW; the result must be LOW.
- Revocation Responsiveness is DIVERGENT only when an ASSERTIVE scenario expectation was
  exceeded. There is no built-in propagation threshold, because CHAINBREAK does not know what a
  correct propagation time is and asserting one would be an unjustified normative claim.
- STALE_AUTHORITY_LIVE_CREDENTIAL yields CONSISTENT plus a mandatory note that it is documented
  behaviour. Only EXPIRED_CREDENTIAL_HONORED is DIVERGENT.
- Cross-run aggregation refuses differing compiled_hash, adapter_version or catalog_version.
  No mean without dispersion; no dispersion below n=5 — report the count instead.

No CLI flag may raise confidence or coverage. --allow-unsealed and --allow-heterogeneous exist
and only lower it. Assert this by introspecting the command surface.

Preserve every invariant in handoff Part 2. Run the verification commands, paste real output,
update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

---

## S8 — M16 reporting and visualisation

The last fully-unblocked milestone. After this, M17 needs the AWS account.

```
Implement milestone M16 for CHAINBREAK — reporting and visualisation.

Inspect the repository. Read docs/CLAUDE_CODE_HANDOFF.md,
docs/implementation/milestones/M16-reporting.md, EXPERIMENT_PROTOCOL.md section 7 (the language
rules), SCORING_MODEL.md section 4, and THREAT_MODEL.md T-10. Run the suite and confirm M15 is
green.

Implement reporting/: terminal.py, markdown.py, html.py, figures.py, language.py, templates/.

Two requirements do most of the work:

1. reporting/language.py implements the EXPERIMENT_PROTOCOL section 7 rules as a checkable lint
   over both templates and generated text. Required: n, interval, mechanism and region on every
   timing result; coverage and confidence on every category. Forbidden: "vulnerable", "broken",
   "insecure", "exploit", "proves", a timing value without an interval, a percentage without its
   denominator. Demonstrate the lint works by planting a violating sentence in a template and
   showing the test fail, then removing it.

2. Jinja2 autoescape on, with NO |safe anywhere — asserted by a test that greps the template
   directory. A third-party evidence bundle is a plausible XSS vector into a generated HTML
   report. Test with a bundle whose security_interpretation contains a script tag.

Every finding renders observation, expected_state, observed_state and security_interpretation
under separate headings, in that order. Never merge them into prose — the separation is what
keeps the project from overclaiming, and a report that blends them undoes ADR-006 at the last
step.

A provider: fake run must be stamped as non-measurement output in the header AND in every figure
caption, enforced in the rendering layer rather than left to operator discipline. A fake-provider
report must never be mistakable for a measurement.

Every report carries a limitations section naming: single account, single region, simple
policies, deterministic worker, small n.

All figures are generated from evidence. Never hand-written numbers.

Commit a sample HTML report from a fake run under examples/, with its header stating it is
fake-provider output.

Preserve every invariant in handoff Part 2. Run the verification commands, paste real output,
update PROJECT_STATUS.md. Stop only when every acceptance criterion passes.
```

---

## What is NOT in this file, and why

**M17** (full AWS experiment suite) needs the account, real spend, and at least three separate
hours of wall-clock time for block randomisation. It cannot be prompted ahead of time because
its output depends on what actually happens.

**M18** (reproducibility) formally depends on M17, since `chainbreak compare` needs real runs to
compare. Parts of it — `evidence/archive.py`, `evidence/migrate.py`, the Dockerfile, the hashed
lockfile — could be built earlier against fake-provider bundles. If S1–S8 finish before the AWS
work does, that is the sensible next thing to pull forward.

**M19** (release) requires M17's results and your publication decision.

**M8 and M9 completion** is a separate track that starts the moment
`scripts/bootstrap_aws_config.py` produces a working config.

---

## Session discipline

- One prompt per session. Merging two produces a session that runs out of context mid-milestone
  and leaves the repository in a half-implemented state that is worse than not starting.
- If Claude Code reports "acceptance criteria met" without pasted command output, ask for the
  output before believing it.
- If it proposes changing an invariant from handoff Part 2, stop and read the ADR it would
  supersede before agreeing.
- If it weakens or deletes an existing test to make something pass, reject the change. That is
  the single modification that makes the whole apparatus untrustworthy, and it is the one thing
  a green suite cannot warn you about.
