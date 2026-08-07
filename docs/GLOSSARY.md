# Glossary

Precise meanings as used in this repository. Where a term has a looser everyday meaning,
the difference is stated — several of these distinctions carry real analytic weight.

---

**Agent identity.** A non-root identity in an authorization graph that receives authority by
delegation. In the AWS adapter this is an IAM role; the core model does not know that.

**Attenuation.** The intended reduction of authority across a delegation hop. Correct
attenuation means the target's effective authority equals the source's effective authority
intersected with the hop's intended capabilities.

**Authority, delegation-time.** Effective authority measured immediately after a credential
was issued.

**Authority, effective.** The capability set empirically demonstrated by probe outcomes.
Only `ALLOWED` outcomes contribute (AUTH-1). Authority that exists but has no probe is
invisible, and the probe universe is recorded so the boundary of the claim is explicit.

**Authority, execution-time.** Effective authority at the moment a deferred task actually
runs. Differs from delegation-time authority when policy changed in between — that gap is
the subject of the stale-authority family.

**Authority, expected.** What the scenario says an identity should hold. For a non-root node
it is *derived*: `parent.expected ∩ edge.intended`. A scenario may also declare it
redundantly, and the compiler asserts the two agree.

**Authority, intended.** What a delegation hop is designed to confer. A property of an
edge, not a node. Distinct from expected authority, and conflating the two makes negative
controls inexpressible.

**AuthoritySet.** A canonically ordered frozen set of capability IDs. All divergence
computation is set algebra over these.

**Authorization graph.** A rooted DAG: identities as nodes, delegations as edges. Subject to
invariants G-1 (acyclic) through G-5 (bounded depth).

**Block.** A group of experiment trials run in one time window. Timing trials are
distributed across at least three blocks (control C-7) because provider-side propagation may
vary with load.

**Bootstrap identity.** The role that writes markers, verifies preconditions, snapshots
policy, and applies mutations. Deliberately **not** a node in any authorization graph: an
identity that can rewrite policy must never be a measurement subject.

**Capability.** An abstract, provider-neutral unit of authority defined by an observable,
benign, verifiable operation (`objectstore.read`). Not an action string.

**Capability, control.** `identity.whoami`. Granted to every identity, cannot be denied by an
identity policy. Its failure means the apparatus is broken, so the matrix is discarded
rather than recorded as denials.

**Coverage.** Classified cells ÷ attempted cells. Below 0.7 a category is reported `PARTIAL`
regardless of what the measured cells showed.

**Compiled hash.** SHA-256 over the canonical scenario spec plus catalog and adapter
versions. Two runs with different compiled hashes are not directly comparable.

**Confidence.** `HIGH`/`MEDIUM`/`LOW`/`INSUFFICIENT`, computed from coverage, trial
unanimity, error presence, and policy-snapshot success. Aggregated with `min`, never a mean.
No flag raises it.

**Delegation mechanism.** How authority transfers across an edge: `ROLE_CHAIN`,
`SESSION_POLICY_SCOPED`, `ROLE_CHAIN_WITH_SESSION_POLICY`, `DIRECT_ROLE_ASSUMPTION`,
`RESOURCE_POLICY_GRANT`.

**Delegation plane.** Runtime STS operations — assumption, session policies, credential
issuance, controlled mutations. Contrast provisioned identity plane.

**DETECTOR_FAILURE.** The finding type emitted when a negative control's declared
`expect_finding` was not produced. The only finding type that says something about
CHAINBREAK rather than the system under test.

**Divergence.** Any difference between expected and observed authority at a node. Expansion
(unexpected gain), narrowing (unexpected loss), or mixed.

**Divergence, first.** The lowest hop index on a root-to-leaf path where divergence occurs.
The remediation target: hops below it usually inherit rather than cause the problem.

**Drift class.** How a node's divergence relates to its parent's: `ORIGINATED`,
`PROPAGATED`, `AMPLIFIED`, or `CORRECTED`. `CORRECTED` distinguishes "the system is broken"
from "defense in depth is working", and a benchmark that cannot express it produces
alarmist output.

**Evidence bundle.** The directory of sealed, append-only artifacts a run produces. The
durable deliverable; reports are disposable renderings of it.

**Exclusion.** A trial removed from analysis, always with a recorded reason and counted in
the report. Silent exclusion is the classic way to manufacture a clean result.

**Finding.** A conclusion derived from observations by `analyze`. Regenerable. Carries
`observation`, `expected_state`, `observed_state` and `security_interpretation` as separate
fields.

**Marker.** A benchmark-owned object or item with a known digest that read probes target.
Its verified presence is what makes a read probe interpretable at all: on S3, a missing key
and a denial return the same error when the caller lacks `s3:ListBucket`.

**Namespace.** `cb-` plus eight hex characters derived from account, workspace and salt.
Every benchmark resource carries it. Every probe target is asserted against it before the
call (SI-2).

**Negative control.** A scenario with a deliberately injected defect whose detection is
asserted. Lives in `scenarios/_negative-controls/` and declares `expect_finding`.

**Observation.** One probe attempt, immutable, written during the run. The atom of the
system.

**Outcome class.** The classification of a probe attempt. `ALLOWED`, three `DENIED_*`
variants, three `ERROR_*` variants, `INDETERMINATE`. `ERROR_*` is an *absence* of
measurement, not a negative measurement.

**Phase.** A named point in a run's plan: `PROBE`, `MUTATE`, `POLL`, `WAIT`,
`DEFERRED_EXECUTION`, `TASK`, `SNAPSHOT`.

**Preflight.** The provider-side gate run before any benchmark call: account allowlist,
region, namespace, tags, markers, cost, clock. `GetCallerIdentity` is the first call and, on
account mismatch, the only one.

**Probe.** A single benign operation executed to test one capability for one identity.

**Probe matrix.** The cartesian product of identities and capabilities under test at a
phase. Its *universe* defaults to every capability the scenario names — you cannot detect
expansion by testing only what you expect.

**Probe cell.** One (identity, capability) pair across its trials. `ALLOWED` only if every
trial was `ALLOWED` (ADR-012).

**Provisioned identity plane.** Terraform-managed roles, policies and resources. Contrast
delegation plane.

**Receipt.** Confirmation that a policy mutation was written, ideally by read-after-write.
Anchors every revocation measurement. An unconfirmed mutation makes the resulting timing
`INCONCLUSIVE`.

**Redaction.** The single serialization choke point every evidence record passes through. It
*raises* on detecting a secret rather than sanitizing — a leak is a bug to fix, not a value
to clean up.

**Revocation mechanism.** Which controlled change was applied: `ATTACH_INLINE_DENY`,
`REMOVE_INLINE_POLICY`, `UPDATE_TRUST_POLICY`, `REVOKE_OLDER_SESSIONS`,
`DELETE_SESSION_POLICY_SCOPE`. The independent variable of the revocation family.

**Safety envelope.** The resolved set of safety constraints — account allowlist, regions,
namespace, duration ceiling, cost ceiling, depth limit. A run without one is refused (SI-5).

**Sealing.** Computing per-artifact hashes and a root at run completion. Tamper-evidence,
not tamper-proofing.

**Session policy.** A policy supplied at `AssumeRole` that *intersects* with the role's
permissions. It cannot grant. This is why it is the correct primary attenuation mechanism to
test, and why a negative control must inject expansion through the role's own policy instead.

**Stale authority.** Authority that remains effective at execution time because it was
captured at delegation time. On bearer-token systems this is documented behavior; the
measurement of interest is the window duration, not its existence.

**Transition window.** `[t_last_allow, t_first_deny]` relative to the mutation anchor,
reported as an interval whose width is bounded by the polling period. Never a scalar.

**Trial.** One repetition of a probe cell. Default 3 for set-valued measurements, 5 for
timing.

**Unanimity.** The rule that a cell resolves only if all its trials agree. Disagreement
yields `INDETERMINATE` with the trial vector preserved.
