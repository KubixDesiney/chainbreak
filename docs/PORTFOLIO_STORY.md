# CHAINBREAK as a Portfolio Artifact

How to present this project honestly, and what it actually demonstrates.

> **Read this first.** As of 2026-08-18, CHAINBREAK has a complete architecture, a verified
> domain model, a validated scenario corpus, and three valid real-AWS M17 blocks. The blocks
> contain 87 analyzed/exported runs (`n=32`, `n=23`, `n=32`) and six `DETECTOR_OK` controls per
> block. The measured timing rows and exact run IDs are in
> [results-v0.1.md](research/results-v0.1.md); they apply only to this account, this region,
> and this time. W03/W04/W05 and the older AWS blocks remain excluded apparatus records.
> Fake-provider outputs remain apparatus checks. IAM cleanup completed 2026-09-01 with the
> account verified clean; the `0.1.0` release candidate now awaits only the owner's explicit
> publication approval.

---

## The problem, in one paragraph

Cloud systems hand authority down chains of identities — a human authorizes a service, the
service assumes a role, that role assumes another, and eventually an autonomous process acts.
Every hop is supposed to attenuate authority, and every policy change is supposed to
propagate. Those are assumptions, and they are rarely measured. CHAINBREAK measures them:
the gap between the authority a policy *intended* to grant and the authority a workload
*actually* holds, and the gap between authority at delegation time and authority at execution
time.

## Why it matters now

Agentic systems make both gaps operationally significant rather than theoretical. A human
operator who receives excess permissions usually does not exercise them. An autonomous process
that receives excess permissions will use whatever it has if a task calls for it. The same is
true in reverse: a human notices when a task fails for lack of permission; an agent may
produce output that looks complete. The window between "policy changed" and "authority
actually gone" used to be a background risk. It is now a window during which an autonomous
process is still acting.

That framing is the strongest thing about this project, and it is true regardless of what the
measurements eventually show.

---

## What the work demonstrates

### Security engineering judgment

The clearest example is the 403/404 problem. On S3, `GetObject` against a missing key returns
`AccessDenied` — identical to a denial — when the caller lacks `s3:ListBucket`, which an agent
under test generally does. Without a guaranteed marker, "can this identity read?" is
unanswerable, and a naive benchmark would report a wave of denials while measuring nothing.
CHAINBREAK's response is three layered controls: precondition verification by a separate
provisioning identity, content-digest verification on success, and a distinct
`ERROR_RESOURCE_MISSING` outcome class kept out of both the allow and deny sets.

This is the kind of detail that separates a benchmark that produces numbers from one that
produces correct numbers, and it is a good answer to "tell me about a hard technical problem".

### Threat modeling a tool that could do damage

CHAINBREAK holds cloud credentials, creates identities, and mutates authorization policy. The
security model therefore has two structural goals: make it difficult to affect anything
outside the benchmark namespace *even when the operator errs*, and make credential disclosure
impossible rather than unlikely. Twelve invariants, each with a named enforcement point and a
merge-gate test. Fifteen threats with mitigations and — the part reviewers actually check —
seven accepted residual risks, stated plainly rather than hidden.

The best specific example: `SecretMaterial` raises on `str`, `repr`, `format`, `bytes`,
pickling and Pydantic serialization, so a stray f-string fails loudly instead of leaking; and
`redact()` *raises* on detecting a secret rather than sanitizing, because a leak is a bug to
fix, not a value to clean up. The redaction test is reflection-driven, so a future model field
carrying a secret is covered without anyone remembering to add a test.

### Research methodology

The methodology is written to a standard a paper would require: five research questions,
eight falsifiable hypotheses with their expected outcomes stated in advance, nine named
experimental controls, and an explicit threats-to-validity section covering internal,
external, construct and conclusion validity.

Two design choices are worth walking through in an interview:

**H4 as an instrument check.** Updating a trust policy should *not* revoke a live session,
because trust policies gate issuance rather than use. Running it as a within-experiment null
condition means that if CHAINBREAK ever reports a fast transition there, the apparatus is
wrong — and the whole block is discarded rather than published.

**The paired fresh credential.** In the stale-authority family, a deferred probe that succeeds
is ambiguous between "the policy change never propagated" and "the old credential retained
old authority". Probing again immediately with a freshly minted credential disambiguates
them. Without that pair the family produces uninterpretable results, and the design element
costs almost nothing.

### What was measured

The valid M17 blocks were `cb-m17-20260818-01` (`n=32`), `cb-m17-20260818-02` (`n=23`), and
`cb-m17-20260818-03` (`n=32`), for 87 AWS runs in `eu-west-3`; the exact run IDs, mechanisms,
intervals, and this-account/region/time scope are recorded in
[results-v0.1.md](research/results-v0.1.md). Timing conditions have `n=5` runs per row. The
two explicit-deny rows measured `10.500–12.265 s` and `10.046–11.375 s`; three revocation rows
recorded no transition within the configured poll window. Stale-authority waits measured
`30.907–31.062 s`, `120.938–122.250 s`, and `600.906–602.688 s` across two declared
capabilities per run; post-expiry recorded no stale window. These are measurements of this
account, this region, this time, not AWS-general claims.

### Knowing what not to claim

Several decisions cost capability in exchange for defensibility:

- **No composite score** (ADR-010). Weights would be invented; a score would do rhetorical
  rather than analytical work; and a gamed security benchmark produces worse security.
- **Observation separated from conclusion** (ADR-006), structurally — different objects,
  different lifetimes, different fields, different report headings.
- **Eventual consistency is not a vulnerability.** A nonzero propagation interval is the
  expected result. The contribution is characterizing the distribution, not discovering that
  it is positive. Reports are linted against words like "broken" and "vulnerable".
- **`NOT_MEASURED` is not a pass**, rendered as that literal sentence, because the most common
  way a benchmark misleads is by letting absence of measurement read as absence of problems.

### Detector validation

Six negative controls, one per injected-defect kind, each declaring the finding it must
produce. `DETECTOR_FAILURE` is a first-class finding type, and a block containing one is
unvalidated regardless of what else passed. A benchmark that only reports PASS has not
demonstrated it can detect a failure — this is the mechanism that closes that gap, and it is
machine-checked.

### Technical breadth

AWS IAM and STS mechanics (role chaining and its 3600-second cap, session policies and their
intersection semantics, five distinct revocation mechanisms, trust-policy conditions,
`RoleSessionName` for CloudTrail correlation). Terraform module design with a stable output
interface consumed across a language boundary. Python architecture with an enforced
dependency rule, a Protocol-based adapter boundary, and a shared contract suite both
implementations must pass. A four-layer test strategy where CI needs no cloud credentials at
all.

---

## Interview talking points

**"Walk me through a design decision you'd defend."**
Empirical probing over policy simulation (ADR-009). Simulation is cheaper, faster, and needs
no infrastructure — but it answers "what does the policy evaluator say about the request as I
described it", not "what happened". Building on it would also mean measuring AWS's evaluator
against AWS's evaluator, which is tautological. Probing puts an independent observation
between the policy and the conclusion.

**"What's the hardest bug you anticipated?"**
The 403/404 ambiguity. It would not have surfaced as a failure — it would have surfaced as
plausible-looking denials, which is worse.

**"How do you know your tool is right?"**
Three ways. A deterministic fake provider with a real policy evaluator and known ground truth,
so the analysis is validated against answers we already know — including timing, by injecting
a known propagation delay and asserting the measured interval contains it. Negative controls
with `DETECTOR_FAILURE` as a first-class outcome. And publishing raw evidence bundles, because
systematic error that our own controls do not model can only be caught by someone else.

**"What would you do differently?"**
Two things. The capability catalog operationalizes "can read" as "can read *this marker*",
which is precise but narrower than a reader's intuition — it needs stating in every report,
and a richer construct would be better. And v0.1's roles are trivially simple compared with
production IAM: no permission boundaries, no SCPs, no resource policies of consequence. That
is the largest external-validity gap, and closing it may matter more than adding a second
cloud.

**"How do you handle a result you can't explain?"**
`INCONCLUSIVE`, with a machine-readable reason, and the report says so. The confidence gate
downgrades automatically and no flag can raise it. A benchmark whose failure mode is a
confident wrong number is worse than no benchmark.

**"What did you not build?"**
Kubernetes, multi-cloud, a web UI, LLM orchestration, distributed execution, SIEM
integration. Each would have added operational surface without improving the measurement. The
research artifact is the product.

---

## How to present it

**In a CV bullet.** "Designed and built an open-source benchmark measuring authorization
drift in delegated AWS identity chains — capability abstraction over IAM/STS, Terraform
sandbox, negative-control-validated detectors, reproducible evidence bundles."

**In a portfolio README.** Lead with the research question, then the architecture diagram,
then the current status — accurately. A reviewer who sees an honest status block trusts the
rest of the document.

**In conversation.** Lead with the problem, not the implementation. "When an agent hands
authority to another agent, does the authority actually shrink the way the policy says?" is a
question most cloud security engineers have not measured, and that is more interesting than
any architecture diagram.

**What not to do.** Do not present the architecture as results. Do not quote a propagation
number that has not been measured in an account you ran it in. Do not describe documented
bearer-token behavior as a discovery. Every one of these is checkable in about thirty seconds
by someone who knows AWS, and failing that check costs more than the claim was worth.

---

## Update checklist for M19

- [x] Replace the status banner with what M17 actually measured, with run IDs.
- [x] Add a results summary: which families ran, n per condition, which categories were
      `NOT_MEASURED`.
- [x] Add the honest surprises — including the ones where nothing surprising happened, since
      "the documented behavior held, measured as follows" is a legitimate and useful result.
- [x] Add the engineering problems actually hit during M8/M9/M17, which will be better
      interview material than the anticipated ones above.
- [x] Re-verify every claim in this document against `PROJECT_STATUS.md`.
