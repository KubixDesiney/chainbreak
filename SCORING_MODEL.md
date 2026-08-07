# CHAINBREAK Scoring Model

**v0.1 position: CHAINBREAK does not emit a composite security score.**
It emits six independent category results, each carrying its own measurements, coverage, and
confidence. This document explains that decision, defines each category, and specifies what
would have to be true before a composite score could be justified.

---

## 1. Why no single number

A composite score would require weighting incommensurable quantities — a set difference
(capabilities), a duration (seconds), and a behavioral classification (loud vs. silent
failure) — and the weights would be invented. Any reader could reasonably disagree with
them, and the score would then be doing rhetorical work rather than analytical work.

Worse, a score compresses away the thing that makes the evidence useful. "CHAINBREAK score:
72/100" tells an engineer nothing actionable. "Hop 3 grants `keyvalue.read` that hop 3's
session policy did not intend; confidence HIGH; here are the three probe IDs" tells them
exactly what to fix.

There is also a self-interested reason to be careful. A benchmark that publishes a score
invites comparison, comparison invites gaming, and gaming a security benchmark produces
worse security. A benchmark that publishes measurements invites replication.

See [ADR-010](docs/adr/ADR-010-no-composite-score.md).

---

## 2. Category results

Each category yields a `CategoryResult`:

```python
CategoryResult(
    category: ScoringCategory,
    status: Literal["CONSISTENT", "DIVERGENT", "PARTIAL", "NOT_MEASURED", "DETECTOR_FAILED"],
    measurements: list[Measurement],     # each with low/point/high + unit
    findings: list[FindingRef],
    coverage: float,                     # measured cells / applicable cells
    confidence: Confidence,              # min() across contributing findings
    caveats: list[str],
)
```

`status` is a description of the measurement, not a grade. `CONSISTENT` means observed
matched intended within the measured scope — it does **not** mean "secure". The distinction
is stated in every report.

### 2.1 Delegation Integrity

*Does each hop transfer exactly the authority it declared?*

- **Applies to:** every `DelegationEdge` with both endpoints measured.
- **Primary measurement:** per edge, `attenuation_correct` (bool), plus
  `|survived_incorrectly|` and `|dropped_incorrectly|`.
- **`DIVERGENT` when:** any edge has `survived_incorrectly ≠ ∅`.
- **Reported as:** a per-edge table plus the chain's first divergence hop.

### 2.2 Scope Attenuation

*Is authority non-increasing along every path?*

- **Primary measurements:** `attenuation_monotone_set` (∀i: `observed(hᵢ₊₁) ⊆ observed(hᵢ)`)
  and `attenuation_monotone_cardinality`.
- **`DIVERGENT` when:** set monotonicity fails anywhere.
- Note: cardinality monotonicity can hold while set monotonicity fails (a hop swapping one
  capability for another). Set monotonicity is the property that matters; cardinality is
  reported because it is what a reader's intuition reaches for first.

### 2.3 Revocation Responsiveness

*After a controlled policy change, how long does previously granted authority remain effective?*

- **Primary measurement:** `transition_window = [low, high]` seconds, per (identity,
  capability, revocation mechanism).
- **Status mapping:** `CONSISTENT` if a transition was observed within the polling window;
  `PARTIAL` if `NO_TRANSITION_OBSERVED_WITHIN_WINDOW`; `DIVERGENT` **only** if an
  `assertive` scenario expectation was exceeded.
- **There is no built-in threshold.** CHAINBREAK does not assert what an acceptable
  propagation time is; that is an operator's risk decision. A scenario may set one, and must
  justify it in a comment.
- Mechanism is reported alongside every interval, because a 40 s interval for
  `ATTACH_INLINE_DENY` and a 40 s interval for `UPDATE_TRUST_POLICY` mean entirely different
  things (the latter should show *no* transition at all for live sessions).

### 2.4 Authority Freshness

*Does deferred execution use current or historical authority?*

- **Primary measurement:** the stale-authority classification per deferred task, plus
  `stale_window_seconds = t_exec − t_M` when authority was stale.
- **`DIVERGENT` when:** classification is `EXPIRED_CREDENTIAL_HONORED`. That is the one
  outcome that contradicts documented provider behavior.
- `STALE_AUTHORITY_LIVE_CREDENTIAL` yields `CONSISTENT` with a prominent note: this is
  expected bearer-token behavior, and the measurement of interest is the *window duration*,
  which is an input to an operator's credential-lifetime policy.

### 2.5 Failure Transparency

*When authority is insufficient, does the workload fail loudly?*

- **Primary measurements:** per task — `reported_insufficient_authority`,
  `substituted_capabilities`, `redelegation_attempts`, `output_marker_written` vs
  `status`.
- **`DIVERGENT` when:** `status == COMPLETE` while `steps_succeeded < steps_total`, or a
  `completion_contract` clause was violated.
- This is the only category that measures the *workload's* behavior rather than the cloud's.
  In v0.1 the workload is a deterministic worker, so the category measures the benchmark's
  own contract-checking. Its value grows substantially when v0.4 introduces real agent
  workers — the plumbing is built now so the comparison is possible later, and the report
  states plainly that v0.1 results here describe a synthetic worker.

### 2.6 Credential Hygiene

*Do issued credentials behave as requested?*

- **Primary measurements:** requested vs granted lifetime per credential; `lifetime_capped`
  count; observed time-to-first-failure after `expires_at`; session-policy fingerprint
  presence on every scoped delegation.
- **`DIVERGENT` when:** a credential remained usable after its stated `expires_at`, or a
  delegation declared a session-policy scope but no fingerprint was recorded (which would
  mean the scope was never applied).
- `lifetime_capped` alone yields `CONSISTENT` + an informational finding: capping is
  documented AWS behavior, and the value is telling the operator their requested duration is
  not what they got.

---

## 3. Coverage and confidence are first-class

Every category reports `coverage` = measured applicable cells / total applicable cells. A
category with `coverage < 0.7` is reported as `PARTIAL` regardless of what the measured
cells showed, and the report leads with the coverage number rather than the result.

`confidence` is the **minimum** across contributing findings, never an average. One
`LOW`-confidence input makes the category `LOW`. Averaging confidence would let a pile of
easy measurements launder one shaky one.

Neither value can be improved by a CLI flag. `--allow-unsealed` and
`--allow-heterogeneous` exist, but they *lower* confidence; there is no flag that raises it.

---

## 4. Report shape

```
CHAINBREAK — run 01J8XKQ4V7ZP3N2M9YB6TCFR5A
scenario delegation-drift-four-hop v1.2.0    provider aws (adapter 0.1.0)

CATEGORY RESULTS
  Delegation Integrity        DIVERGENT     coverage 1.00   confidence HIGH
  Scope Attenuation           DIVERGENT     coverage 1.00   confidence HIGH
  Revocation Responsiveness   NOT_MEASURED  (no MUTATE phase in this scenario)
  Authority Freshness         NOT_MEASURED
  Failure Transparency        NOT_MEASURED
  Credential Hygiene          CONSISTENT    coverage 1.00   confidence HIGH
                                            1 informational: LIFETIME_CAPPED on hop-2

NOT_MEASURED is not a pass. Three of six categories were not exercised by this scenario.
```

That last line is printed literally, every time. The most common way a benchmark misleads is
by letting absence of measurement read as absence of problems.

---

## 5. Cross-run aggregation

`chainbreak analyze --aggregate` combines runs **only** when `compiled_hash`,
`adapter_version`, and `catalog_version` all match. Aggregated output reports, per
measurement: n, median, IQR, min, max, and the count of `INCONCLUSIVE` runs excluded. No
mean without a dispersion measure; no dispersion measure below n=5, where the count is
reported instead. See [RESEARCH_METHODOLOGY.md §8](RESEARCH_METHODOLOGY.md#8-statistical-treatment).

---

## 6. Conditions for introducing a composite score

A composite score becomes defensible only when all of the following hold, and its
introduction requires a new ADR superseding ADR-010:

1. At least three independent operators have run the suite and published bundles.
2. Inter-run variance for each category is characterized, so a score's error bar exists.
3. Weights are derived from something external — a published control framework, a survey of
   practitioners — rather than chosen by the maintainer.
4. The score is always displayed with its component vector and its error bar.
5. Raw measurements remain in the default output; the score never replaces them.

Until then, the answer to "what's the score?" is "here are six measurements and their
confidence", and that is the correct answer.
