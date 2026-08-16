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
- block-02-now: 2026-08-16 12:55–14:25 UTC (rescheduled here with operator approval)
- block-03: 2026-08-16 16:00–17:30 UTC
- block-04: 2026-08-17 10:00–11:30 UTC

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

## 2026-08-16 block-01R2 — checklist recorded before clean restart

checklist: 0.1 pass (clean commit `2fe0755`); 0.2 pass (`1767 passed, 9 skipped, 28 deselected`, plus scenario/compiler validation `60 passed`); 0.3 pass (live P1–P11); 0.4 pass (`infra status` current); 0.5 pass (live preconditions); 0.6 pass (live validation gate; CLI did not emit a numeric offset); 0.7 pass (pre-apply verify-clean: nothing remaining); 0.8 pass (namespace lock available); 0.9 recorded (budget guardrail resource active; CLI exposes no `--check-budget` option)
infrastructure: applied 09:57 UTC, 44 resources, fingerprint `sha256:e09c7cda85ffceb170041addaf9684dc8cc6aea3482d5c0ad6da703836b2c97f`, namespace `cb-ec11b3c2`, region `eu-west-3`; destroyed after invalidation, exact verify-clean passed twice
adapter/catalog: adapter `0.1.0`, catalog `1.0.0`, local commit `2fe0755` (clean before execution)
scenarios: positive set-valued runs began, but the matrix stopped during revocation before all five families and six negative controls were executed
runs: completed before invalidation — `01M04WRQYD99W3WSJSKM151D3A`, `01M04WSQ9Q89MJQ8CY2NKCJFSN`, `01M04WV9YWF657F34N0MBEA3M4`, `01M04WWSGFE4KGHX4FPX3F3VHV`, `01M04WYC8Y4Q37RHKKPGG26NGB`, `01M04X065H1XRT7QQFHYYJA4M5`, `01M04X1D7P2V0RY83T0ZXENJ7P`, `01M04X2DVYECV8KA3TCN7723H4`, `01M04X2Z138XTKMM404GT12QHG`, `01M04X3Z265K5X4STT809NC2E9`; partial runs `01M04X5S8346NGHFDXBPYQKGJR`, `01M04XDE1D9CA00AHPQ56QV2KZ`
negative controls: not run; block invalidated before controls
exclusions: prior invalid runs `01M04VMT6DFQ98E8NCABXEFVK9`, `01M04WD549F85R9CAH00BRGA72` excluded above; all block-01R2 runs excluded from publication because the block matrix was incomplete; partial runs `01M04X5S8346NGHFDXBPYQKGJR` and `01M04XDE1D9CA00AHPQ56QV2KZ` excluded for automatic-revert `MalformedPolicyDocumentException` (duplicate statement IDs)
observation: none publishable; no timing estimate or family result is inferred from this invalid block
anomalies: explained adapter defect found in AWS inline-policy reversion — multi-capability grant synthesis emitted duplicate `CbGrant` SIDs; fixed in the follow-up commit and covered by a regression test; this was not an unexplained provider defect
notes: block invalidated and sandbox destroyed; the next execution requires a new nine-item checklist on the fixed clean commit.

## 2026-08-16 block-01R3 — checklist recorded before clean execution

checklist: 0.1 pass (clean commit `be27feb`; full offline gate `1773 passed, 33 skipped`); 0.2 pass (focused AWS mutation regression `73 passed`, Ruff clean); 0.3 pass (live P1–P11 at 10:19 UTC); 0.4 pass (`infra status` current); 0.5 pass (live preconditions); 0.6 pass (live validation gate); 0.7 pass (pre-apply exact verify-clean at 10:14 UTC: nothing remaining; the post-apply diagnostic is expected to report applied resources); 0.8 pass (namespace lock available); 0.9 recorded (budget guardrail resource active; CLI exposes no `--check-budget` option)
infrastructure: applied 10:18 UTC, 44 resources, fingerprint `sha256:e09c7cda85ffceb170041addaf9684dc8cc6aea3482d5c0ad6da703836b2c97f`, namespace `cb-ec11b3c2`, region `eu-west-3`
adapter/catalog: adapter `0.1.0`, catalog `1.0.0`, chainbreak `0.1.0a0`, local commit `be27feb` (clean before execution)
sampling plan: set-valued families n=3 per scenario; timing families use two independent runs in this block, two in block-02, and one in block-03, with all timing runs recorded by block ID (aggregate n=5 across three windows)
scenarios: all five families and six negative controls required in this block; positive runs pending
runs: pending
negative controls: pending
exclusions: none at checklist time
observation: pending
anomalies: none at checklist time
notes: execution begins after this checklist is committed; any DETECTOR_FAILURE invalidates this block.

block outcome: invalid/incomplete; no result published. The operator interruption stopped the
matrix during delegation-drift and the approved block-01 window elapsed before resumption.
runs: completed `01M04Y0PHQBPW0XTS6GFEWBMV8` (scope attenuation), `01M04Y3ZWQ5HQRHPGHGBZNMSB0` (delegation-drift five-hop), `01M04Y6H295K1E0S2CB6M1X29P` (delegation-drift four-hop), and resumed `01M059VX8KCJ79SW24QHSZEZ5G` (delegation-drift role-chain-five-hop)
exclusions: partial run `01M04Y9JKZ8DFSN0GJS21TNY5J` excluded, reason `operator_interruption` before evidence or mutation; all completed block-01R3 runs excluded from publication because the five-family/six-control matrix was incomplete and the window boundary was crossed
negative controls: not run
observation: none publishable; no timing estimate or family result is inferred from this incomplete block
anomalies: none observed; sandbox destroy completed (`44 destroyed`), exact verify-clean passed, second destroy was a no-op, and second verify-clean passed.
notes: next attempt must use the separately scheduled block-02 window.

## 2026-08-16 block-02-now — checklist recorded before clean execution

checklist: 0.1 pass (clean commit `6adb4f4`; prior full offline gate `1773 passed, 33 skipped`); 0.2 pass (adapter regression `73 passed`, Ruff clean); 0.3 pass (live P1–P11 at 12:55 UTC); 0.4 pass (`infra status` current); 0.5 pass (live preconditions); 0.6 pass (live validation gate); 0.7 pass (pre-apply exact verify-clean at 12:51 UTC: nothing remaining); 0.8 pass (namespace lock available); 0.9 recorded (budget guardrail resource active; CLI exposes no `--check-budget` option)
infrastructure: applied 12:54 UTC, 44 resources, fingerprint `sha256:e09c7cda85ffceb170041addaf9684dc8cc6aea3482d5c0ad6da703836b2c97f`, namespace `cb-ec11b3c2`, region `eu-west-3`
adapter/catalog: adapter `0.1.0`, catalog `1.0.0`, chainbreak `0.1.0a0`, local commit `6adb4f4` (clean before execution)
sampling plan: set-valued families n=3 per scenario; timing families use two independent runs in this window, two in block-03, and one in block-04, with all timing runs recorded by block ID (aggregate n=5 across three valid windows)
scenarios: all five families and six negative controls required in this block; positive runs pending
runs: pending
negative controls: pending
exclusions: none at checklist time
observation: pending
anomalies: none at checklist time
notes: execution begins after this checklist is committed; any DETECTOR_FAILURE invalidates this block.

block outcome: invalid/incomplete; no result published. The first revocation timing pass reached
`trust-policy-null-condition.yaml` and the adapter emitted an invalid trust-policy Deny without
`Principal`; AWS returned `MalformedPolicyDocumentException` before the mutation was applied.
runs: completed before failure — `01M05A992C67BFGYQEN7DEV4M1` (scope attenuation), `01M05AAFQH0T2XDXE3FXT0CCGD` (delegation-drift five-hop), `01M05ACHF91NDQA96RSM06F2XP` (delegation-drift four-hop), `01M05AEK5FDE9Z543JH6WZRCGP` (delegation-drift role-chain-five-hop), `01M05AGTNC57NBH0GBBWVP3TFY` (delegation-drift six-hop), `01M05AK3CT464GK6680XGG31RF` (delegation-drift three-hop), `01M05AMPFJ16E7FS9ABMJA7P28` (delegation-drift two-hop), `01M05AP72G7A6QSAZA27T4EDF0` (silent-narrowing full-authority), `01M05APXVB0J1XFD23GZ1V8FT8` (silent-narrowing), `01M05ARPN2A75WRSZ6H4V8KRP0` (revocation delete-session-scope), `01M05AVC997Z6BJB5FMV9357ZQ` (revocation inline-deny), `01M05AWSCN0KBZ906T24Z70QZ` (revocation remove-policy), `01M05B120B9SYRH844PPENARM5` (revocation revoke-older-sessions); partial run `01M05B2D0H5Z5FBRSGTAFN9ZVA` (trust-policy-null-condition)
negative controls: not run; block stopped before controls
exclusions: partial run `01M05B2D0H5Z5FBRSGTAFN9ZVA` excluded, reason `MalformedPolicyDocumentException` because the adapter omitted required trust-policy `Principal`; all block-02-now runs excluded from publication because the five-family/two-pass timing/six-control matrix was incomplete
observation: none publishable; no timing estimate or family result is inferred from this invalid block
anomalies: explained adapter defect; fixed in the follow-up commit by adding `Principal: {"AWS": "*"}` and a regression assertion; not an unexplained provider defect
notes: sandbox destroy completed (`44 destroyed`), exact verify-clean passed, second destroy was a no-op, and second verify-clean passed.

## No valid M17 block has been published

Invalid and incomplete AWS executions are recorded above with their run IDs and reasons.
**No valid M17 block has produced a publishable measurement.**

The next valid block must satisfy the complete family/control matrix and the timing/sample
requirements before any result is published.

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
