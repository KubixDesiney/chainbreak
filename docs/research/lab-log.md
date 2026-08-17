# CHAINBREAK Lab Log

**Status as of 2026-08-16:** historical apparatus evidence only. Every M17 entry below is
invalid, incomplete, or a pre-block guard failure; all are superseded/excluded and none yields a
valid or publishable block. Intermediate values in these entries are apparatus observations, not
measurements, and must not be used as results. The live namespace is represented everywhere in
this tracked log by the stable label `NAMESPACE_SCRUBBED`.

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

checklist: legacy pre-repair record; live budget gate was not yet implemented; no valid M17 result inferred.
infrastructure: applied 09:37 UTC, 44 resources, fingerprint `sha256:e09c7cda85ffceb170041addaf9684dc8cc6aea3482d5c0ad6da703836b2c97f`, namespace `NAMESPACE_SCRUBBED`, region `eu-west-3`
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

checklist: legacy pre-repair record; live budget gate was not yet implemented; no valid M17 result inferred.
infrastructure: applied 09:44 UTC, 44 resources, fingerprint `sha256:e09c7cda85ffceb170041addaf9684dc8cc6aea3482d5c0ad6da703836b2c97f`, namespace `NAMESPACE_SCRUBBED`, region `eu-west-3`
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

checklist: legacy pre-repair record; live budget gate was not yet implemented; no valid M17 result inferred.
infrastructure: applied 09:57 UTC, 44 resources, fingerprint `sha256:e09c7cda85ffceb170041addaf9684dc8cc6aea3482d5c0ad6da703836b2c97f`, namespace `NAMESPACE_SCRUBBED`, region `eu-west-3`; destroyed after invalidation, exact verify-clean passed twice
adapter/catalog: adapter `0.1.0`, catalog `1.0.0`, local commit `2fe0755` (clean before execution)
scenarios: positive set-valued runs began, but the matrix stopped during revocation before all five families and six negative controls were executed
runs: completed before invalidation — `01M04WRQYD99W3WSJSKM151D3A`, `01M04WSQ9Q89MJQ8CY2NKCJFSN`, `01M04WV9YWF657F34N0MBEA3M4`, `01M04WWSGFE4KGHX4FPX3F3VHV`, `01M04WYC8Y4Q37RHKKPGG26NGB`, `01M04X065H1XRT7QQFHYYJA4M5`, `01M04X1D7P2V0RY83T0ZXENJ7P`, `01M04X2DVYECV8KA3TCN7723H4`, `01M04X2Z138XTKMM404GT12QHG`, `01M04X3Z265K5X4STT809NC2E9`; partial runs `01M04X5S8346NGHFDXBPYQKGJR`, `01M04XDE1D9CA00AHPQ56QV2KZ`
negative controls: not run; block invalidated before controls
exclusions: prior invalid runs `01M04VMT6DFQ98E8NCABXEFVK9`, `01M04WD549F85R9CAH00BRGA72` excluded above; all block-01R2 runs excluded from publication because the block matrix was incomplete; partial runs `01M04X5S8346NGHFDXBPYQKGJR` and `01M04XDE1D9CA00AHPQ56QV2KZ` excluded for automatic-revert `MalformedPolicyDocumentException` (duplicate statement IDs)
observation: none publishable; no timing estimate or family result is inferred from this invalid block
anomalies: explained adapter defect found in AWS inline-policy reversion — multi-capability grant synthesis emitted duplicate `CbGrant` SIDs; fixed in the follow-up commit and covered by a regression test; this was not an unexplained provider defect
notes: block invalidated and sandbox destroyed; the next execution requires a new nine-item checklist on the fixed clean commit.

## 2026-08-16 block-01R3 — checklist recorded before clean execution

checklist: legacy pre-repair record; live budget gate was not yet implemented; no valid M17 result inferred.
infrastructure: applied 10:18 UTC, 44 resources, fingerprint `sha256:e09c7cda85ffceb170041addaf9684dc8cc6aea3482d5c0ad6da703836b2c97f`, namespace `NAMESPACE_SCRUBBED`, region `eu-west-3`
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

checklist: legacy pre-repair record; live budget gate was not yet implemented; no valid M17 result inferred.
infrastructure: applied 12:54 UTC, 44 resources, fingerprint `sha256:e09c7cda85ffceb170041addaf9684dc8cc6aea3482d5c0ad6da703836b2c97f`, namespace `NAMESPACE_SCRUBBED`, region `eu-west-3`
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

## 2026-08-16 block-02R — checklist recorded before clean replacement execution

checklist: legacy pre-repair record; live budget gate was not yet implemented; no valid M17 result inferred.
infrastructure: applied 13:14 UTC, 44 resources, fingerprint `sha256:e09c7cda85ffceb170041addaf9684dc8cc6aea3482d5c0ad6da703836b2c97f`, namespace `NAMESPACE_SCRUBBED`, region `eu-west-3`
adapter/catalog: adapter `0.1.0`, catalog `1.0.0`, chainbreak `0.1.0a0`, local commit `d96f4de` (clean before execution)
sampling plan: set-valued families n=3 per scenario; timing families use one independent run in this window, two in block-03, and two in block-04, with all timing runs recorded by block ID (aggregate n=5 across three valid windows)
scenarios: all five families and six negative controls required in this block; positive runs pending
runs: pending
negative controls: pending
exclusions: none at checklist time
observation: pending
anomalies: none at checklist time
notes: execution begins after this checklist is committed; any DETECTOR_FAILURE invalidates this block.

block outcome: invalid/incomplete; no result published. The positive families and revocation
pass completed until stale-authority began. Because `trust-policy-null-condition` had already
changed a role's future trust policy, the next stale-authority delegation was denied.
runs: completed before failure — `01M05BEMNP49E2QJJG1DVJP5NV`, `01M05BG26036YGH43GCFHTZ3PR`, `01M05BJF2H6JZ8H7S30DVRM0RF`, `01M05BMEMZC51WA6WH7MZWEM42`, `01M05BPMST84KJHH94VC6B5NF8`, `01M05BS5R1D58H3Z2Q2882MGTD`, `01M05BTQ16C63DPC1XS5J1B46C`, `01M05BVZGRFASJ0KK6J2C5YGKG`, `01M05BWNNT5DWDF93T6V47MPYG`, `01M05BYCB244BN6Z288ESYNN44`, `01M05C0TV90XG6GCAJ9XT88PPN`, `01M05C2B4RA4BEPKXM1RBDBD3T`, `01M05C5XPPC4TKESANSH5GSA69`, `01M05C7GMC0V9P7PQWC6ERGND4`; partial run `01M05CA5HH4B2C7RHAWEW5WZHG`
negative controls: not run; block stopped before controls
exclusions: partial run `01M05CA5HH4B2C7RHAWEW5WZHG` excluded, reason `AccessDenied` during stale-authority delegation after the earlier trust-policy mutation; all block-02R runs excluded because the family/control matrix was incomplete
observation: none publishable; no timing estimate or family result is inferred from this invalid block
anomalies: explained cross-scenario contamination; next block orders stale-authority before the trust-policy mutation, with trust-policy and negative controls last
notes: sandbox destroy completed (`44 destroyed`), exact verify-clean passed, second destroy was a no-op, and second verify-clean passed.

## 2026-08-16 block-02R2 — checklist recorded before reordered clean execution

checklist: legacy pre-repair record; live budget gate was not yet implemented; no valid M17 result inferred.
infrastructure: applied 13:34 UTC, 44 resources, fingerprint `sha256:e09c7cda85ffceb170041addaf9684dc8cc6aea3482d5c0ad6da703836b2c97f`, namespace `NAMESPACE_SCRUBBED`, region `eu-west-3`
adapter/catalog: adapter `0.1.0`, catalog `1.0.0`, chainbreak `0.1.0a0`, local commit `72a7b88` (clean before execution)
sampling plan: set-valued families n=3 per scenario; timing families use one independent run in this window, two in block-03, and two in block-04, with all timing runs recorded by block ID (aggregate n=5 across three valid windows)
execution order: set-valued families, stale-authority timing, revocation timing with trust-policy last, then all six negative controls
scenarios: all five families and six negative controls required in this block; positive runs pending
runs: pending
negative controls: pending
exclusions: none at checklist time
observation: pending
anomalies: none at checklist time
notes: execution begins after this checklist is committed; any DETECTOR_FAILURE invalidates this block.

block outcome: invalid/incomplete; no result published. Set-valued families completed, but the
first stale-authority scenario failed while constructing the paired fresh observation.
runs: completed set-valued runs — `01M05CK88WC45578NPP7MHENJK`, `01M05CN0SV6JZ4W1QB1BKD8N0K`, `01M05CQXH391MD8PCZJ24HVG2X`, `01M05CTXMEDBCJPCYAV6XR8WBJ`, `01M05CX6XGDWY740EM026BRBN6`, `01M05D00BKCBTGBY64QFZ877F6`, `01M05D1S0XDDT8GVWTBCYW720K`, `01M05D3MEEBBMW7SQ00Y2TAACS`, `01M05D4R34DN7GB02GRY5YNRK6`; partial stale-authority run `01M05D66XCEJ7VPY9ZHAWH4WXM`
negative controls: not run; block stopped before timing completion and controls
exclusions: partial run `01M05D66XCEJ7VPY9ZHAWH4WXM` excluded, reason `ValidationError` because `credential_age_ms=-3862.803` for the paired fresh credential; all block-02R2 runs excluded because the timing/control matrix was incomplete
observation: none publishable; no timing estimate or family result is inferred from this invalid block
anomalies: explained harness timestamp defect; deferred execution reused the pre-delegation timestamp for the freshly minted credential. Fixed by timestamping the fresh leg after delegation; focused regression tests passed (`5 passed`)
notes: sandbox destroy completed (`44 destroyed`), exact verify-clean passed, second destroy was a no-op, and second verify-clean passed.

## 2026-08-16 block-02R3 — checklist recorded before timestamp-fixed execution

checklist: legacy pre-repair record; live budget gate was not yet implemented; no valid M17 result inferred.
infrastructure: applied 13:53 UTC, 44 resources, fingerprint `sha256:e09c7cda85ffceb170041addaf9684dc8cc6aea3482d5c0ad6da703836b2c97f`, namespace `NAMESPACE_SCRUBBED`, region `eu-west-3`
adapter/catalog: adapter `0.1.0`, catalog `1.0.0`, chainbreak `0.1.0a0`, local commit `63841bb` (clean before execution)
sampling plan: set-valued families n=3 per scenario; timing families use one independent run in this window, two in block-03, and two in block-04, with all timing runs recorded by block ID (aggregate n=5 across three valid windows)
execution order: set-valued families, stale-authority timing, revocation timing with trust-policy last, then all six negative controls
scenarios: all five families and six negative controls required in this block; positive runs pending
runs: pending
negative controls: pending
exclusions: none at checklist time
observation: pending
anomalies: none at checklist time
notes: execution begins after this checklist is committed; any DETECTOR_FAILURE invalidates this block.

block outcome: invalid/incomplete; no result published. Set-valued families completed, but the
first stale-authority run stopped after the paired fresh probe because the orchestrator lacked
the explicit mapping for the declared `paired-fresh-credential` phase name.
runs: completed set-valued runs — `01M05DNMM36SHX8VCQX0C56W8N`, `01M05DQ4HG993GVY8FBG1YQSH2`, `01M05DSCNE8TWF762S66WN33GX`, `01M05DVNBY4E50YJB2FEHCYQF9`, `01M05DXZB22P80581ZAPQRCJNK`, `01M05E0SHD8QTDT89H4F30FE4J`, `01M05E4C7T7R36FKMPTCC9DKQZ`, `01M05E63BH3SZ5FR00ZSXBDBW6`, `01M05E71F0A1B97FWGXJ4KG00H`; partial stale-authority run `01M05E8P1B86ARKNRRPDE8A7FM`
negative controls: not run; block stopped before timing completion and controls
exclusions: partial run `01M05E8P1B86ARKNRRPDE8A7FM` excluded, reason `ExecutionError` for missing `PHASE_NAME_TO_PLAN_PHASE` mapping for `paired-fresh-credential`; all block-02R3 runs excluded because the timing/control matrix was incomplete
observation: none publishable; no timing estimate or family result is inferred from this invalid block
anomalies: explained harness mapping defect; fixed by adding the explicit `paired-fresh-credential` mapping and regression test; focused tests passed (`15 passed`)
notes: sandbox destroy completed (`44 destroyed`), exact verify-clean passed, second destroy was a no-op, and second verify-clean passed.

## 2026-08-16 block-02R4 — checklist recorded before mapped-phase execution

checklist: legacy pre-repair record; live budget gate was not yet implemented; no valid M17 result inferred.
infrastructure: applied 14:11 UTC, 44 resources, fingerprint `sha256:e09c7cda85ffceb170041addaf9684dc8cc6aea3482d5c0ad6da703836b2c97f`, namespace `NAMESPACE_SCRUBBED`, region `eu-west-3`
adapter/catalog: adapter `0.1.0`, catalog `1.0.0`, chainbreak `0.1.0a0`, local commit `309d153` (clean before execution)
sampling plan: set-valued families n=3 per scenario; timing families use one independent run in this window, two in block-03, and two in block-04, with all timing runs recorded by block ID (aggregate n=5 across three valid windows)
execution order: set-valued families, stale-authority timing, revocation timing with trust-policy last, then all six negative controls
scenarios: all five families and six negative controls required in this block; positive runs pending
runs: pending
negative controls: pending
exclusions: none at checklist time
observation: pending
anomalies: none at checklist time
notes: execution begins after this checklist is committed; any DETECTOR_FAILURE invalidates this block.

## 2026-08-16 block-02R4 outcome — invalid/incomplete

block outcome: invalid/incomplete; no result published. All nine set-valued runs
completed, and the deferred-execution and long-defer timing runs completed. The
post-expiry timing run failed before its expired-credential observations could be
sealed, so revocation timing and all six negative controls were not run.
runs: set-valued — `01M05EPZ1V8AH0B2QJGWSYFCDY`, `01M05ERAZ16XV980FGEMBBSW7N`, `01M05ETDV49CBVZ94V5E0P7FK9`, `01M05EW9CEC5WWSAJP972EHKC3`, `01M05EYJEZ9DBKJS07M6RYCKHT`, `01M05F1HSV6Y8M637JMFY5S7YJ`, `01M05F3BFBCF84HKEP20BEZEWB`, `01M05F4ZEEEATMNPQQ2MZQEJW5`, `01M05F5WK980YENW5DPS1BYJBA`; stale timing — `01M05F7ARSBH57799N3CHBZBNT` deferred-execution (120 s), `01M05FC41N7WD23MB96S87QQJD` long-defer (600 s); partial post-expiry — `01M05FZJ102GJGT3HEQZZ9CBRA`
negative controls: not run; block stopped before revocation and controls
exclusions: partial run `01M05FZJ102GJGT3HEQZZ9CBRA` excluded, reason `ExpiredToken` on the expected post-expiry `identity.whoami` control was re-raised as an apparatus fault by the adapter before classification; all block-02R4 runs excluded because the required timing/revocation/control matrix was incomplete
observation: none publishable; no timing estimate or family result is inferred from this invalid block
anomalies: explained adapter classification defect, not an unexplained provider defect; `ExpiredToken` is now classified as the expected denial for expired credentials, while other `identity.whoami` failures remain apparatus faults. Focused regression suite passed (`104 passed`) and Ruff passed.
notes: sandbox destroy completed (`44 destroyed`), exact verify-clean passed, second destroy was a no-op, and second verify-clean passed. The next block must use the committed fix and a newly recorded nine-item checklist.

## No valid M17 block has been published

## 2026-08-16 block-02R5 pre-block guard — not started

checklist: legacy pre-repair record; post-clean live validation correctly failed because destroy removed outputs; no valid M17 result inferred.
infrastructure: none applied for this attempted block; no run started
runs: none
negative controls: none
exclusions: none; this was a pre-block guard failure, not an experiment block
observation: none
anomalies: the current teardown removes `outputs.json`, preventing a post-clean live validation/status gate before the next apply; no provider defect inferred
notes: residual prior-sandbox resources were destroyed (`44 destroyed`), exact verify-clean passed, second destroy was a no-op, and second verify-clean passed. No new block will start until the setup/checklist ordering is made protocol-compliant.

Invalid and incomplete AWS executions are recorded above with their run IDs and reasons.
**No valid M17 block has produced a publishable measurement.**

## 2026-08-17 M17 workflow preflight exclusions

These workflow attempts stopped before AWS apply. They are apparatus/preflight
failures, not measurements, and no Chainbreak run IDs were produced.

| block | GitHub workflow run | pre-apply result | exclusion reason | AWS apply |
|---|---:|---|---|---|
| M17-20260817-W01 | `32021454170` | failed environment contract | Environment-scoped `CHAINBREAK_BUDGET_LIMIT_USD` was not mapped at workflow scope; no OIDC, namespace, or apply | no |
| M17-20260817-W02 | `32021740136` | failed environment contract | Direct `CHAINBREAK_BUDGET_LIMIT_USD` mapping was missing from the per-job environment; no OIDC, namespace, or apply | no |
| M17-20260817-W03 | `32021898659` | OIDC apparatus failure | Role trust used the legacy GitHub subject and credentials action retried; no namespace or apply | no |
| M17-20260817-W04 | `32022274942` | clean-gate failure | Namespace/artifact capture created an untracked `artifacts/` directory before the clean-tree check; no apply | no |
| M17-20260817-W05 | `32022533049` | clean-gate failure | Same artifact-ordering defect; diagnostic output recorded `?? artifacts/`; no apply | no |
| M17-20260817-W06 | `32022681703` | test-gate failure | Full unit/integration gate reported 9 failures, 1,803 passed, 9 skipped, 28 deselected. The AWS env was visible to tests that require default/fake settings; no OIDC, namespace, or apply | no |

All six attempts were cancelled before any apply approval or AWS resource creation.
They are excluded from family/control matrices, sample counts, timing windows,
scores, and public archives. The W06 test-isolation fix is pending commit and a
new preflight run.

## 2026-08-17 M17-20260817-W07 — applied, live-gate invalid, cleaned

checklist: preflight contract passed; clean tree and unit/integration tests passed;
short-lived GitHub OIDC role assumption passed; pre-apply namespace/status/verify-clean
passed; budget guard contract passed; separate operator approval recorded for apply;
fresh post-apply status and outputs were captured; separate operator approval recorded
for destroy.
infrastructure: applied 11:13:49 UTC, fingerprint
`sha256:28a55a99d6322de3b75abdb55f5d4001be383331cba525ce587f4895842f36dc`, exact
namespace captured as `cb-3cee2aea` before teardown, region `eu-west-3`; 44 resources
were created and the budget guard was present in Terraform state.
adapter/catalog: repository commit `a19319e`; provider `aws`; negative controls were
enabled; no benchmark or control run was started.
scenarios: suite requested; positive-family matrix not run; all six negative controls
not run.
runs: none; no sealed Chainbreak run IDs exist for this block.
negative controls: not run.
exclusions: whole block excluded because fresh `chainbreak validate --provider aws
--stage live --check-budget --block-id M17-20260817-W07` failed its AWS P1-P11 gate
with `marker_preconditions`; no measurement is inferred and no provider conclusion
is drawn from the failure.
observation: none publishable; no public scrubbed archive or scrub diff was produced
because no run was sealed.
anomalies: live infrastructure validation found a missing marker precondition after
apply. This is recorded as an apparatus/infrastructure failure pending diagnosis, not
as a provider measurement.
cleanup: first destroy completed with `44 destroyed`; second destroy completed with
`0 destroyed` and no changes; exact namespace `cb-3cee2aea` verify-clean passed with
`nothing remaining`; cleanup artifact recorded `state_ready=true`.
outcome: invalid/incomplete; no result published and `results-v0.1.md` remains gated.

## 2026-08-17 M17-20260817-W08 — applied, live-gate invalid, cleaned

checklist: preflight contract passed; clean tree and unit/integration tests passed;
short-lived GitHub OIDC role assumption passed; pre-apply namespace/status/verify-clean
passed; budget guard contract passed; separate operator approval recorded for apply;
fresh post-apply status and outputs were captured; separate operator approval recorded
for destroy.
infrastructure: applied 11:24:28 UTC, fingerprint
`sha256:28a55a99d6322de3b75abdb55f5d4001be383331cba525ce587f4895842f36dc`, exact
namespace captured as `cb-3cee2aea` before teardown, region `eu-west-3`; 44 resources
were created and state was sealed for cleanup.
adapter/catalog: repository commit `4f8249b`; provider `aws`; negative controls were
enabled; no benchmark or control run was started.
scenarios: suite requested; positive-family matrix not run; all six negative controls
not run.
runs: none; no sealed Chainbreak run IDs exist for this block.
negative controls: not run.
exclusions: whole block excluded because fresh `chainbreak validate --provider aws
--stage live --check-budget --block-id M17-20260817-W08` failed its AWS P1-P11 gate
with `objectstore.marker_present`, `keyvalue.marker_present`, and `queue.present`;
`function.alive` passed. No measurement is inferred and no provider conclusion is
drawn from the failure.
observation: none publishable; no public scrubbed archive or scrub diff was produced
because no run was sealed.
anomalies: the same three marker preconditions failed in two consecutive freshly
applied blocks while the Lambda precondition passed. This repeated infrastructure /
apparatus failure is recorded for diagnosis; public measurement work remains stopped.
cleanup: first destroy completed with `44 destroyed`; second destroy completed with
`0 destroyed` and no changes; exact namespace `cb-3cee2aea` verify-clean passed with
`nothing remaining`; cleanup artifact recorded `state_ready=true`.
The next valid block must satisfy the complete family/control matrix and the timing/sample
requirements before any result is published.

## 2026-08-17 M17-20260817-W09 — applied, budget live-gate invalid, cleaned

checklist: preflight contract passed; clean tree and unit/integration tests passed;
short-lived GitHub OIDC role assumption passed; exact pre-apply namespace/status/
verify-clean passed; budget guard contract passed; blanket operator approval for W09
apply and subsequent M17 apply/destroy gates was recorded; fresh post-apply status and
Terraform outputs were captured before validation.
infrastructure: applied at 12:11:09 UTC, 44 resources added, 0 changed, 0 destroyed;
fresh fingerprint `sha256:28a55a99d6322de3b75abdb55f5d4001be383331cba525ce587f4895842f36dc`,
exact namespace captured before teardown as `cb-3cee2aea`, region `eu-west-3`.
adapter/catalog: repository commit `1d395216e6058eedc1fe3e777f8250d156ccb0f1`;
provider `aws`; negative controls enabled; budget limit configured in the workflow as
`1.0` USD.
scenarios: suite requested; all five positive benchmark families were not run because
the post-apply live gate failed first; all six negative controls were not run.
runs: none; no sealed Chainbreak run IDs exist for this block.
negative controls: not run.
exclusions: whole block excluded because fresh
`chainbreak validate --provider aws --stage live --check-budget --block-id
M17-20260817-W09` failed `AWS live validation (P1-P11) + budget` with the exact detail
`budget missing a positive monthly COST limit or active subscribed alarm`. No benchmark
or control measurement is inferred. The marker checks were not reached in this block.
observation: none publishable; no timing or family score is inferred.
anomalies: explained budget-guard apparatus failure; this block provides no evidence
for or against an AWS provider defect. Public archive and scrub diff were not produced
because no run was sealed.
repair: validator corrected in commit `4c28743` to accept a subscribed budget
notification in the AWS-documented healthy `OK` state as well as `ALARM`; focused
protocol tests passed (`12 passed`).
cleanup: destroy approval was recorded under the blanket operator approval; first
destroy completed with `44 destroyed`; second destroy completed with `0 destroyed` and
no changes; exact namespace `cb-3cee2aea` verify-clean passed with `nothing remaining`.
outcome: invalid/incomplete; no result published and `results-v0.1.md` remains gated.

---

## Template

```
## YYYY-MM-DD block-NN
stage A:              pass | record clean tree, tests, config/budget guard, exact namespace cleanup, and lock
stage B:              pass | record fresh outputs/fingerprint, live P1-P11, markers, preconditions, budget, and clock
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
