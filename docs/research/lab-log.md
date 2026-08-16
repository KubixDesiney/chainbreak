# CHAINBREAK Lab Log

The human-readable counterpart to the evidence bundles. Every experiment block appends an
entry. Exclusions are recorded **with reasons** — that is the single most important honesty
mechanism in the protocol, and a suite whose exclusions are undocumented is not publishable.

Format per [EXPERIMENT_PROTOCOL §8](../../EXPERIMENT_PROTOCOL.md#8-lab-log).

---

## Approved M17 schedule — 2026-08-16

The operator approved the M17 schedule in this task. Planned windows are deliberately
separated by clock hour so timing trials are not treated as one contiguous sample:

- block-01: 2026-08-16 10:00–11:30 UTC
- block-02: 2026-08-16 16:00–17:30 UTC
- block-03: 2026-08-17 10:00–11:30 UTC

Each block must complete the nine-item checklist, run all five families and all six negative
controls on the same applied sandbox, log every exclusion with run ID and reason, and destroy
and verify-clean before the next block. The schedule is not evidence of execution; only the
entries below are.

## 2026-08-16 block-01 — checklist recorded before execution

checklist: 0.1 pass (clean commit `1c934ea`); 0.2 pass (`1767 passed, 9 skipped, 28 deselected`); 0.3 pass (live P1–P11); 0.4 pass (`infra status` current); 0.5 pass (live preconditions); 0.6 pass (live validation gate; CLI did not emit a numeric offset); 0.7 pass (pre-apply verify-clean: nothing remaining); 0.8 pass (namespace lock available); 0.9 recorded (budget guardrail resource active; CLI exposes no `--check-budget` option)
infrastructure: applied 09:37 UTC, 44 resources, fingerprint `sha256:e09c7cda85ffceb170041addaf9684dc8cc6aea3482d5c0ad6da703836b2c97f`, namespace `cb-ec11b3c2`, region `eu-west-3`
adapter/catalog: adapter `0.1.0`, catalog `1.0.0`, local commit `1c934ea` (clean before execution)
scenarios: pending execution; all five families and six negative controls required in this block
runs: pending
negative controls: pending
exclusions: none at checklist time
observation: pending
anomalies: none at checklist time
notes: execution begins after this checklist is committed; any DETECTOR_FAILURE invalidates this block.

block outcome: invalid before scenario completion; no result published.
exclusions: run `01M04VMT6DFQ98E8NCABXEFVK9` excluded, reason `SecretLeakError` at `$.outcome.message_redacted` (`base64_blob`) caused by raw AWS ARN text reaching the evidence gate before provider-side identifier redaction. This was an apparatus evidence-boundary defect; no provider measurement was inferred. Sandbox destroy completed (`44 destroyed`), exact verify-clean passed, second destroy was a no-op, and second verify-clean passed.

## 2026-08-16 block-01R — checklist recorded before retry

checklist: 0.1 pass (clean commit `cc656e8`); 0.2 pass (offline gate previously `1767 passed, 9 skipped, 28 deselected`, redaction regression `25 passed`); 0.3 pass (live P1–P11); 0.4 pass (`infra status` current); 0.5 pass (live preconditions); 0.6 pass (live validation gate; CLI did not emit a numeric offset); 0.7 pass (pre-apply verify-clean: nothing remaining); 0.8 pass (namespace lock available); 0.9 recorded (budget guardrail resource active; CLI exposes no `--check-budget` option)
infrastructure: applied 09:44 UTC, 44 resources, fingerprint `sha256:e09c7cda85ffceb170041addaf9684dc8cc6aea3482d5c0ad6da703836b2c97f`, namespace `cb-ec11b3c2`, region `eu-west-3`
adapter/catalog: adapter `0.1.0`, catalog `1.0.0`, local commit `cc656e8` (clean before execution)
scenarios: pending execution; all five families and six negative controls required in this retry block
runs: pending
negative controls: pending
exclusions: prior invalid run `01M04VMT6DFQ98E8NCABXEFVK9` excluded above; no exclusions in this retry yet
observation: pending
anomalies: provider-identifier redaction fix under test
notes: execution begins after this checklist is committed; any DETECTOR_FAILURE invalidates this retry block.

block outcome: invalidated before completing the matrix; no result published.
exclusions: run `01M04WD549F85R9CAH00BRGA72` excluded, reason `AccessDenied` during `AssumeRole` from fixed `agent-a` directly to `agent-c`; the original stale-authority scenario omitted the required adjacent `agent-b` hop. The scenario was corrected and revalidated offline; this block is restarted so pre-fix and post-fix evidence are not mixed. Sandbox destroy completed (`44 destroyed`) and exact verify-clean passed.

## No experiments have been run

As of the current commit, CHAINBREAK's architecture and specifications are complete and the
domain model, capability catalog and scenario corpus are implemented and verified. **No
scenario has been executed against AWS, and no measurement exists.**

The first entry in this file will be written during milestone M17.

---

## Template

```
## YYYY-MM-DD block-NN
checklist:            0.1-0.9 pass | note any that failed and what was done
infrastructure:       applied HH:MM UTC, fingerprint sha256:…, negative controls enabled
adapter/catalog:      adapter 0.1.0, catalog 1.0.0, chainbreak 0.1.0, commit abc1234 (clean)
scenarios:            <path> v<version>, …
runs:                 <run-id>, …
negative controls:    nc-… -> DETECTOR_OK | DETECTOR_FAILURE
exclusions:           run <id> trial <n> excluded, reason …
observation:          <measured value with n, interval, mechanism, region>
anomalies:            …
notes:                block window; next block scheduled (control C-7 requires >= 3 blocks)
```

## Rules

- One entry per block, written at the time, not reconstructed afterwards.
- Record the checklist result even when everything passed.
- Record every exclusion, with its reason and the run ID.
- A block containing a `DETECTOR_FAILURE` is unvalidated. Record it, and do not publish any
  result from it.
- State observations in measurement language: "authorization remained effective for X–Y s
  after the mutation request, mechanism M, n=k". Not "revocation is slow".
