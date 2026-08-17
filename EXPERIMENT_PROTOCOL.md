# CHAINBREAK Experiment Protocol

Operational procedures. Where [RESEARCH_METHODOLOGY.md](RESEARCH_METHODOLOGY.md) says *why*,
this says *exactly what to do, in what order, and what invalidates the result*.

---

## 0. Two-stage experiment gates

The old single checklist was contradictory: it required infrastructure to be current and
clean at the same time. M17 uses two ordered gates. Stage B is never evaluated before a
successful apply, and a destroyed sandbox cannot pass it because `status` requires fresh
`outputs.json` and a matching live Terraform output.

### Stage A — pre-apply clean gate

Run every item before `chainbreak infra apply`. All are hard gates.

| # | Check | Command/evidence | Invalidates if failed |
|---|---|---|---|
| A1 | Working tree clean | `git status --porcelain` empty | Yes — provenance unusable |
| A2 | Tests green | `pytest -m "unit or integration" -q` | Yes |
| A3 | Config, account, and region resolve | `chainbreak validate --provider aws --stage pre-apply --check-budget --block-id <block-id>` | Yes |
| A4 | Exact prior namespace known and clean | `chainbreak infra namespace ...` followed by `chainbreak infra verify-clean ... --namespace <captured>`; if outputs exist, `infra status` must first prove they are current | Yes |
| A5 | Namespace lock held | GitHub environment concurrency plus `CHAINBREAK_ALLOW_CONCURRENT_RUNS=false` | Yes |
| A6 | Budget guard is configured | Pre-apply `--check-budget` validates a positive budget, notification, and enabled negative controls; no AWS call is needed because the old budget may have been destroyed | Yes |

The exact namespace is captured before apply and retained through destroy. A stale or missing
namespace/output capture is never silently substituted. A block whose Stage A was not recorded
is not a CHAINBREAK experiment.

### Stage B — post-apply live gate

Run only after Stage A and a successful apply. All are hard gates except the documented P11
timing-confidence downgrade.

| # | Check | Command/evidence | Invalidates if failed |
|---|---|---|---|
| B1 | Fresh outputs and current state | `chainbreak infra status aws-sandbox --provider aws --block-id <block-id> --capture-namespace <path>` | Yes |
| B2 | Current infrastructure fingerprint | `status` compares captured outputs with live `terraform output -json` | Yes |
| B3 | Live provider gate | `chainbreak validate --provider aws --stage live --check-budget --block-id <block-id>` | Yes |
| B4 | Markers and preconditions | P8 in the live validation report | Yes |
| B5 | P1–P11 and clock status | P1–P11 in the live validation report; P11 may downgrade timing confidence | Yes, except P11 warning |
| B6 | Block metadata and controls | every run uses `--provider aws --block-id <block-id>` and Terraform has `enable_negative_controls=true` | Yes |

`chainbreak validate --provider aws --stage live` refuses missing/stale outputs. It also performs
the fail-closed live budget/alarm check when `--check-budget` is supplied: the exact namespace
budget must be a positive monthly COST budget with an active subscribed alarm notification.

Record both gate results in the lab log (§8). An experiment whose two gates were not run in this
order is not a CHAINBREAK experiment.

---

## 1. Family A — Scope attenuation

**Question.** Does a delegated identity ever hold authority beyond what its hop granted?
**Hypotheses.** H1, H2. **Scenarios.** `scenarios/scope-attenuation/`.

**Design.** Principal → Agent A → Agent B. Agent A is provisioned with capability sets
{A, B, C} = {objectstore.*, keyvalue.read, function.invoke}. Hop 2 intends to delegate only
{objectstore.read}. Probe universe = all scenario capabilities, so expansion is detectable.

**Procedure**

1. Baseline probe of principal; abort on divergence (C-3).
2. Delegate hop 1 (`ROLE_CHAIN`), record credential metadata.
3. Probe matrix on Agent A, phase `after-delegation`, 3 trials, shuffled order (C-6).
4. Delegate hop 2 (`SESSION_POLICY_SCOPED`, `derive_from: intended_capabilities`).
5. Probe matrix on Agent B, same parameters.
6. Compute per-node and per-edge divergence.
7. Repeat 2–6 for each `delegation.mechanism` level.
8. Run the negative control `nc-scope-expansion` and require detection.

**Primary outcome.** `unexpected_gain(agent-b)`; `attenuation_correct(hop-2)`.
**Invalidating conditions.** `identity.whoami` failure; precondition failure; coverage < 1.0;
baseline divergence; negative control undetected.

**Expected result.** No expansion (session policies cannot grant). The value of this family
is that it establishes the apparatus is trustworthy before the harder families run.

---

## 2. Family B — Delegation drift

**Question.** Across a multi-hop chain, where does effective authority first diverge?
**Hypotheses.** H2, H8. **Scenarios.** `scenarios/delegation-drift/`.

**Design.** Chains of depth 2–6, each hop applying a session policy narrowing by one
capability. Depth is the independent variable; each depth is a separate scenario file so
`compiled_hash` differs and results are not accidentally pooled.

**Procedure**

1. Steps 1–5 of Family A, extended to depth *d*.
2. Probe every node at `after-delegation`. Serial across nodes; concurrent within a node's
   matrix (this family is not timing-sensitive).
3. Compute per-hop gain/loss, drift classification, first divergence, set- and
   cardinality-monotonicity.
4. Repeat for d ∈ {2,3,4,5,6}, n=3 trials each.
5. Run `nc-drift-nonmonotone` and require detection.

**Primary outcome.** `first_divergence_hop` distribution over depth; per-hop
`|unexpected_gain|`.

**Analysis note for RQ5.** Depth and total probe count are confounded — a depth-6 chain
issues more calls and takes longer, so more opportunity for transient error. Control:
report divergence *rate per hop*, not per chain, and report the excluded-trial count per
depth alongside. If deeper chains show more divergence *and* more exclusions, the result is
inconclusive and must be reported as such.

**Invalidating conditions.** As Family A, plus: any hop where the credential was
`LIFETIME_CAPPED` below the probe matrix's duration (the credential could expire mid-matrix,
turning a valid grant into a denial). The executor checks remaining credential lifetime
before each matrix and re-delegates if under 2× the estimated matrix duration, recording the
re-delegation as an event.

---

## 3. Family C — Revocation propagation

**Question.** How long does authority remain effective after a controlled change?
**Hypotheses.** H3, H4. **Scenarios.** `scenarios/revocation/`.
**This family is timing-sensitive: all probes are strictly serial.**

**Procedure**

1. Delegate to Agent B; probe to confirm the target capability is `ALLOWED` (if not, abort —
   you cannot measure the revocation of authority that was never present).
2. `SNAPSHOT` policy state (auto-inserted).
3. Poll the target capability at 500 ms until 3 consecutive `ALLOWED` — establishes a stable
   pre-mutation baseline and warms connection pools so the first post-mutation poll is not
   systematically slower.
4. Apply the mutation. Record `t_M` = monotonic send instant. Confirm via read-after-write;
   record confirmation latency separately.
5. Continue polling until 3 consecutive `DENIED_*`, credential expiry, or the 300 s window.
6. `SNAPSHOT` policy state.
7. Compute `t_last_allow`, `t_first_deny`, `transition_window`, `uncertainty_half_width`.
8. Revert the mutation; confirm reversion; wait for a stable `ALLOWED` before the next trial.
9. Repeat n=5, distributed across ≥3 blocks (C-7).
10. Repeat for each of the 5 revocation mechanisms.
11. `UPDATE_TRUST_POLICY` is the within-experiment null (C-5): a transition there means the
    apparatus is wrong and the entire block is discarded.

**Primary outcome.** `transition_window [low, high]` per mechanism; median and IQR across
trials.

**Reporting rule.** Always as an interval with n, mechanism, region, and endpoint.
Never as a bare number. Never as a verdict.

**Invalidating conditions.** Mutation receipt unconfirmed; polling gap > 2× the configured
interval (indicates the harness stalled); clock offset out of tolerance; `NON_MONOTONIC_TRANSITION`
(not invalidating, but reported separately and excluded from the interval aggregate);
a transition observed for `UPDATE_TRUST_POLICY`.

---

## 4. Family D — Stale authority

**Question.** Does deferred execution use current or historical authority?
**Hypotheses.** H5, H6. **Scenarios.** `scenarios/stale-authority/`.
**Timing-sensitive: serial.**

**Procedure**

1. Delegate to Agent C at `t₀`, requesting a lifetime that comfortably exceeds the deferral
   interval. Record `expires_at`.
2. Probe to confirm the capability is `ALLOWED` at `t₀`.
3. Apply the mutation at `t_M`; confirm.
4. `WAIT` for the deferral interval *without touching the credential* — no keepalive, no
   refresh. The waiting is the experiment.
5. At `t_exec`, probe using the **credential minted at `t₀`**
   (`credential_source: phase:after-delegation`).
6. Immediately probe with a **freshly minted** credential for the same identity. The pair is
   the measurement: it distinguishes "the policy change never propagated" from "the old
   credential retained old authority".
7. Classify per [AUTHORIZATION_MODEL §5.2](AUTHORIZATION_MODEL.md#52-stale-authority-classification).
8. Repeat for deferral intervals {30, 120, 600} s, n=5.
9. Separately: let a credential pass `expires_at` and probe, to test H6.

Step 6 is the design element that makes this family interpretable. Without the paired fresh
credential, a `ALLOWED` at `t_exec` is ambiguous between two very different explanations.

**Primary outcome.** Classification distribution; `stale_window_seconds`.

**Reporting rule.** `STALE_AUTHORITY_LIVE_CREDENTIAL` is documented bearer-token behavior.
The report states this in the same paragraph as the result, every time.

---

## 5. Family E — Silent narrowing

**Question.** When authority is insufficient, does the workload fail observably?
**Hypothesis.** H-behavioral (no provider prediction — this measures the workload).
**Scenarios.** `scenarios/silent-narrowing/`.

**Procedure**

1. Delegate to Agent B with `intended_capabilities` deliberately missing one capability the
   task requires.
2. Probe to establish observed authority (so the analysis knows what was actually available,
   independent of what the task reports).
3. Run the task with `deterministic.sequential`.
4. Capture `TaskOutcome`.
5. Verify output side effects independently: did the scratch marker the task claims to have
   written actually appear? (Checked by the bootstrap identity, not the task.)
6. Compare against `completion_contract`.
7. Repeat with the full capability set as the positive control — the task must report
   `COMPLETE` and the marker must exist.
8. Run `nc-silent-success` and require `SILENT_NARROWING` detection.

**Primary outcome.** `status` vs. `steps_succeeded`; `reported_insufficient_authority`;
independent side-effect verification.

Step 5 matters more than it looks: a task that reports `COMPLETE` while its output marker is
absent is the purest possible instance of silent failure, and it is verified by the
benchmark rather than trusted from the worker's self-report.

**Scope statement, mandatory in the report.** v0.1's worker is deterministic. This family
measures the harness's contract-checking, not real agent behavior. It becomes a measurement
of agent behavior when v0.4 registers an LLM-backed worker.

---

## 6. Negative-control protocol

Negative controls run **in the same block, on the same infrastructure, with the same
adapter** as the positive scenarios they validate. A control run days later against
different infrastructure proves less.

For each: apply, run, assert the declared `expect_finding` appeared with at least the
declared confidence. If it did not, emit `DETECTOR_FAILURE`, mark every positive result in
the block as **unvalidated**, and stop. Do not publish a suite containing a
`DETECTOR_FAILURE`.

Run the full negative-control set: after any change to a probe implementation, a capability
binding, the analysis layer, or the adapter version; before any published experiment suite;
and at least once per release.

---

## 7. Reporting language rules

Checkable rules, linted over report templates by `tests/unit/test_report_language.py`.

**Required**
- Every timing result carries n, an interval, the mechanism, and the region.
- Every category result carries coverage and confidence.
- `NOT_MEASURED` is rendered with the literal sentence "NOT_MEASURED is not a pass."
- Every report includes a limitations section naming: single account, single region,
  simple policies, deterministic worker, small n.
- Every finding renders `observation`, `expected_state`, `observed_state`, and
  `security_interpretation` under separate headings, in that order.

**Forbidden in generated text** (the lint greps for these)
- "vulnerable", "vulnerability", "exploit", "broken", "insecure", "flaw" applied to a
  provider.
- A timing value without an interval.
- A percentage without its denominator.
- "proves", "demonstrates conclusively", "guarantees".
- Any claim about a provider generally, as opposed to the measured environment.

**Preferred phrasing**
- "Authorization remained effective for X–Y s after the mutation request."
- "In this environment, at this time, with n=5."
- "This is consistent with documented bearer-token semantics."
- "The measurement was inconclusive because …"

---

## 8. Lab log

Every experiment block appends to `docs/research/lab-log.md`:

```
## 2026-08-07 block-03
checklist: 0.1-0.9 pass (0.6 offset -3.2ms)
scenarios: revocation/inline-deny.yaml v1.0.0, revocation/trust-policy.yaml v1.0.0
runs: 01J8XK…, 01J8XM…, 01J8XN…, 01J8XP…, 01J8XQ…
negative controls: nc-no-revocation -> DETECTOR_OK
anomalies: run 01J8XN excluded, ERROR_TRANSIENT x2 on poll 41-42 (throttling)
observation: transition window 36.9-39.4s median 38.1s IQR 4.2s (n=4 after exclusion)
notes: block run 14:00-15:00 UTC; second block scheduled 22:00 UTC per C-7
```

The lab log is the human-readable counterpart to the evidence bundles and is what makes a
suite defensible months later. It records exclusions **with reasons**, which is the single
most important honesty mechanism in the protocol.

---

## 9. Publication checklist

Before any result leaves the operator's machine:

1. Full negative-control suite passed in the same block.
2. n ≥ 5 for timing, n ≥ 3 for set-valued, across ≥ 3 blocks for timing.
3. Excluded trials counted, with reasons, in the report.
4. `chainbreak evidence export --public` run; scrub diff reviewed.
5. Limitations section present and specific.
6. No forbidden language (lint passes).
7. Claims scoped to "this account, this region, this time".
8. PROJECT_STATUS.md updated to reflect that the experiment actually ran, with run IDs.
9. If a result suggests a genuine provider defect rather than documented behavior: **stop
   and follow coordinated disclosure** before publishing. See [SECURITY.md](SECURITY.md).
