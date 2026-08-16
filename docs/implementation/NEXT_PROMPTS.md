# Ready-to-run Claude Code prompts — final phase

**State verified 2026-08-11.** M0–M16 complete. M8 and M9 are code-complete with only their
real-account acceptance criteria outstanding. 1,693 tests passing (1,454 unit, 239 integration),
119 source files clean under `ruff` and `mypy --strict`, 6/6 import-linter contracts kept,
21 `aws`-marked tests written and waiting.

**The AWS account state is not recorded here.** The real-account acceptance work requires an
operator-provisioned dedicated account; its identifier, region, namespace, and live resource
state must be supplied at execution time and must not be committed to documentation.

S1–S8 from the previous edition are all done. This edition covers what remains: two offline
sessions, two AWS sessions, and the release.

---

## Ordering

```
P1 (offline, now)  ─┐
P2 (offline, now)  ─┼─→  P3 (AWS, needs outputs.json)  →  P4 (AWS, needs ≥3 blocks)  →  P5 (release)
                    ┘
```

P1 and P2 need nothing from you and can run today, in either order, in parallel.
P3 needs one command from you first. P4 needs P3 green and a day of elapsed time.

---

## P1 — Documentation truth pass (offline, ~30 min)

Small, and it removes the one thing a reviewer would catch immediately.

```
Documentation consistency session for CHAINBREAK. No new features, no behaviour changes.

Read docs/CLAUDE_CODE_HANDOFF.md Part 2 first. Run `pytest -m "unit or integration" -q` and
record the baseline — it must be identical at the end.

1. ARCHITECTURE.md section 2 shows `delegation/` and `observation/` as layers in the mermaid
   diagram (lines ~53 and ~62) and describes them in sections 3.7 and 3.12. Both packages are
   empty on disk: delegation planning landed in execution/delegation.py and outcome
   classification in execution/matrix.py and execution/_records.py. The consolidation was the
   right call — do NOT reverse it by creating those packages. Fix the documentation instead:
   update the diagram, rewrite 3.7 and 3.12 to describe where the responsibility actually
   lives, and add a one-line note in docs/DECISIONS.md under "Smaller decisions" recording
   that the two layers folded into execution/ and why. Then delete the two empty package
   directories so the tree matches the docs.

2. Audit every root document for claims that no longer match the code. Specifically check:
   the CLI command list in ARCHITECTURE.md 3.1 against `chainbreak --help`; the module list in
   TESTING.md against what exists; the file layout in README.md; and any "not implemented"
   or "pending" marker that is now stale. Report what you found before changing it.

3. Verify every internal markdown link still resolves. There should be zero broken links.

4. Confirm PROJECT_STATUS.md's milestone table matches reality: M0-M16 complete, M8/M9
   real-account criteria outstanding, M17-M19 remaining.

Do not touch src/ except to delete the two empty package directories. The test count must be
unchanged at the end — if it moved, something was not a documentation change.

Paste real output for the link check and the test run. Update PROJECT_STATUS.md. Stop when
docs and code agree.
```

---

## P2 — M18 offline portion (offline, ~half a day)

Everything in M18 except the parts that need real runs to compare.

```
Implement the offline portion of milestone M18 for CHAINBREAK — reproducibility tooling.

Read docs/CLAUDE_CODE_HANDOFF.md, docs/implementation/milestones/M18-reproducibility-hardening.md,
and REPRODUCIBILITY.md in full. Run the suite and confirm 1,693 tests pass.

Note the scope boundary: `chainbreak compare` and `chainbreak evidence export` already exist as
CLI commands, but analysis/compare.py, evidence/archive.py and evidence/migrate.py do not exist
and `export` has no --archive flag. Build those. Do NOT attempt the parts of M18 that require
real AWS runs to compare — Level 3 distributional comparison can be exercised against two
fake-provider runs with different seeds, which is sufficient to validate the logic.

Implement:

1. analysis/compare.py implementing the three levels from REPRODUCIBILITY section 1:
   - Level 1 analytical: same bundle re-analyzed, byte-identical findings.
   - Level 2 structural: set-valued results (observed authority, divergence, first divergence
     hop) match exactly. A Level 2 failure is itself a finding — it means authorization
     behaviour was non-deterministic where it should not have been. Report it as such, not as
     a tool error.
   - Level 3 distributional: timing results overlap with a comparable median. Exact
     reproduction is NOT expected and the output must say so in words, not just in a status
     code. Anyone claiming exact timing reproducibility on a shared cloud control plane is
     mistaken, and the tool should not imply otherwise.

2. Refuse to compare across differing compiled_hash, adapter_version or catalog_version
   without --allow-heterogeneous, which lowers reported confidence. --cross-operator relaxes
   the environment checks and must print a prominent note that environment equivalence is
   assumed and unverified.

3. evidence/archive.py and an --archive flag on `evidence export`. The tarball contains the
   bundle, the resolved scenario, the capability catalog AS IT WAS AT RUN TIME, the JSON
   schemas, and a generated REPRODUCE.md with exact commands and versions. Schemas are
   included because a bundle without its schema is uninterpretable once schemas evolve.
   --archive implies --public scrubbing; there is no unscrubbed archive path.
   Test self-containment by extracting into a directory with no repository present and
   asserting every referenced file resolves.

4. evidence/migrate.py for evidence format version transitions, preserving the original.

5. A Dockerfile producing byte-identical fake-provider runs. Verify by running the same
   scenario with the same seed inside and outside the container and diffing the observation
   stream hashes.

6. A dependency lockfile with hashes, and `pip install --require-hashes` wired into CI
   (threat T-14).

Preserve every invariant in handoff Part 2 — especially that --archive cannot bypass scrubbing.
Run the verification commands, paste real output including the two-seed comparison and the
container determinism check. Update PROJECT_STATUS.md. Stop only when every offline acceptance
criterion in the milestone file passes.
```

---

## P3 — Close M8 and M9 against the real account (AWS, ~1 hour)

**Prerequisite from you:** `outputs.json` must exist. One command, listed in the section below.

```
Close the real-account acceptance criteria for milestones M8 and M9 of CHAINBREAK.

This session spends real money (well under $1) and creates and destroys real IAM roles in the
operator's dedicated benchmark account. Confirm with the operator before the first billable
command, and again before `terraform destroy`.

Read docs/CLAUDE_CODE_HANDOFF.md, docs/implementation/milestones/M08-aws-adapter.md and
M09-terraform-sandbox.md, and AWS_PROVIDER_SPEC.md sections 2, 6 and 10.

Environment, already verified:
  account   <operator-configured>   region <operator-configured>   namespace <captured-output>
  infrastructure state and marker checks must be verified at execution time
  chainbreak.toml must be present and resolving
  use the operator's approved short-lived authentication method

Sequence:

1. `chainbreak validate` — all eleven preflight checks P1 through P11 must pass. Paste the
   full output. If P9 warns about production-tagged resources, STOP and report rather than
   passing --i-know-what-i-am-doing.

2. Run the 21 aws-marked tests: `CHAINBREAK_ALLOW_AWS_TESTS=1 pytest -m aws -q`.
   These are the only place real IAM semantics get validated. Pay particular attention to two:
   - test_denial_message_attribution is the canary for AWS changing its error message format.
     If it fails, denial_attribution classification is silently degraded across the whole
     project. Do not "fix" it by loosening the assertion — report the actual message shape you
     observed so the classifier can be updated deliberately.
   - test_s3_403_404_ambiguity confirms the documented behaviour the marker precondition exists
     to handle. If it does NOT reproduce, that is more interesting than if it does, and it means
     the precondition control may be guarding against something that is not happening here.

3. Confirm the AWS adapter passes the shared M5 provider contract assertions. Fixed-role AWS
   setup may use explicit hooks; if a contract test fails against real AWS, the finding is in
   the adapter or setup hook, never in the behavioral assertion. Do not weaken it.

4. Verify the H7 chained-role cap empirically: request 7200s on a chained hop, assert the grant
   is 3600s and LIFETIME_CAPPED is emitted.

5. Verify SI-12 with iam:SimulatePrincipalPolicy: bootstrap must be denied PutRolePolicy on
   both principal and itself, and allowed on agent-b. Note the operator's IAM user currently
   lacks iam:SimulatePrincipalPolicy — if the call is denied, either request that permission or
   verify by reading the bootstrap policy's Resource list and say which method you used.

6. `terraform destroy`, then `terraform destroy` again (must be a clean no-op), then
   `chainbreak infra verify-clean` showing zero resources tagged Project=CHAINBREAK remaining.
   Then re-apply, because M17 needs the infrastructure back.

7. If `tflint` is installed, run it to close the remaining half of M9 criterion 2. If it is
   not, say so plainly rather than marking the criterion met.

Paste real command output for every step — not a description of it. Update PROJECT_STATUS.md
marking M8 and M9 genuinely complete, recording the date, the hashed account, the region, and
which tests actually ran. Never mark a criterion met that you did not observe pass.
```

---

## P4 — M17, the first real measurements (AWS, ~1 day elapsed)

This is the one that produces the actual research result. It is mostly discipline, not code.

```
Execute milestone M17 for CHAINBREAK — the full AWS experiment suite. This produces the
project's first real measurements.

Read EXPERIMENT_PROTOCOL.md IN FULL and RESEARCH_METHODOLOGY.md IN FULL before running anything.
Read docs/implementation/milestones/M17-aws-experiment-suite.md. Confirm P3 completed and both
M8 and M9 are marked genuinely complete.

This is an experimental session, not a coding one. The discipline IS the deliverable. A suite
run carelessly produces numbers that look identical to a suite run properly and are worthless.

Per block, in order:

1. Run the EXPERIMENT_PROTOCOL section 0 pre-experiment checklist, all nine items. Record the
   result in docs/research/lab-log.md INCLUDING the items that passed. An experiment whose
   checklist was not run is not a CHAINBREAK experiment.
2. Apply infrastructure with enable_negative_controls = true.
3. Run all five families at the required trial counts: n>=5 for timing families (revocation,
   stale authority), n>=3 for set-valued families (scope attenuation, delegation drift, silent
   narrowing).
4. Run ALL SIX negative controls in the SAME block, on the SAME infrastructure, with the SAME
   adapter version. A control run later against different infrastructure proves less.
5. Record every excluded trial with its reason and its run ID. Silent exclusion is the classic
   way to manufacture a clean result, and it is the one thing that would make this suite
   indefensible.
6. Destroy, then `chainbreak infra verify-clean`.

Distribute the timing trials across AT LEAST THREE separate hours, recording block_id (control
C-7). IAM propagation may plausibly vary with provider-side load, and back-to-back trials
cannot detect that. This is why the milestone takes a day rather than an hour — do not
compress it.

Two results you should expect and must not misreport:

- revocation/trust-policy-null-condition should show NO transition. That is control C-5, the
  instrument check. If it shows a fast transition, the apparatus is wrong and the entire block
  is discarded, not published.
- Most families will likely show exactly the documented behaviour: session policies do not
  grant, attenuation is exact, no drift. That is a GOOD outcome and a publishable one. It
  means the instrument works, which is the precondition for believing the revocation and
  stale-authority intervals — the numbers nobody has published.

If any block produces a DETECTOR_FAILURE, that block is unvalidated. Do not publish any result
from it. This is not a guideline.

Write docs/research/results-v0.1.md from actual measurements only. Every timing result carries
n, an interval (never a scalar), the mechanism, and the region. Every claim is scoped to "this
account, this region, this time". Apply the EXPERIMENT_PROTOCOL section 7 language rules — the
lint from M16 will catch violations, but write it correctly the first time.

If a result suggests a genuine provider defect rather than one of the documented behaviours in
AWS_PROVIDER_SPEC section 10: STOP. Reproduce it. Re-run the negative controls. Rule out the
known measurement hazards. Then follow coordinated disclosure per SECURITY.md before publishing
anything. Do not open a public issue and do not write it up.

Update PROJECT_STATUS.md moving experiments from "unmeasured" to "measured" WITH RUN IDS, and
listing what remains unmeasured. Paste real run IDs and real output. Never claim an experiment
ran unless it ran.
```

---

## P5 — M19 release (offline, needs your publication decision)

```
Execute milestone M19 for CHAINBREAK — the v0.1.0 release.

Read docs/implementation/milestones/M19-portfolio-release.md, docs/PORTFOLIO_STORY.md and
PROJECT_STATUS.md. Confirm M17 produced real results and M18 is complete. Run the full suite.

1. Full consistency review across: scenario schema, domain models, authorization graph,
   provider abstraction, capability model, AWS adapter, Terraform contracts, testing strategy,
   evidence schema, findings, scoring, reporting, README. Resolve every contradiction and
   record each resolution in docs/DECISIONS.md. Do not paper over one — where two documents
   disagree, one of them is wrong and it matters which.

2. Then the part requiring the most discipline: audit every document for claims about results.
   Update docs/PORTFOLIO_STORY.md and README.md to describe ONLY what M17 actually measured,
   each with its run ID. Anything designed and implemented but unmeasured is described exactly
   that way, explicitly.

   The strongest temptation in this project arrives here — describing the architecture as if it
   were results. The architecture is real and defensible; the measurements are whatever M17
   produced. State both accurately. A reviewer who knows AWS can check an overclaim in thirty
   seconds, and failing that check costs more than the claim was worth.

   Fill in the PORTFOLIO_STORY M19 update checklist, including the honest surprises — and note
   that "the documented behaviour held, measured as follows" is a legitimate and useful result,
   not a disappointing one.

3. Verify no sensitive value exists in the repository OR ITS GIT HISTORY: account IDs, ARNs,
   key-shaped strings, hostnames, session names. A working-tree
   scan is not sufficient — scan the history.

4. Execute every command that appears in the README and confirm it works as documented.

5. Write CHANGELOG.md. Publish a scrubbed sample report under examples/. Confirm the README
   status block matches PROJECT_STATUS.md exactly.

6. Tag v0.1.0.

Paste real output for every verification command. Update PROJECT_STATUS.md to the released
state, including an explicit list of what remains unmeasured.
```

---

## Session discipline

Unchanged, and it has held up so far:

- One prompt per session.
- If Claude Code reports "acceptance criteria met" without pasted command output, ask for the
  output before believing it.
- If it proposes changing an invariant from handoff Part 2, read the ADR it would supersede
  before agreeing.
- If it weakens or deletes an existing test to make something pass, reject the change. A green
  suite cannot warn you about that one.
