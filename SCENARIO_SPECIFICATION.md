# CHAINBREAK Scenario Specification

**Schema version:** `chainbreak.dev/v1alpha1`
**JSON Schema:** [`schemas/scenario.v1alpha1.schema.json`](schemas/scenario.v1alpha1.schema.json)
**Pydantic model:** `src/chainbreak/scenarios/schema.py`

A scenario is a declarative description of an authorization experiment. It is
provider-neutral, deterministic to compile, and versioned.

---

## 1. Design constraints

The format was chosen against four requirements, in priority order:

1. **A reviewer must be able to read a scenario and state what it asserts** without running
   it. Security artifacts that require execution to understand do not get reviewed.
2. **Compilation must be pure.** Same document + same catalog + same adapter version ⇒
   identical `compiled_hash`. This is what makes runs comparable.
3. **Intent must be explicit and separable from expectation.** `intended_capabilities` on an
   edge is a *design statement*; `expect` on a node is an *assertion*. Conflating them makes
   negative controls impossible to express.
4. **Negative controls must be first-class**, not a naming convention.

YAML with a JSON Schema was chosen over a Python DSL because a DSL makes scenarios
executable code, which makes malicious scenario input (threat T-10) a code-execution risk
rather than a parsing risk. See [ADR-003](docs/adr/ADR-003-declarative-scenario-format.md).

---

## 2. Document structure

```yaml
apiVersion: chainbreak.dev/v1alpha1
kind: Scenario

metadata:
  id: delegation-drift-four-hop            # unique, kebab-case, stable
  version: 1.2.0                           # semver; bump on any semantic change
  family: delegation-drift                 # one of the five families
  title: Four-hop chain with session-policy attenuation at each hop
  description: >
    Measures whether effective authority attenuates monotonically across four
    delegation hops when each hop applies a session policy.
  authors: ["operator"]
  tags: [multi-hop, session-policy]

spec:
  provider: aws                            # or: fake
  requires:
    catalog_version: ">=1.0.0,<2.0.0"
    adapter_version: ">=0.1.0"
    infrastructure_profile: standard       # which Terraform environment must be applied

  execution:
    trials: 3                              # repetitions per probe cell
    timing_sensitive: false                # true => strictly serial probes
    max_duration_seconds: 900
    probe_universe: scenario               # declared | scenario | catalog

  identities: [...]                        # §3
  delegations: [...]                       # §4
  phases: [...]                            # §5
  tasks: [...]                             # §6  (silent-narrowing family)
  expectations: [...]                      # §7
  negative_control: {...}                  # §8  (optional)
```

`metadata.id` + `metadata.version` together identify a scenario in evidence. Changing
semantics without bumping `version` breaks run comparability and is caught by CI, which
hashes the spec block and compares against a recorded lockfile (`scenarios/.lock.json`).

---

## 3. `identities`

```yaml
identities:
  - id: principal
    role: root                             # root | agent
    provider_binding:
      terraform_output: principal_role_arn  # how the adapter resolves the real identity
    capabilities:                          # root only: declared, not derived
      - objectstore.read
      - objectstore.write
      - objectstore.list
      - keyvalue.read
      - keyvalue.write
      - function.invoke
      - identity.delegate

  - id: agent-a
    role: agent
    provider_binding:
      terraform_output: agent_a_role_arn
    # No `capabilities:` — expected authority is DERIVED from the inbound edge.
    # An optional `expect_capabilities:` may be given as a redundant assertion (§7).
```

Rules:

- Exactly one identity with `role: root`.
- `provider_binding` is the only provider-aware field in the document, and it is
  indirection-only: it names a Terraform output, never an ARN. A scenario file therefore
  contains **no account IDs, no ARNs, and no region names**, which is what makes scenarios
  safe to publish (threat T-13).
- `identity.whoami` is implicitly added to every identity's probe universe.

---

## 4. `delegations`

```yaml
delegations:
  - id: hop-1
    from: principal
    to: agent-a
    mechanism: ROLE_CHAIN
    intended_capabilities:                 # the design statement for this hop
      - objectstore.read
      - objectstore.write
      - keyvalue.read
      - function.invoke
      - identity.delegate
    credential:
      requested_lifetime_seconds: 3600
    constraints:
      session_name: cb-{run_id}-hop1       # templated; hashed in evidence
      session_tags:
        chainbreak_run: "{run_id}"
      external_id_ref: null

  - id: hop-2
    from: agent-a
    to: agent-b
    mechanism: SESSION_POLICY_SCOPED
    intended_capabilities:
      - objectstore.read
      - keyvalue.read
    session_policy:
      derive_from: intended_capabilities   # compiler generates the scoping policy
      # or: inline_ref: policies/hop2-session-policy.json  (must be namespace-scoped)
    credential:
      requested_lifetime_seconds: 900
```

`derive_from: intended_capabilities` instructs the compiler to ask the provider adapter to
synthesize the least-privilege session policy expressing exactly that capability set. The
generated document is fingerprinted into evidence. This keeps scenarios provider-neutral
while still exercising real session-policy semantics.

`inline_ref` is the escape hatch for testing hand-written policies (used by negative
controls). Inline policies are validated against the namespace regex before use: a policy
referencing a resource outside the benchmark namespace is a compile error.

**Templating.** Only `{run_id}`, `{namespace}`, `{scenario_id}`, `{hop_id}` are expandable.
Arbitrary expression evaluation is not supported, deliberately.

---

## 5. `phases`

Phases give scenarios their time dimension. The compiler emits an ordered execution plan.

```yaml
phases:
  - name: baseline
    kind: PROBE
    targets: [principal]

  - name: after-delegation
    kind: PROBE
    targets: [agent-a, agent-b, agent-c, agent-d]

  - name: revoke
    kind: MUTATE
    mutation:
      target_identity: agent-b
      kind: ATTACH_INLINE_DENY
      denies:
        - objectstore.read
      record_receipt: true

  - name: poll-transition
    kind: POLL
    target_identity: agent-b
    capability: objectstore.read
    interval_ms: 500
    max_duration_seconds: 300
    stop_on: STABLE_DENIAL          # STABLE_DENIAL | STABLE_ALLOW | TIMEOUT
    stability_count: 3

  - name: deferred
    kind: DEFERRED_EXECUTION
    target_identity: agent-c
    wait_seconds: 120
    credential_source: phase:after-delegation   # reuse the credential issued earlier
    targets: [objectstore.read, keyvalue.read]

  - name: final
    kind: PROBE
    targets: [agent-a, agent-b, agent-c, agent-d]
```

Phase kinds: `PROBE`, `MUTATE`, `POLL`, `WAIT`, `DEFERRED_EXECUTION`, `TASK`, `SNAPSHOT`.

`SNAPSHOT` captures policy state without probing. The compiler automatically inserts a
`SNAPSHOT` immediately before and after every `MUTATE`, so operators never have to remember
to; explicit snapshots are for additional points of interest.

`credential_source: phase:<name>` is the mechanism behind the stale-authority family: it
pins execution to a credential minted at an earlier phase rather than a fresh one.

---

## 6. `tasks` — the silent-narrowing family

```yaml
tasks:
  - id: two-step-pipeline
    worker: deterministic.sequential       # worker Protocol implementation id
    identity: agent-b
    requires_capabilities:
      - objectstore.read
      - keyvalue.write
    steps:
      - use: objectstore.read
        on_failure: continue               # continue | abort | retry
      - use: keyvalue.write
        on_failure: continue
    completion_contract:
      must_report_partial: true            # the worker MUST signal incompleteness
      must_not_substitute: true            # MUST NOT swap in a different capability
      must_not_redelegate: true            # MUST NOT seek authority elsewhere
```

The worker is deliberately dumb in v0.1. `deterministic.sequential` attempts each step and
reports a structured `TaskOutcome`:

```
{status: COMPLETE|PARTIAL|FAILED, steps_attempted, steps_succeeded,
 reported_insufficient_authority: bool, substituted_capabilities: [...],
 redelegation_attempts: [...], output_marker_written: bool}
```

Analysis compares the outcome against `completion_contract`. `status: COMPLETE` while
`steps_succeeded < len(steps)` is `SILENT_NARROWING`. `status: PARTIAL` with
`reported_insufficient_authority: true` is `EXPECTED_BEHAVIOR` — the system failed loudly,
which is the desired outcome.

`worker` is an extension point. v0.4 may register an LLM-backed worker implementing the
same Protocol; the analysis logic does not change. That is the point of specifying the
contract in terms of the outcome object rather than the worker's internals.

---

## 7. `expectations`

Expectations are assertions the analysis layer checks. They are *not* how expected authority
is derived — derivation comes from the graph (`parent ∩ intended`). Expectations are
redundant, explicit, and reviewer-facing.

```yaml
expectations:
  - kind: node_authority
    identity: agent-b
    phase: after-delegation
    allow: [objectstore.read, keyvalue.read]
    deny:  [objectstore.write, objectstore.list, keyvalue.write, function.invoke]

  - kind: attenuation_monotone
    path: [principal, agent-a, agent-b, agent-c, agent-d]
    mode: set                              # set (⊆) | cardinality (≤)

  - kind: no_first_divergence
    path: [principal, agent-a, agent-b, agent-c, agent-d]

  - kind: revocation_within
    identity: agent-b
    capability: objectstore.read
    max_seconds: 60
    severity: informational                # informational | assertive

  - kind: task_contract
    task: two-step-pipeline
```

`severity: informational` records the comparison without turning a miss into a failure. This
matters for `revocation_within`: CHAINBREAK does not know what the "correct" propagation
time is, and asserting one would be an unjustified normative claim. Timing expectations
default to informational; making one assertive requires a comment in the scenario file
justifying the threshold, which CI checks for.

**The `deny` list is mandatory** on `node_authority`. Listing only what should be allowed
means expansion goes undetected — you cannot fail a test you did not write.

---

## 8. `negative_control`

```yaml
negative_control:
  kind: INTENT_EXCEEDS_PARENT              # see table below
  rationale: >
    Agent C's role carries an inline policy granting keyvalue.read that the hop
    never intended to delegate, simulating a misconfigured role. CHAINBREAK must
    detect this as AUTHORITY_EXPANSION at hop 3.
  expect_finding:
    type: AUTHORITY_EXPANSION
    identity: agent-c
    capabilities: [keyvalue.read]
    min_confidence: MEDIUM
  suppress_graph_check: [G-3]              # which compile-time guardrails to downgrade
```

Negative controls are a schema feature rather than a naming convention, for the reasons in
[ADR-014](docs/adr/ADR-014-negative-controls-first-class.md). When `negative_control` is
present:

- Listed graph invariants are downgraded from errors to recorded warnings.
- After analysis, the harness asserts the declared `expect_finding` was produced. If it was
  **not**, CHAINBREAK emits `DETECTOR_FAILURE` and the run is reported as a benchmark
  failure regardless of what else passed.
- The scenario is excluded from any aggregate "system health" reporting, because its
  purpose is to fail.

| `kind` | Injected defect | Must be detected as |
|---|---|---|
| `INTENT_EXCEEDS_PARENT` | Child role granted a capability the hop did not delegate | `AUTHORITY_EXPANSION` |
| `SURVIVING_AUTHORITY` | Session policy fails to remove an inherited capability | `AUTHORITY_SURVIVAL` |
| `NON_MONOTONE_CHAIN` | Hop `n+1` broader than hop `n` | `DELEGATION_DRIFT` |
| `NO_REVOCATION` | Mutation applied to the wrong identity, so nothing revokes | `NO_TRANSITION_OBSERVED_WITHIN_WINDOW` |
| `SILENT_SUCCESS` | Worker configured to report COMPLETE on partial execution | `SILENT_NARROWING` |
| `STALE_CREDENTIAL_REUSE` | Deferred phase reuses a pre-mutation credential | `STALE_AUTHORITY` |

Negative controls live in `scenarios/_negative-controls/` and are additionally marked by
directory, so a reviewer cannot mistake one for a health check.

---

## 9. Validation pipeline

`chainbreak scenario validate` runs five stages and reports all failures in each stage
before stopping:

1. **Syntactic** — YAML parse, JSON Schema validation against `v1alpha1`.
2. **Structural** — Pydantic model construction; type and enum checks.
3. **Semantic** — graph invariants G-1…G-5, capability closure, phase ordering, references
   resolve (`credential_source`, `task.identity`, expectation targets).
4. **Provider binding** — every capability has a binding in the declared provider; every
   `provider_binding.terraform_output` exists in the declared `infrastructure_profile`'s
   output schema.
5. **Safety** — no literal ARNs/account IDs/regions anywhere in the document; every inline
   policy is namespace-scoped; no capability with `sensitivity: DANGEROUS` without opt-in.

Stage 5 runs even in `--offline` mode and cannot be skipped. It is the reason an untrusted
scenario file is a parsing problem rather than a security problem.

Exit codes: `0` valid, `2` schema/structural, `3` semantic, `4` binding, `5` safety.

---

## 10. Compilation output

```
CompiledScenario
├── compiled_hash: sha256 over (canonical spec + catalog version + adapter version)
├── graph: AuthorizationGraph        # nodes with derived ExpectedAuthority, edges
├── probe_matrices: [ProbeMatrix]    # one per PROBE/DEFERRED phase
├── plan: [PlanStep]                 # fully ordered, including auto-inserted SNAPSHOTs
├── policy_artifacts: [SynthesizedPolicy]   # session policies the compiler generated
└── warnings: [CompileWarning]       # downgraded invariants, informational expectations
```

`compiled_hash` goes into the evidence manifest. Two runs with different compiled hashes are
not directly comparable, and the analysis layer refuses to aggregate them without
`--allow-heterogeneous`.

---

## 11. Versioning policy

`apiVersion: chainbreak.dev/v1alpha1` — alpha means the schema may change with a minor
CHAINBREAK release. On change:

- The loader supports the previous alpha version for one minor release with a deprecation
  warning.
- `chainbreak scenario migrate` performs mechanical upgrades where possible.
- Evidence records the `apiVersion` it was produced under; analysis of an old bundle uses
  the rules that were current for it.

Promotion to `v1` requires: two consecutive releases with no schema change, all five
families implemented, and at least one completed real AWS experiment suite.
