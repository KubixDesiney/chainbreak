# M17 — Full AWS experiment suite: the first real measurements

## Purpose
Execute all five families against real AWS infrastructure, with negative controls, block
randomization, and honest reporting. **This is the first milestone that produces a
measurement.**

## Dependencies
M9 and M16. **Requires an operator-owned AWS benchmark account and real spend (< $1).**

## Required components
No new architecture. Execution, observation, a lab log, and discipline.

## Files expected
```
docs/research/lab-log.md                  # appended per block
docs/research/results-v0.1.md             # the write-up
runs/<run-ids>/                           # gitignored; exported bundles under examples/
examples/reports/                          # a published, scrubbed report
```

## Functional requirements
- F1 Complete the pre-experiment checklist ([EXPERIMENT_PROTOCOL §0](../../../EXPERIMENT_PROTOCOL.md#0-pre-experiment-checklist))
  before every block; record the result in the lab log.
- F2 Run all five families with the trial counts in RESEARCH_METHODOLOGY §5: n≥5 for timing,
  n≥3 for set-valued.
- F3 Distribute timing trials across **at least three separate hours** (control C-7), with
  `block_id` recorded.
- F4 Run the full negative-control suite **in the same block**, on the same infrastructure,
  with the same adapter version.
- F5 Record every exclusion with its reason in the lab log and in the report.
- F6 `chainbreak infra verify-clean` after every block.
- F7 Produce `docs/research/results-v0.1.md` from actual measurements only.

## Non-functional requirements
Total cost under $1. Each block under 90 minutes. All infrastructure destroyed after each.

## Security requirements
- S1 A dedicated benchmark account; the allowlist contains only it.
- S2 Never publish an unscrubbed bundle. `evidence export --public`, diff reviewed.
- S3 If a result suggests a genuine provider defect rather than documented behavior: **stop**
  and follow coordinated disclosure per [SECURITY.md](../../../SECURITY.md) before publishing.

## Tests
The experiment *is* the test. Additionally: `test_adapter_real.py` (M8) must pass in the same
block, and the negative-control suite must be `DETECTOR_OK` throughout.

## Negative controls
All six, in every block. **A block containing a `DETECTOR_FAILURE` is unvalidated: do not
publish any result from it.** This is not a guideline.

## Acceptance criteria
1. All five families executed against real AWS with the required trial counts.
2. All six negative controls `DETECTOR_OK` in every published block.
3. Timing measurements distributed across ≥3 blocks with `block_id` recorded.
4. `results-v0.1.md` contains only measured values, each with n, interval, mechanism, region.
5. Every claim scoped to "this account, this region, this time".
6. `verify-clean` shows nothing remaining after every block.
7. `PROJECT_STATUS.md` moves experiments from "unmeasured" to "measured" **with run IDs**.

## Verification commands
```bash
chainbreak validate && chainbreak infra apply aws-sandbox
chainbreak run scenarios/scope-attenuation/basic.yaml
chainbreak run scenarios/delegation-drift/four-hop.yaml
chainbreak run scenarios/revocation/inline-deny.yaml
chainbreak run scenarios/revocation/trust-policy-null-condition.yaml
chainbreak run scenarios/stale-authority/deferred-execution.yaml
chainbreak run scenarios/silent-narrowing/two-step-pipeline.yaml
for f in scenarios/_negative-controls/*.yaml; do chainbreak run "$f"; done
chainbreak analyze --aggregate --block "$(date +%Y%m%d-%H)"
chainbreak infra destroy aws-sandbox && chainbreak infra verify-clean
```

## Definition of done
All acceptance criteria met with **real run IDs and real output pasted**. `PROJECT_STATUS.md`
lists exactly which experiments ran, when, in which account (hashed), and which remain
unmeasured.

## Out of scope
Cross-provider comparison. Statistical hypothesis testing (n is too small). Any claim about
AWS in general.

## Risks
The temptation to publish n=1. The temptation to describe a documented behavior as a
discovery. The temptation to omit an inconvenient exclusion. Every one of these is a
publication-checklist item precisely because every one is tempting.
