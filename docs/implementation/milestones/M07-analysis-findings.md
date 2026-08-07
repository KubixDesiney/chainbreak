# M7 — Analysis, findings and the confidence gate

## Purpose
Turn sealed evidence into observed authority, divergence, and findings — as a pure,
re-runnable function. After this milestone the analytic core is complete and validated
against known ground truth, before any AWS code exists.

## Dependencies
M6.

## Required components
`analysis/authority.py` (observations → `ProbeCellResult` → `ObservedAuthority`),
`analysis/divergence.py` (apply M1 algorithms to a bundle's graph),
`analysis/confidence.py` (the gate), `analysis/rules.py` (one rule per finding type),
`analysis/timing.py` (revocation window, stale classification),
`analysis/detector.py` (negative-control assertion → `DETECTOR_FAILURE`),
`analysis/pipeline.py` (orchestration, idempotent).

## Files expected
```
src/chainbreak/analysis/{authority,divergence,confidence,rules,timing,detector,pipeline}.py
tests/unit/{test_authority_aggregation,test_confidence_gate,test_finding_rules,test_revocation_math,test_stale_classification}.py
tests/integration/{test_known_truth_divergence,test_known_truth_timing,test_analyze_idempotence}.py
```

## Functional requirements
- F1 Cell resolution by **unanimity** (ADR-012): all-`ALLOWED` ⇒ `ALLOWED`; all-denial ⇒ that
  denial (or `DENIED_UNATTRIBUTED` if attributions differ); all-error ⇒ that error; mixed ⇒
  `INDETERMINATE` with the trial vector recorded.
- F2 `ObservedAuthority` contains only `ALLOWED` cells (AUTH-1); everything else lands in
  `excluded` with an `ExclusionReason`.
- F3 Confidence gate exactly as [AUTHORIZATION_MODEL §6](../../../AUTHORIZATION_MODEL.md#6-from-divergence-to-finding).
  `INSUFFICIENT` ⇒ the finding becomes `INCONCLUSIVE`.
- F4 One rule per finding type, each with an explicit predicate and each emitting
  `observation`, `expected_state`, `observed_state` and `security_interpretation` as
  **separate** fields.
- F5 Revocation math: `t_last_allow`, `t_first_deny`, `transition_window`, uncertainty
  half-width, `NON_MONOTONIC_TRANSITION`, `NO_TRANSITION_OBSERVED_WITHIN_WINDOW`.
- F6 Stale classification per the six-row table, requiring the paired fresh-credential
  outcome to disambiguate.
- F7 Detector check: assert every negative control's `expect_finding` was produced; emit
  `DETECTOR_FAILURE` otherwise.
- F8 Idempotence: analyzing the same bundle twice yields byte-identical `findings.json`.

## Non-functional requirements
Analysis of a 10 000-observation bundle under 5 s. Pure: no network, no provider, no clock
reads that affect output.

## Security requirements
- S1 Analysis operates on possibly-untrusted bundles; never trusts a field without schema
  validation.
- S2 `security_interpretation` strings are static templates with substituted values, never
  free-form text built from bundle content — that would be an injection path into the HTML
  report (T-10).

## Tests
`test_known_truth_divergence.py` is the differential control (C-9): configure the fake with a
*known* authority set differing from intent, run, analyze, and assert exactly the expected
findings with exactly the expected confidence. `test_known_truth_timing.py` sets
`propagation_delay_ms = 2000` and asserts the measured window contains 2000 ms — this
directly validates the interval math against a known answer, which no AWS run can do.

## Negative controls
Run all six `nc-*` scenarios against the fake; each must produce its declared finding. Then
"fix" each defect and assert `DETECTOR_FAILURE` is emitted. Both directions are required:
the first proves detection, the second proves the detector check itself works.

## Acceptance criteria
1. Every finding type has a rule, a test, and at least one scenario that produces it.
2. Known-truth divergence and timing tests pass against the fake.
3. All six negative controls detected; all six "fixed" variants produce `DETECTOR_FAILURE`.
4. `analyze` is idempotent (byte-identical output).
5. Coverage ≥ 95% on `analysis/`.

## Verification commands
```bash
pytest -m "unit or integration" tests/unit/test_finding_rules.py tests/integration/ -q
chainbreak run scenarios/_negative-controls/nc-scope-expansion.yaml --provider fake --seed 3
chainbreak analyze <run-id> && chainbreak analyze <run-id>
diff <(jq -S . runs/<run-id>/findings.json) <(jq -S . runs/<run-id>/findings.json)
```

## Definition of done
Acceptance criteria met; AUTHORIZATION_MODEL §6 updated if a predicate changed;
`PROJECT_STATUS.md` updated.

## Out of scope
Scoring (M15). Reporting (M16). AWS.

## Risks
A rule that fires on noise. The confidence gate plus unanimity are the controls. Resist any
temptation to "smooth" a `NON_MONOTONIC_TRANSITION` — oscillation is the most interesting
possible result in the revocation family, and hiding it would be a research failure, not a
usability improvement.
