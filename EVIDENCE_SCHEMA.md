# CHAINBREAK Evidence Schema

**Bundle format version:** `1`
**JSON Schemas:** [`schemas/`](schemas/)
**Code:** `src/chainbreak/evidence/`

> Every JSON example below is an **illustration of the format**. The values are invented to
> show field shapes; none is a measurement. See [PROJECT_STATUS.md](PROJECT_STATUS.md).

Evidence is the product. Reports are a rendering of evidence; findings are a function of
evidence. If evidence is wrong, incomplete, or unverifiable, nothing downstream is worth
anything.

---

## 1. Bundle layout

```
runs/<run_id>/
├── manifest.json          # identity, integrity, provenance, versions
├── environment.json       # host, tool versions, clock calibration, provider environment
├── scenario.json          # the compiled scenario (spec + derived graph + compiled_hash)
├── graph.json             # authorization graph with expected + observed authority
├── observations.jsonl     # one record per probe attempt        (append-only)
├── events.jsonl           # delegations, mutations, waits, task outcomes (append-only)
├── policy_states.jsonl    # policy fingerprints at each snapshot (append-only)
├── credentials.jsonl      # credential metadata, no secrets     (append-only)
├── findings.json          # produced by `analyze`, not by `run`
├── scores.json            # produced by `analyze`
└── logs/
    └── run.log            # redacted structured log
```

Two properties are structural, not conventional:

- **`.jsonl` files are append-only and written during the run**, so an aborted run still
  yields usable partial evidence. A crash mid-experiment is a data point, not a data loss.
- **`findings.json` is written by `analyze`, never by `run`.** You can delete it and
  regenerate it. You cannot regenerate `observations.jsonl`. This separation is
  [ADR-006](docs/adr/ADR-006-observation-separated-from-conclusion.md) made physical.

---

## 2. `manifest.json`

```json
{
  "bundle_format_version": 1,
  "run_id": "01J8XKQ4V7ZP3N2M9YB6TCFR5A",
  "created_at": "2026-08-07T14:19:58.114233Z",
  "completed_at": "2026-08-07T14:27:11.902004Z",
  "status": "COMPLETED",
  "block_id": null,

  "scenario": {
    "id": "delegation-drift-four-hop",
    "version": "1.2.0",
    "family": "delegation-drift",
    "api_version": "chainbreak.dev/v1alpha1",
    "compiled_hash": "sha256:6f1c…"
  },

  "provenance": {
    "chainbreak_version": "0.1.0a0",
    "git_commit": "9d4a2c1f…",
    "git_dirty": false,
    "capability_catalog_version": "1.0.0",
    "provider": "aws",
    "provider_adapter_version": "0.1.0",
    "python_version": "3.12.4",
    "config_fingerprint": "sha256:be07…",
    "infrastructure_fingerprint": "sha256:11ab…"
  },

  "integrity": {
    "algorithm": "sha256",
    "artifacts": {
      "observations.jsonl": "sha256:…",
      "events.jsonl": "sha256:…",
      "policy_states.jsonl": "sha256:…",
      "credentials.jsonl": "sha256:…",
      "graph.json": "sha256:…",
      "scenario.json": "sha256:…",
      "environment.json": "sha256:…"
    },
    "root": "sha256:…",
    "sealed_at": "2026-08-07T14:27:12.004411Z"
  },

  "redaction": {
    "policy_version": "1.0.0",
    "rules_applied": ["secret_patterns", "arn_account", "session_names", "policy_bodies"],
    "account_id_treatment": "hashed",
    "violations_detected": 0
  },

  "counts": {
    "observations": 168, "events": 27, "policy_snapshots": 8, "credentials": 4
  },

  "warnings": []
}
```

`run_id` is a ULID: lexicographically sortable by creation time, collision-resistant,
URL-safe, and it does not leak a hostname or MAC address the way UUIDv1 does.

`infrastructure_fingerprint` is a hash over the Terraform output values (post-redaction),
so evidence records *which* infrastructure produced it without recording the ARNs.

`block_id` mirrors the field of the same name on `ExperimentRun` and on the SQLite index's
`runs` table, added at M6 for schema symmetry. It is `null` until the orchestrator (M10+) and
control C-7's block randomization (M17, EXPERIMENT_PROTOCOL.md section 0) exist to set it.

---

## 3. `observations.jsonl`

One record per probe attempt. The atom of the entire system.

```json
{
  "observation_id": "obs_01J8XKQ5C2…",
  "run_id": "01J8XKQ4V7ZP3N2M9YB6TCFR5A",
  "sequence": 42,
  "phase": "after-delegation",
  "probe_matrix_id": "pm_02",
  "identity_id": "agent-b",
  "identity_ref_hash": "sha256:2c9f…",
  "capability_id": "keyvalue.read",
  "trial": 1,
  "trial_count": 3,

  "credential_id": "cred_01J8XKQ4Z…",
  "credential_age_ms": 8421,

  "request": {
    "probe_kind": "READ_MARKER",
    "binding_actions": ["dynamodb:GetItem"],
    "target_ref_hash": "sha256:7a10…",
    "target_namespace": "cb-01j8xkq4",
    "parameters_fingerprint": "sha256:44de…"
  },

  "timing": {
    "monotonic_start_ns": 918273645000,
    "monotonic_end_ns": 918315201000,
    "duration_ms": 41.556,
    "wall_start": "2026-08-07T14:21:03.418772Z",
    "clock_offset_ms": -3.2,
    "attempt_number": 1,
    "retries": 0
  },

  "outcome": {
    "class": "DENIED_EXPLICIT",
    "provider_status_code": 400,
    "provider_error_code": "AccessDeniedException",
    "denial_attribution": "EXPLICIT_DENY",
    "disambiguation_path": "dynamodb.access_denied.explicit",
    "message_digest": "sha256:c1b8…",
    "message_redacted": "User: <REDACTED_ARN> is not authorized to perform: dynamodb:GetItem on resource: <REDACTED_ARN> with an explicit deny in an identity-based policy",
    "request_id_hash": "sha256:9f02…"
  },

  "quality": {
    "preconditions_verified": true,
    "classified": true,
    "notes": []
  }
}
```

Design notes worth defending:

- **`message_redacted` keeps structure, drops identifiers.** The sentence shape is what
  carries the `EXPLICIT_DENY` attribution, and losing it would destroy the ability to
  distinguish explicit from implicit denial. So the redactor replaces ARNs in place rather
  than dropping the field. `message_digest` is over the *original* message, so two runs can
  be compared for message-identity without either storing the original.
- **`disambiguation_path`** names the exact branch of the classification logic that fired.
  When a classification is later found to be wrong, every affected observation is findable
  by path, and re-analysis can correct historical bundles.
- **`clock_offset_ms`** is the measured local-vs-provider clock offset at the time of the
  probe (see [§7](#7-clock-calibration)). Timing findings that depend on wall-clock
  correlation carry this forward into their uncertainty.
- **No raw ARNs anywhere.** `identity_ref_hash` and `target_ref_hash` are salted with a
  per-run salt derived from `run_id`, so within a bundle you can tell "same target" without
  the bundle disclosing which target, and across bundles the hashes do not correlate.

---

## 4. `events.jsonl`

Everything that is not a probe.

```json
{"event_id":"ev_…","sequence":7,"kind":"DELEGATION_ISSUED","phase":"after-delegation",
 "edge_id":"hop-2","source_identity":"agent-a","target_identity":"agent-b",
 "mechanism":"SESSION_POLICY_SCOPED",
 "requested_capabilities":["objectstore.read","keyvalue.read"],
 "session_policy_fingerprint":"sha256:…","credential_id":"cred_…",
 "requested_lifetime_s":900,"granted_lifetime_s":900,
 "timing":{"monotonic_ns":918100000000,"wall":"2026-08-07T14:21:01.002Z","duration_ms":212.4},
 "outcome":"SUCCESS"}

{"event_id":"ev_…","sequence":18,"kind":"POLICY_MUTATION_APPLIED","phase":"revoke",
 "mutation_kind":"ATTACH_INLINE_DENY","target_identity":"agent-b",
 "policy_before_fingerprint":"sha256:…","policy_after_fingerprint":"sha256:…",
 "denies_capabilities":["objectstore.read"],
 "timing":{"monotonic_ns":919400000000,"wall":"2026-08-07T14:22:14.771Z","duration_ms":186.0},
 "receipt":{"confirmed":true,"confirmation_method":"read_after_write",
            "confirmation_latency_ms":412.7,"provider_request_id_hash":"sha256:…"},
 "outcome":"SUCCESS"}
```

Event kinds: `RUN_STARTED`, `PREFLIGHT_COMPLETED`, `PHASE_STARTED`, `PHASE_COMPLETED`,
`DELEGATION_ISSUED`, `DELEGATION_FAILED`, `POLICY_SNAPSHOT_TAKEN`, `POLICY_MUTATION_REQUESTED`,
`POLICY_MUTATION_APPLIED`, `WAIT_STARTED`, `WAIT_COMPLETED`, `TASK_STARTED`, `TASK_COMPLETED`,
`CREDENTIAL_ISSUED`, `CREDENTIAL_EXPIRED_OBSERVED`, `SAFETY_ASSERTION`, `RUN_ABORTED`,
`RUN_COMPLETED`.

**`POLICY_MUTATION_APPLIED.receipt` is the anchor `t_M` for every revocation measurement.**
`confirmed: true` means the control plane acknowledged *and* a read-after-write confirmed the
new document. `confirmation_method` distinguishes `read_after_write` from
`api_ack_only`; the latter widens the reported uncertainty because the write may not have
settled. An unconfirmed mutation makes the resulting timing measurement `INCONCLUSIVE`.

---

## 5. `credentials.jsonl` — metadata only

```json
{"credential_id":"cred_01J8XKQ4Z…","edge_id":"hop-2","identity_id":"agent-b",
 "mechanism":"SESSION_POLICY_SCOPED",
 "issued_at":"2026-08-07T14:21:01.214Z","expires_at":"2026-08-07T14:36:01.000Z",
 "requested_duration_s":900,"granted_duration_s":900,"lifetime_capped":false,
 "session_name_hash":"sha256:…","access_key_id_hash":"sha256:…",
 "session_policy_fingerprint":"sha256:…","scope_capabilities":["objectstore.read","keyvalue.read"]}
```

**INVARIANT EV-1 — no secret material, ever.** Not the secret access key, not the session
token, not a truncation of either, not an encrypted copy. `access_key_id_hash` is a salted
hash of the *public* key ID and exists solely so observations can be correlated to the
credential that produced them.

Enforcement is structural, not procedural:

1. The `Credential` domain object stores secrets in a `SecretStr`-derived type whose
   `__repr__`, `__str__`, and Pydantic serializer all raise on serialization attempt.
2. Every record passes through `evidence.redaction.redact()` before it touches a file.
3. `redact()` applies a pattern scan (`(?:ASIA|AKIA)[0-9A-Z]{16}`, `aws_secret_access_key`,
   long base64 blobs, `x-amz-security-token`, PEM markers, JWT shapes) and **raises
   `SecretLeakError`** on a hit, aborting the run rather than writing a redacted
   approximation. A leak is a bug to fix, not a value to sanitize.
4. `tests/unit/test_redaction.py` fuzzes every domain model with synthetic secret values and
   asserts none reach a serialized bundle. This test is a merge gate.

---

## 6. `graph.json`

The compiled graph plus results, in one document, so a report can be produced from a single
file for quick inspection.

```json
{
  "nodes": [
    {"identity_id":"agent-b","hop_index":2,"parent":"agent-a",
     "expected_authority":{"capabilities":["keyvalue.read","objectstore.read"],
                           "derivation":"INHERITED_ATTENUATED","phase":"after-delegation"},
     "observed_authority":{"capabilities":["objectstore.read"],
                           "excluded":{"queue.send":"NO_BINDING_IN_SCENARIO"},
                           "coverage":1.0,"probe_matrix_id":"pm_02","phase":"after-delegation"},
     "divergence":{"unexpected_gain":[],"unexpected_loss":["keyvalue.read"],
                   "drift_class":null}}
  ],
  "edges": [
    {"edge_id":"hop-2","from":"agent-a","to":"agent-b","mechanism":"SESSION_POLICY_SCOPED",
     "intended_capabilities":["objectstore.read","keyvalue.read"],
     "expected_effective":["objectstore.read","keyvalue.read"],
     "attenuation_correct":false,
     "survived_incorrectly":[],"dropped_incorrectly":["keyvalue.read"]}
  ],
  "paths":[{"path":["principal","agent-a","agent-b","agent-c","agent-d"],
            "first_divergence":{"hop_index":2,"kind":"NARROWING"},
            "attenuation_monotone_set":true,"attenuation_monotone_cardinality":true}]
}
```

Capability arrays are **always sorted** so the file is diffable across runs.

---

## 7. Clock calibration — `environment.json`

```json
{
  "host": {"os":"Linux-6.8.0","arch":"x86_64","python":"3.12.4","container":true,
           "hostname_hash":"sha256:…"},
  "tooling": {"terraform":"1.9.2","boto3":"1.34.140","botocore":"1.34.140"},
  "clock": {
    "source":"time.monotonic_ns + time.time",
    "calibration_samples":5,
    "provider_offset_ms":{"mean":-3.2,"stdev":1.4,"min":-5.1,"max":-1.8},
    "offset_method":"http_date_header_midpoint",
    "max_tolerated_offset_ms":1000,
    "within_tolerance":true
  },
  "network": {"rtt_ms":{"p50":21.4,"p95":38.9,"samples":20}},
  "provider_environment": {
    "provider":"aws","region_hash":"sha256:…","account_id_hash":"sha256:…",
    "partition":"aws","namespace":"cb-01j8xkq4",
    "caller_identity_kind":"assumed-role","credential_source":"env"
  }
}
```

The offset is estimated from the provider's HTTP `Date` header using the request-midpoint
method (`offset = server_time − (t_send + t_recv)/2`), sampled five times, median taken. It
is **not** used to adjust measurements — all interval math is monotonic and local. It is
recorded so that correlating a CHAINBREAK observation with a provider-side log entry (e.g.
CloudTrail) has a stated error bound. If `|offset| > max_tolerated_offset_ms`, timing
findings are downgraded to `LOW` confidence automatically.

---

## 8. `findings.json`

```json
{
  "analysis": {"chainbreak_version":"0.1.0a0","analyzer_version":"1.0.0",
               "analyzed_at":"2026-08-07T14:28:03Z","bundle_root_verified":true},
  "findings":[
    {"finding_id":"fnd_01…","type":"AUTHORITY_EXPANSION","severity_hint":"REVIEW",
     "confidence":"HIGH",
     "subject":{"kind":"identity","identity_id":"agent-c","hop_index":3},
     "observation":"agent-c returned ALLOWED for keyvalue.read in all 3 trials at phase after-delegation",
     "expected_state":{"capabilities":["objectstore.read"]},
     "observed_state":{"capabilities":["objectstore.read","keyvalue.read"]},
     "delta":{"unexpected_gain":["keyvalue.read"],"unexpected_loss":[]},
     "security_interpretation":"Agent C holds authority that hop-3 did not delegate. If hop-3's session policy is the intended control boundary, this represents a failure of that boundary. Determine whether the capability originates from the role's own permission policy rather than the delegated scope.",
     "evidence":{"observation_refs":["obs_…","obs_…","obs_…"],
                 "event_refs":["ev_…"],"policy_state_refs":["ps_…"]},
     "confidence_rationale":"coverage=1.0; 3/3 trials unanimous; no ERROR outcomes; policy snapshots succeeded before and after",
     "caveats":["Single run; not repeated across sessions."]}
  ],
  "detector_checks":[
    {"negative_control":"nc-expansion-hop3","expected":"AUTHORITY_EXPANSION","produced":true,"result":"DETECTOR_OK"}
  ]
}
```

`observation`, `expected_state`, `observed_state`, and `security_interpretation` are separate
fields, and the reporting layer renders them in that order under separate headings. Merging
them into a single prose blob is how benchmarks end up overclaiming.

`severity_hint` is deliberately named *hint*: CHAINBREAK does not know the operator's risk
context and will not assign a CVSS-like severity. Values: `INFORMATIONAL`, `REVIEW`,
`INVESTIGATE`.

---

## 9. SQLite run index

Local index for `chainbreak runs list|show` and cross-run analysis. It is a **cache derived
from bundles**, never the source of truth. `chainbreak runs reindex` rebuilds it from disk.

```sql
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, completed_at TEXT,
  status TEXT NOT NULL, scenario_id TEXT NOT NULL, scenario_version TEXT NOT NULL,
  family TEXT NOT NULL, provider TEXT NOT NULL, adapter_version TEXT NOT NULL,
  chainbreak_version TEXT NOT NULL, git_commit TEXT, compiled_hash TEXT NOT NULL,
  config_fingerprint TEXT NOT NULL, bundle_path TEXT NOT NULL,
  bundle_root TEXT NOT NULL, sealed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE findings (
  finding_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
  type TEXT NOT NULL, confidence TEXT NOT NULL, severity_hint TEXT NOT NULL,
  identity_id TEXT, hop_index INTEGER, capabilities_json TEXT NOT NULL
);
CREATE TABLE measurements (          -- numeric results for cross-run comparison
  run_id TEXT NOT NULL REFERENCES runs(run_id), metric TEXT NOT NULL,
  identity_id TEXT, capability_id TEXT,
  value_low REAL, value_point REAL, value_high REAL, unit TEXT NOT NULL,
  confidence TEXT NOT NULL, PRIMARY KEY (run_id, metric, identity_id, capability_id)
);
CREATE INDEX idx_runs_scenario ON runs(scenario_id, created_at);
CREATE INDEX idx_findings_type ON findings(type, confidence);
CREATE INDEX idx_measurements_metric ON measurements(metric);
```

`measurements` stores every timing result as a **triple** (`low`, `point`, `high`). There is
no column for a bare scalar, because there is no such thing as a bare scalar in this
benchmark.

---

## 10. Sealing and verification

On completion the writer computes SHA-256 per artifact, then a root over the sorted
`name:hash` pairs. `chainbreak analyze` recomputes and compares. Mismatch ⇒ refuse to
produce findings unless `--allow-unsealed`, and in that case every finding is stamped
`bundle_root_verified: false`.

This is tamper-*evidence*, not tamper-*proofing* — an operator who edits a bundle can
recompute the root. It defends against accidental corruption and makes deliberate
falsification require deliberate effort, which is the appropriate bar for a
self-administered benchmark. Optional detached signing (`cosign`/`minisign`) is deferred to
v0.2; the manifest already reserves a `signatures` key.

---

## 11. Publishing a bundle

Bundles are gitignored by default. `chainbreak evidence export <run> --public` produces a
review-ready copy and, before writing, asserts: redaction violations = 0, no unhashed
account ID, no ARN, no policy document unless explicitly opted in, no hostname, and no
session name in cleartext. It prints a diff summary of what it stripped so the operator
sees exactly what is leaving their machine.
