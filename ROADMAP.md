# CHAINBREAK Roadmap

Version numbers describe *capability*, not dates. A version ships when its acceptance
criteria are met and its experiments have actually run.

---

## v0.1 — AWS, five families, one provider

**Goal.** Prove the method works: measure the gap between intended and effective authority on
one cloud, with reproducible evidence and a detector that demonstrably detects.

**Scope.** AWS IAM/STS. Ten capabilities. Five benchmark families plus six negative controls.
Deterministic workers. Terraform sandbox. Evidence bundles, per-category scoring, terminal /
Markdown / HTML reports.

**Definition of shipped.** All twenty milestones complete; the full suite executed against a
real AWS benchmark account across at least three time blocks; every negative control
`DETECTOR_OK`; `results-v0.1.md` written from measured values only; v0.1.0 tagged.

**Explicitly out of scope.** A second provider. Real agent workers. Permission boundaries and
SCPs. Cross-account delegation. Any cross-provider claim.

---

## v0.2 — OIDC and workload federation

**Why next.** It is the smallest step that tests whether the abstractions hold. OIDC
federation on AWS uses `AssumeRoleWithWebIdentity` — a different credential-issuance path,
the same delegation model. If the `DelegationMechanism` enum and `IdentityRef` opacity were
designed correctly, this requires no change above the adapter boundary. If it does require
one, that is a valuable and early finding about the architecture.

**Adds.** `FEDERATED_TOKEN` mechanism. GitHub Actions OIDC as a realistic identity source.
Token-lifetime and audience-claim variables. Detached signing of evidence bundles
(`cosign`/`minisign`) — the manifest already reserves the key.

**Research question it opens.** Does authority attenuate identically when the root identity is
a federated token rather than a role?

---

## v0.3 — SPIFFE / SPIRE

**Why.** SPIFFE is the closest thing to a vendor-neutral workload identity standard, and its
SVID model makes "identity at execution time" explicit in a way IAM does not. It is the first
real test of the provider adapter boundary against something that is not a cloud IAM.

**Adds.** A SPIRE adapter. `WORKLOAD_IDENTITY` mechanism. SVID rotation as a variable — which
makes the stale-authority family substantially more interesting, since rotation is a designed
mitigation for exactly the window CHAINBREAK measures.

**Risk.** Requires running a SPIRE server and agents, which is real operational surface. If it
turns out to need Kubernetes, that dependency must be justified and confined to this
provider's test environment — it must not leak into the core.

---

## v0.4 — Azure workload identity, and real agent workers

Two independent tracks that happen to land together.

**Azure.** A second cloud. This is the first version that can make a cross-provider claim, and
it must do so carefully: denial semantics, consistency models and capability granularity all
differ, and [CAPABILITY_MODEL §6](CAPABILITY_MODEL.md#6-cross-provider-comparison--and-its-honest-limits)
lists why a naive comparison would be invalid. Expect the capability catalog to need a second
mapping table and possibly a capability split.

**Real agent workers.** An LLM-backed `TaskWorker` implementing the same Protocol as the
deterministic workers. This turns the silent-narrowing family from "does the harness check
contracts" into "does an autonomous agent fail observably when its authority is narrowed" —
the question that motivated the project. The comparison is only meaningful because v0.1 built
the deterministic baseline first.

Non-determinism arrives with this, and the methodology needs extending: n per condition rises
substantially, and results become distributional in a way the current statistical treatment
does not cover.

---

## v0.5 — Google Cloud IAM

A third cloud, and the first version where cross-provider results have enough n to be worth
generalizing over. Adds service-account impersonation chains, which are the closest analogue
to AWS role chaining and therefore the cleanest three-way comparison available.

---

## Beyond

Candidates, unordered and uncommitted:

**Kubernetes service accounts and projected tokens.** Natural after SPIFFE; the token-volume
projection model has a well-defined refresh behavior that the stale-authority family could
characterize.

**Vault dynamic credentials.** A different credential lifecycle entirely — leases and renewal
rather than fixed expiry. Would need a new credential-lifetime model.

**MCP authorization.** As agent tool-use protocols acquire authorization models, the same
questions apply: does a tool's effective authority match what the delegating agent intended?
CHAINBREAK's capability abstraction is the right shape for this, but the protocol needs to
stabilize first.

**Human-to-agent-to-agent delegation.** Chains that begin with a human authorization decision
rather than a service identity. Interesting because consent, not policy, defines the intended
scope at hop 0.

**Permission boundaries, SCPs and resource policies as variables.** The largest
external-validity gap in v0.1: real IAM has hundreds of statements and multiple evaluation
layers, and CHAINBREAK's roles are trivially simple by comparison. Closing this gap may
matter more than adding a fourth cloud.

**Multi-operator replication.** Three independent operators running the suite and publishing
bundles. This is the prerequisite for characterizing inter-environment variance — and
therefore the prerequisite for any composite score
([SCORING_MODEL §6](SCORING_MODEL.md#6-conditions-for-introducing-a-composite-score)).

---

## Things this project will not do

Not a roadmap gap — a boundary.

- Automated exploitation of any finding.
- Scanning or discovery against accounts the operator has not explicitly allowlisted.
- A hosted service, a dashboard product, or a SaaS offering.
- A leaderboard or public scoreboard of provider "scores". See ADR-010: a gamed security
  benchmark produces worse security.
- Any capability listed in [SECURITY_MODEL §6](SECURITY_MODEL.md#6-what-chainbreak-will-never-implement).

---

## How a version gets prioritized

In order: (1) does it test whether an existing abstraction is right, (2) does it open a
research question the current version cannot answer, (3) does it reduce a named
external-validity threat, (4) is it maintainable by one engineer.

Adding a provider that merely increases surface area without doing (1) or (2) is not
progress.
