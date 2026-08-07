# CHAINBREAK Research Methodology

This document is written to the standard a technical paper would require. It defines what
CHAINBREAK measures, how, under what controls, with what statistical treatment, and — at
length — what it cannot conclude.

**No measurement described here has been performed.** This is the method, not the results.
See [PROJECT_STATUS.md](PROJECT_STATUS.md).

---

## 1. Research questions

**RQ1 (Authority axis).** In a delegation chain of depth *d*, does the effective authority
of each identity equal the authority the delegation policy intended to confer?

**RQ2 (Time axis).** After a controlled authorization change at time *t_M*, for how long
does previously conferred authority remain effective, and how does that interval depend on
the revocation mechanism?

**RQ3 (Deferred execution).** When a task authorized at *t₀* executes at *t₁ > t_M*, does it
operate under the authorization state current at *t₁* or the state captured at *t₀*?

**RQ4 (Behavioral).** When a workload's authority is legitimately narrower than its task
requires, does it fail observably, or does it produce output that appears complete?

**RQ5 (Depth).** Does delegation depth correlate with divergence between intended and
effective authority?

RQ5 is the one most likely to yield a genuinely novel result and the one most vulnerable to
confounding, so it carries the most controls (§4).

---

## 2. Hypotheses

Stated as falsifiable predictions with the direction we expect from documented provider
behavior, so that a *confirming* result is uninteresting and a *disconfirming* result is the
finding.

| ID | Hypothesis | Expected outcome from documentation | What would be surprising |
|---|---|---|---|
| H1 | Session-policy attenuation is exact: `observed(child) = observed(parent) ∩ intended` | Holds — session policies intersect and cannot grant | Any expansion |
| H2 | Effective authority is non-increasing along a chain (set inclusion) | Holds | Non-monotone sets |
| H3 | `ATTACH_INLINE_DENY` produces a transition within a bounded interval | Holds, interval > 0 | No transition within the window |
| H4 | `UPDATE_TRUST_POLICY` produces **no** transition for a live session | Holds — trust policy gates issuance only | Any transition (would indicate a measurement fault) |
| H5 | A live credential retains pre-mutation authority until deny propagation or expiry | Holds — bearer-token semantics | Immediate revocation without a deny |
| H6 | A credential is unusable after `expires_at` | Holds | Any success after expiry (would be significant) |
| H7 | Chained-role credentials are capped at 3600 s regardless of request | Holds | Longer grant |
| H8 | Divergence rate is independent of depth at depths 2–6 | Unknown — this is the open question | A depth effect either way |

H4 doubles as an instrument check. H8 is the only hypothesis whose expected outcome is
genuinely unknown; the rest establish that the apparatus measures reality correctly, which
is a prerequisite for believing H8's result.

---

## 3. Variables

**Independent (manipulated)**

| Variable | Levels | Family |
|---|---|---|
| Delegation depth | 1, 2, 3, 4, 5, 6 | drift, RQ5 |
| Delegation mechanism | `ROLE_CHAIN`, `SESSION_POLICY_SCOPED`, `ROLE_CHAIN_WITH_SESSION_POLICY` | attenuation |
| Revocation mechanism | 5 kinds (see [AWS_PROVIDER_SPEC §4](AWS_PROVIDER_SPEC.md#4-delegation-mechanics-and-their-constraints)) | revocation |
| Deferral interval | 30, 120, 600 s | stale authority |
| Requested credential lifetime | 900, 3600, 7200 s | credential hygiene |
| Capability sensitivity | read-only vs. read+write sets | all |
| Injected defect (neg. control) | 6 kinds | all |

**Dependent (measured)**

`observed_authority` per (identity, phase); `unexpected_gain` / `unexpected_loss`
cardinality and membership; `first_divergence_hop`; `transition_window [low, high]`;
`stale_window_seconds`; `granted_duration_s`; `task_outcome` fields; `coverage`; per-probe
latency.

**Controlled (held constant within an experiment)**

Region; STS endpoint (regional, pinned); account; capability catalog version; adapter
version; probe implementation; polling interval; trial count; resource state (markers
verified before each matrix); time of day within a block (§5); concurrency (serial for
timing-sensitive scenarios).

**Uncontrolled and recorded**

Provider-side load; network RTT (measured per probe); IAM propagation topology (opaque);
provider software version (unobservable); throttling behavior.

---

## 4. Experimental controls

**C-1 · Control capability.** `identity.whoami` is probed in every matrix. It cannot be
denied by an identity policy, so its failure indicates apparatus fault, and the matrix is
discarded rather than reported.

**C-2 · Precondition verification.** Markers are verified present and content-matched by the
bootstrap identity before every read matrix. Without this, a missing marker is
indistinguishable from a denial on S3 ([AWS_PROVIDER_SPEC §6.1](AWS_PROVIDER_SPEC.md#61-the-403404-problem)).

**C-3 · Baseline probe.** The principal is probed before every experiment. Baseline
divergence from its declared capability set aborts the run — it means the infrastructure
does not match the scenario's assumptions.

**C-4 · Negative controls.** Each family ships a scenario with a deliberately injected
defect. Failure to detect it produces `DETECTOR_FAILURE`, which invalidates the
corresponding positive results in the same suite.

**C-5 · Instrument-check hypothesis.** H4 (`UPDATE_TRUST_POLICY` should not revoke a live
session) is run in every revocation block as a within-experiment null condition.

**C-6 · Order randomization.** Within a probe matrix, capability order is shuffled with a
recorded seed. Without this, a capability probed last would systematically carry more
credential age and more accumulated throttling pressure.

**C-7 · Block randomization across time.** Repeated trials of a timing experiment are
distributed across at least three separate hours rather than run back-to-back, because IAM
propagation may plausibly vary with provider-side load. Recorded as `block_id`.

**C-8 · Fresh-infrastructure condition.** A subset of runs is executed against
freshly-applied infrastructure and compared with runs against infrastructure applied hours
earlier, to detect any warm-up effect in policy propagation.

**C-9 · Fake-provider differential.** Every analysis path is exercised against the
deterministic fake provider with known ground truth. A finding that the fake provider
produces incorrectly is an analysis bug, discoverable without AWS.

---

## 5. Protocol summary

Full step-by-step protocol per family is in [EXPERIMENT_PROTOCOL.md](EXPERIMENT_PROTOCOL.md).
Structure common to all:

```
apply infrastructure  →  verify preconditions  →  baseline probe (principal)
  →  for trial in 1..n:            (trials distributed across blocks)
        delegate chain
        probe matrix (phase: after-delegation)
        [mutate + poll]  |  [wait + deferred execute]  |  [run task]
        probe matrix (phase: final)
        revert runtime mutations
  →  seal bundle  →  analyze  →  verify-clean  →  destroy
```

Minimum trials: **n = 5** for timing measurements, **n = 3** for set-valued measurements.
The asymmetry is deliberate: set-valued outcomes are near-deterministic (a policy either
grants or does not), so repetition guards against transient errors rather than variance.
Timing outcomes are genuinely stochastic and need a distribution.

---

## 6. Timing methodology

**All intervals are computed from `time.monotonic_ns()`.** Wall-clock time is recorded for
correlation only and never enters interval arithmetic. This makes measurements immune to NTP
steps mid-experiment.

**Anchor.** `t_M` is the monotonic instant the mutation request was *sent*. The
read-after-write confirmation latency is recorded separately, so an analysis can report
relative to either anchor and states which it used. Using the send instant is the
conservative choice: it can only make the measured window appear longer, never shorter.

**Resolution.** The polling interval (default 500 ms) bounds the uncertainty. Reported
uncertainty half-width is `(t_first_deny − t_last_allow)/2`, which is ≥ interval/2 and
absorbs RTT variance.

**Reported form.** Always `[low, high]` with a point estimate at the midpoint, never a bare
scalar. The `measurements` table in the SQLite index has no column for a scalar.

**Clock offset.** Local-vs-provider offset is estimated five times from HTTP `Date` headers
using the request-midpoint method and recorded. It is not used to correct anything. If
`|offset| > 1000 ms`, all timing findings in the run are automatically downgraded to LOW
confidence.

**Non-monotonic transitions.** If `ALLOWED` reappears after the first denial, the
measurement is flagged `NON_MONOTONIC_TRANSITION` and the full timeline is preserved.
Oscillation is a legitimate observation about eventual consistency, and smoothing it away
would destroy the most interesting possible result in the revocation family.

---

## 7. Eventual consistency

IAM is documented as eventually consistent. Three consequences shape the method:

1. **A nonzero propagation interval is the expected result, not a finding of insecurity.**
   The contribution is characterizing the distribution, not discovering that it is positive.
2. **A single measurement is nearly meaningless.** Reporting requires the distribution
   across ≥ 5 trials across ≥ 3 blocks.
3. **Absence of a transition within the window is reported as
   `NO_TRANSITION_OBSERVED_WITHIN_WINDOW` with the window length** — never as "revocation
   failed" and never as a pass.

Language discipline: reports say *"authorization remained effective for 37.2–39.0 s after
the policy change request, mechanism ATTACH_INLINE_DENY, n=5, median 38.1 s, IQR 4.2 s"*.
They do not say *"revocation is broken"*. [EXPERIMENT_PROTOCOL.md §7](EXPERIMENT_PROTOCOL.md#7-reporting-language-rules)
makes this a checkable rule with a lint over report templates.

---

## 8. Statistical treatment

Deliberately conservative, because n is small and the distributions are unknown.

- **Descriptive over inferential.** Report n, median, IQR, min, max, and the full ordered
  sample for timing measurements. Report exact counts and proportions for set-valued
  outcomes.
- **No mean without dispersion.** Enforced in the reporting layer.
- **No p-values in v0.1.** With n=5 per condition, a significance test would be theater.
  A hypothesis test appears only if a future version reaches n ≥ 30 per condition, and then
  it will be a non-parametric one (Mann–Whitney U for two-condition comparisons,
  Kruskal–Wallis across mechanisms) with the assumption checks stated.
- **Bootstrap CIs, when used, require n ≥ 20** and are labeled as such with the resample
  count.
- **Excluded trials are counted and reported.** A trial excluded for `ERROR_TRANSIENT`,
  failed precondition, or control-capability failure appears in the report as
  `excluded: k/n` with reasons. Silent exclusion is the classic way to manufacture a clean
  result.
- **Set-valued outcomes are reported as exact membership**, not just cardinality. "Observed
  2 of an expected 1" is far less useful than "observed `{objectstore.read, keyvalue.read}`,
  expected `{objectstore.read}`".

---

## 9. Threats to validity

**Internal validity**

- *Instrument error.* Mitigated by C-1, C-2, C-4, C-5, C-9. Residual: a systematic mapping
  error in a capability binding would produce consistent wrong results that pass every
  control. Mitigation of last resort: publish bundles for third-party re-analysis.
- *Ordering effects.* Mitigated by C-6.
- *Carryover between trials.* Mitigated by run-scoped scratch prefixes, baseline policy
  fingerprint comparison, and revert-in-`finally`.
- *Provider-side load confound.* Mitigated by C-7 block randomization; not eliminated.

**External validity**

- Results characterize **one AWS account, in one region, at one point in time**. AWS's
  propagation behavior is not contractually specified and may differ by region, account age,
  account size, or provider-side changes. No result generalizes to "AWS" as a whole, and
  reports must not be phrased as if it does.
- The benchmark's roles are trivially simple compared with production IAM. Divergence
  behavior under hundreds of statements, permission boundaries, SCPs, and resource policies
  is **not** measured by v0.1. This is arguably the single largest external-validity gap and
  is named in every report's limitations section.
- The v0.1 workload is a deterministic worker, not an autonomous agent. Failure-transparency
  results describe the harness, not real agent behavior.

**Construct validity**

- "Capability" is a modeling choice. `objectstore.read` operationalizes "can read an object"
  as "can `GetObject` one specific marker". A policy granting read on a *different* prefix
  would be scored as not holding the capability, which is correct for this construct but
  differs from what a reader might assume "can read" means. Stated explicitly in every
  report.
- "Effective authority" is operationalized as the set of capabilities whose probes returned
  `ALLOWED`. Authority that exists but has no probe is invisible. The probe universe is
  recorded in evidence so the boundary of the claim is explicit.

**Conclusion validity**

- Small n; unknown distributions; §8's conservatism is the response.
- Multiple comparisons: with 6 depths × 3 mechanisms × 10 capabilities, some divergence will
  appear by chance if any probe is noisy. Unanimity across trials and the confidence gate
  are the controls; the number of comparisons is reported.

---

## 10. Observation versus conclusion

The rule the whole project is organized around:

> **Observation:** "Authorization for `objectstore.read` by `agent-b` remained effective for
> 37.2–39.0 s after an `ATTACH_INLINE_DENY` mutation request, n=5, median 38.1 s, region
> pinned, regional STS endpoint."
>
> **Permissible conclusion:** "In this environment, an operator relying on inline-deny
> revocation should not assume sub-30-second propagation."
>
> **Impermissible conclusion:** "AWS has broken revocation."

The first is data. The second is a scoped engineering recommendation with its scope stated.
The third is a claim the method cannot support: it generalizes from one account, ignores
that eventual consistency is documented, and asserts a defect where a design property was
measured.

`Finding.observation` and `Finding.security_interpretation` are separate fields for exactly
this reason, and the report renders them under separate headings.

---

## 11. Reproducibility

Every run records the CHAINBREAK version, git commit and dirty flag, catalog version,
adapter version, compiled scenario hash, config fingerprint, infrastructure fingerprint,
randomization seeds, and full environment descriptor. Given the same commit, the same
scenario, and a comparable AWS account, another operator can re-run and compare. Set-valued
results should reproduce exactly; timing results should reproduce distributionally, not
exactly, and the report says so. See [REPRODUCIBILITY.md](REPRODUCIBILITY.md).

---

## 12. Ethics and scope

All experiments run in an account the operator owns, on identities and resources the
benchmark created, using benign operations. No third-party system is contacted. No
vulnerability is exploited. Should a measurement ever suggest a genuine provider defect
rather than documented behavior, the appropriate action is coordinated disclosure to the
provider before publication — not a blog post. This is stated in [SECURITY.md](SECURITY.md).
