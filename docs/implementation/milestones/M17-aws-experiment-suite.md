# M17 — Full AWS experiment suite: the first real measurements

## Current status

Not complete. The dedicated-account M8/M9 acceptance passed, but every M17 attempt recorded so
far was invalid or incomplete. Zero M17 blocks are valid or publishable, and no M17 measurement
is claimed. The historical apparatus attempts and their exclusions remain in
`docs/research/lab-log.md`; their intermediate values are superseded and excluded from all
measurement claims.

## Purpose
Execute all five families against real AWS infrastructure, with negative controls, block
randomization, and honest reporting. **This is the first milestone that produces a
measurement.**

## Dependencies
M9 and M16. **Uses the operator-owned AWS benchmark account and real spend (< $1).**

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
- F1 Complete Stage A and Stage B ([EXPERIMENT_PROTOCOL §0](../../../EXPERIMENT_PROTOCOL.md#0-two-stage-experiment-gates))
  in order before every block; record both results in the lab log.
- F2 Run all five families with the trial counts in RESEARCH_METHODOLOGY §5: n≥5 for timing,
  n≥3 for set-valued.
- F3 Distribute timing trials across **at least three separate hours** (control C-7), with
  `block_id` recorded.
- F4 Run the full negative-control suite **in the same block**, on the same infrastructure,
  with the same adapter version.
- F5 Record every exclusion with its reason in the lab log and in the report.
- F6 Capture the exact namespace before destroy and run `chainbreak infra verify-clean` after every block.
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

The runnable contract is `.github/workflows/aws-experiment.yml`. Its environment-scoped
contract supplies `CHAINBREAK_*` settings and `TF_VAR_*` values without printing them. The
operator supplies a non-empty `<block-id>` and uses this ordering:

Set `CHAINBREAK_ACCOUNT_ID`, `CHAINBREAK_REGION`, and `CHAINBREAK_BUDGET_LIMIT_USD` as
environment variables; set `CHAINBREAK_BENCHMARK_ROLE_ARN`, `CHAINBREAK_NAMESPACE_SALT`,
`CHAINBREAK_OPERATOR_PRINCIPAL_ARNS` (a Terraform JSON list of role ARNs), and
`CHAINBREAK_BUDGET_NOTIFICATION_EMAIL` as environment secrets. The workflow maps these to
both CHAINBREAK configuration variables and the required `TF_VAR_*` inputs, and fails before
OIDC use when any required value is empty.

```bash
chainbreak infra namespace aws-sandbox --provider aws --block-id <block-id> > artifacts/namespace.txt
chainbreak validate --provider aws --stage pre-apply --check-budget --block-id <block-id>
chainbreak infra verify-clean aws-sandbox --provider aws --block-id <block-id> --namespace "$(< artifacts/namespace.txt)"
chainbreak infra apply aws-sandbox --provider aws --block-id <block-id> --auto-approve
chainbreak infra status aws-sandbox --provider aws --block-id <block-id> --capture-namespace artifacts/namespace.txt
chainbreak validate --provider aws --stage live --check-budget --block-id <block-id>
chainbreak run scenarios/scope-attenuation/basic.yaml --provider aws --block-id <block-id> --run-id-file artifacts/run-ids.txt
while read -r run_id; do
  chainbreak analyze "$run_id" --provider aws --block-id <block-id>
  chainbreak evidence export "$run_id" --provider aws --block-id <block-id> --archive --output "artifacts/$run_id.tar.gz"
done < artifacts/run-ids.txt
chainbreak infra destroy aws-sandbox --provider aws --block-id <block-id> --auto-approve
chainbreak infra verify-clean aws-sandbox --provider aws --block-id <block-id> --namespace "$(< artifacts/namespace.txt)"
```

For a suite, repeat the `chainbreak run` line for every positive and negative-control
scenario, keeping the same outputs, provider, block id, and applied namespace. Never use
`--latest` or `--json`; the CLI does not provide those options for these commands.

## Cancellation and orphan recovery

The workflow serializes the benchmark environment with `concurrency.cancel-in-progress: false`.
It writes `artifacts/namespace.txt` before apply and `artifacts/apply-attempted` before the
apply command, so the always-run cleanup can destroy and verify the exact namespace after a
failure or cancellation. If a runner disappears before cleanup completes, download the
workflow artifact (or use the namespace derived by `chainbreak infra namespace` from the same
environment contract), assume the reviewed OIDC role, and run `chainbreak infra destroy
aws-sandbox --provider aws --block-id <recovery-block> --auto-approve` followed by
`chainbreak infra verify-clean aws-sandbox --provider aws --block-id <recovery-block>
--region <region> --namespace <captured-namespace>`. Do not start another apply until
verify-clean reports zero exact-namespace resources.

The artifact path contains scrubbed evidence, run ids, and namespace metadata only. Terraform
state and `.terraform/` are never uploaded as ordinary artifacts.

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
