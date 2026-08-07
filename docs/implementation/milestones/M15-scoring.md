# M15 — Per-category scoring

## Purpose
Aggregate findings into six independent category results with coverage and confidence, and
make it structurally impossible to emit a composite score.

## Dependencies
M13, M14.

## Required components
`scoring/categories.py` (one evaluator per category), `scoring/coverage.py`,
`scoring/confidence.py` (min-aggregation), `scoring/aggregate.py` (cross-run, guarded).

## Files expected
```
src/chainbreak/scoring/{categories,coverage,confidence,aggregate}.py
tests/unit/{test_scoring,test_coverage,test_cross_run_aggregation}.py
```

## Functional requirements
- F1 Six evaluators exactly as [SCORING_MODEL §2](../../../SCORING_MODEL.md#2-category-results).
- F2 `status` ∈ {`CONSISTENT`, `DIVERGENT`, `PARTIAL`, `NOT_MEASURED`, `DETECTOR_FAILED`}.
  A category not exercised by the scenario is `NOT_MEASURED` — never `CONSISTENT`.
- F3 `coverage < 0.7` forces `PARTIAL` regardless of what the measured cells showed, and the
  report leads with coverage rather than the result.
- F4 Confidence aggregates with `min`, never a mean.
- F5 Revocation Responsiveness is `DIVERGENT` only when an **assertive** scenario expectation
  was exceeded. There is no built-in propagation threshold.
- F6 `STALE_AUTHORITY_LIVE_CREDENTIAL` yields `CONSISTENT` with a mandatory note that this is
  documented bearer-token behavior; only `EXPIRED_CREDENTIAL_HONORED` is `DIVERGENT`.
- F7 Cross-run aggregation requires matching `compiled_hash`, `adapter_version` and
  `catalog_version`; otherwise `HeterogeneousComparisonError`.
- F8 Aggregation reports n, median, IQR, min, max, and the count of excluded runs with
  reasons. No mean without dispersion; no dispersion below n=5 (report the count instead).

## Non-functional requirements
Scoring under 500 ms for a 10 000-observation bundle. Pure.

## Security requirements
- S1 No CLI flag raises confidence or coverage. `--allow-unsealed` and
  `--allow-heterogeneous` exist and only *lower* it. Asserted by a test that introspects the
  command surface.
- S2 A `DETECTOR_FAILED` category cannot be overridden.

## Tests
`test_scoring.py` asserts: `NOT_MEASURED` never becomes `CONSISTENT`; min-not-mean
aggregation; low coverage forces `PARTIAL`; a composite score is not producible — there is no
function returning a single number over categories, asserted by module introspection.

## Negative controls
Construct a findings set with five HIGH-confidence and one LOW-confidence contributor;
assert the category is LOW. Construct a run exercising two of six categories; assert the
other four are `NOT_MEASURED` and that the rendered output contains the literal sentence
"NOT_MEASURED is not a pass."

## Acceptance criteria
1. All six categories evaluate correctly on fake-provider runs.
2. `NOT_MEASURED` handling verified, including the literal sentence.
3. Confidence min-aggregation verified.
4. Cross-run aggregation refuses heterogeneous inputs.
5. No composite score exists anywhere in the codebase.

## Verification commands
```bash
chainbreak run scenarios/delegation-drift/four-hop.yaml --provider fake --seed 29
chainbreak analyze <run-id> && jq '.categories[]|{category,status,coverage,confidence}' runs/<run-id>/scores.json
pytest -m unit tests/unit/test_scoring.py -q
grep -rn "composite\|overall_score\|total_score" src/ && echo "FAIL: composite found" || echo "no composite score"
```

## Definition of done
Acceptance criteria met; SCORING_MODEL.md updated if a category definition changed;
`PROJECT_STATUS.md` updated.

## Out of scope
Report rendering (M16). Introducing a composite score (requires an ADR superseding ADR-010).

## Risks
Category status quietly becoming a grade. Keep the language descriptive: `CONSISTENT` means
"observed matched intended within the measured scope", not "secure", and the report says so.
