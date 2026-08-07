# CHAINBREAK Capability Model

Why CHAINBREAK does not compare IAM action strings, and what it compares instead.
Code: `src/chainbreak/capabilities/`, catalog: `src/chainbreak/capabilities/catalog.yaml`.

---

## 1. The problem with action strings

`s3:GetObject` is not a unit of authority. It is a provider-specific token whose effect
depends on the resource ARN, the condition block, the bucket policy, the account boundary,
and whether the caller also holds `s3:ListBucket` (which changes the *error code* on a
missing key and therefore changes what the benchmark can conclude). Comparing sets of
action strings across delegation hops produces syntactically tidy, semantically meaningless
diffs — and it makes cross-provider comparison impossible, since
`Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read` has no textual
relationship to `s3:GetObject` despite meaning approximately the same thing.

CHAINBREAK therefore defines authority at the level of **what a workload can accomplish**.

---

## 2. Definition

A **Capability** is a named, provider-neutral ability to perform one *observable, benign,
verifiable* operation against a benchmark-owned resource class.

Three words carry weight:

- **Observable** — there must exist a probe whose outcome unambiguously distinguishes
  "permitted" from "denied". If you cannot test it, it is not a capability.
- **Benign** — the probe must be non-destructive to anything but benchmark scratch data.
- **Verifiable** — success must be confirmable, not merely "no exception raised".

```yaml
id: objectstore.read
title: Read a benchmark object
description: >
  Retrieve the content of a known benchmark marker object from the benchmark object store
  and confirm the returned bytes match the expected marker payload.
probe_kind: READ_MARKER
sensitivity: BENIGN_READ
idempotent: true
mutates_state: false
requires_precondition: [objectstore.marker_present]
```

## 3. The v0.1 catalog

Ten capabilities. The catalog is small on purpose: every capability multiplies the probe
matrix, which multiplies run time, cost, and the number of things that can be wrong.

| Capability ID | Probe kind | Mutates | Sensitivity | What it proves |
|---|---|---|---|---|
| `objectstore.read` | `READ_MARKER` | no | `BENIGN_READ` | Can retrieve a known marker object |
| `objectstore.write` | `WRITE_SCRATCH` | yes (scratch) | `BENIGN_WRITE` | Can create an object under the run's scratch prefix |
| `objectstore.list` | `LIST_PREFIX` | no | `BENIGN_READ` | Can enumerate the benchmark prefix |
| `keyvalue.read` | `READ_MARKER` | no | `BENIGN_READ` | Can read a known marker item |
| `keyvalue.write` | `WRITE_SCRATCH` | yes (scratch) | `BENIGN_WRITE` | Can put a scratch item |
| `function.invoke` | `INVOKE_NOOP` | no | `BENIGN_INVOKE` | Can synchronously invoke the no-op function |
| `queue.send` | `WRITE_SCRATCH` | yes (scratch) | `BENIGN_WRITE` | Can enqueue a benchmark message |
| `queue.receive` | `READ_MARKER` | no* | `BENIGN_READ` | Can dequeue from the benchmark queue |
| `identity.whoami` | `SELF_DESCRIBE` | no | `BENIGN_READ` | Can resolve its own identity |
| `identity.delegate` | `DELEGATE` | no | `DELEGATION` | Can assume the next-hop identity |

\* `queue.receive` changes message visibility. The AWS binding uses a dedicated probe queue
and `VisibilityTimeout=0` so the operation is effectively non-destructive; this is documented
in the binding rather than hidden.

Two capabilities deserve comment.

**`identity.delegate`** is the capability to hand authority onward. Treating delegation as a
first-class capability rather than as plumbing is what lets CHAINBREAK ask "did agent-c
retain the ability to delegate further, even though the hop only intended to grant read?" —
which is one of the more consequential real-world drift patterns.

**`identity.whoami`** is the control capability. It is granted to every identity in every
scenario. If a `whoami` probe fails, the problem is the benchmark or the network, not the
policy. It calibrates the run.

### Reserved namespaces

`objectstore.*`, `keyvalue.*`, `function.*`, `queue.*`, `identity.*` are reserved for the
core catalog. Community/extension capabilities must use `x-<vendor>.<name>`. Capability IDs
match `^[a-z][a-z0-9]*(\.[a-z][a-z0-9_]*)+$` and are stable identifiers: **renaming a
capability requires a catalog major version bump**, because evidence bundles reference them.

### Explicitly excluded from the default catalog

No `*.delete`, no `*.destroy`, no `iam.*` mutation, no `kms.decrypt`, no credential-issuing
capability beyond `identity.delegate`. A destructive capability would make the benchmark's
default posture unsafe for the marginal case where a probe targets the wrong resource. If a
future scenario needs one, it must be declared in a separate `dangerous` catalog file, be
opt-in via `--allow-dangerous-capabilities`, and pass an additional namespace assertion.

---

## 4. Provider bindings

The catalog knows nothing about AWS. Bindings live in the provider package.

```python
# src/chainbreak/providers/aws/bindings.py
ProviderCapabilityBinding(
    capability_id="objectstore.read",
    provider="aws",
    actions=["s3:GetObject"],
    resource_template="arn:aws:s3:::{bucket}/{namespace}/markers/marker.json",
    probe=S3ReadMarkerProbe,
    preconditions=[MarkerPresent("s3", "{namespace}/markers/marker.json")],
    disambiguation=S3ReadDisambiguation,  # see AWS_PROVIDER_SPEC §6
    notes="Requires marker precondition; 403 vs 404 is ambiguous without s3:ListBucket.",
)
```

### Binding rules (**INVARIANT CAP-2**)

1. **A binding declares its complete action set.** The probe may not invoke any provider
   action not listed in `actions`. Enforced at runtime by a botocore event hook that
   inspects each outbound API call during a probe and raises if the operation is not in the
   binding's allowlist. This is the technical mechanism behind "adapters cannot silently
   broaden scenario capabilities."
2. **A binding's resource template must expand to an ARN matching the namespace regex.**
   Checked before every call.
3. **A binding must declare its preconditions.** The executor verifies preconditions using
   the *provisioning* identity before the probe matrix runs. Failed precondition ⇒ the whole
   matrix is `CONFIGURATION_ERROR`, not a set of denials.
4. **Bindings are versioned with the adapter.** `adapter_version` appears in every evidence
   bundle, so a binding change invalidates comparison across runs and the analysis layer
   will say so.

### Mapping is many-to-many and that is fine

`objectstore.list` maps to `s3:ListBucket` with a `Condition` on `s3:prefix`. One capability,
one action, one condition. But `keyvalue.write` on DynamoDB maps to `dynamodb:PutItem` with
a `dynamodb:LeadingKeys` condition — and on a future Azure binding it would map to a
different action *and* a different resource shape. The capability is the invariant; the
binding absorbs the variation. When a provider genuinely cannot express a capability, the
binding is absent and any scenario using it fails to compile for that provider with a clear
message. Silent skipping is forbidden (**INVARIANT CAP-1**).

---

## 5. Capability sensitivity and the safety envelope

`Sensitivity` gates what a probe may do:

| Sensitivity | Permitted operations | Namespace assertion |
|---|---|---|
| `BENIGN_READ` | GET/HEAD/LIST on benchmark markers | required |
| `BENIGN_WRITE` | PUT/POST under `{namespace}/scratch/{run_id}/` only | required, run-scoped |
| `BENIGN_INVOKE` | Invoke the benchmark no-op function only | required |
| `DELEGATION` | AssumeRole targeting a benchmark role only | required |
| `DANGEROUS` | *(no capability in v0.1 uses this)* | required + explicit CLI opt-in |

`BENIGN_WRITE` probes write to a **run-scoped** prefix, which means (a) a run never
overwrites another run's data, (b) cleanup is a single prefix delete, and (c) cross-run
contamination (threat T-08) is structurally prevented rather than avoided by discipline.

---

## 6. Cross-provider comparison — and its honest limits

The capability layer makes cross-provider comparison *possible*. It does not make it
*valid*. Recorded in every future multi-provider report:

- Denial semantics differ. AWS distinguishes explicit deny from implicit deny in some
  messages; other providers may not. `DENIED_EXPLICIT` vs `DENIED_IMPLICIT` is therefore
  not comparable across providers, only `DENIED_*` in aggregate is.
- Consistency models differ. A revocation interval measured on AWS says nothing about Azure.
- Capability granularity differs. One provider's single action may be another's three.
- Probe cost and latency differ, which affects polling resolution and therefore uncertainty.

[RESEARCH_METHODOLOGY.md §9](RESEARCH_METHODOLOGY.md#9-threats-to-validity) treats this as a
named threat to external validity. v0.1 makes no cross-provider claims because v0.1 has one
provider.

---

## 7. Adding a capability

1. Add the entry to `catalog.yaml` with a rationale comment and bump the catalog `version`.
2. Add a binding in every provider package, or explicitly record the capability as
   unsupported for that provider.
3. Implement the probe class, including its disambiguation logic.
4. Add a provider-contract test asserting allow and deny both classify correctly.
5. Add a fake-provider binding so integration tests can use it.
6. Update this document's table.

Steps 4 and 5 are not optional. A capability without a deterministic-fake binding cannot be
exercised in CI, and an untested probe is a source of silently wrong findings.
