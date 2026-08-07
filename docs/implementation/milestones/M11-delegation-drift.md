# M11 — Delegation drift benchmark (Family B)

## Purpose
Extend to multi-hop chains, implement per-hop attribution and drift classification, and make
depth a first-class experimental variable.

## Dependencies
M10.

## Required components
`execution/chain.py` (multi-hop walking with per-hop credential tracking),
`analysis/drift.py` (drift classification and per-path attribution), depth-parameterized
scenarios.

## Files expected
```
src/chainbreak/execution/chain.py
src/chainbreak/analysis/drift.py
scenarios/delegation-drift/{two-hop,three-hop,five-hop,six-hop}.yaml   # four-hop exists
tests/integration/{test_delegation_drift,test_depth_sweep}.py
```

## Functional requirements
- F1 Chains to `max_delegation_depth` (6), with the chained-role duration cap surfaced as
  `LIFETIME_CAPPED` at every affected hop.
- F2 Per-hop gain/loss vectors and drift classification (`ORIGINATED`, `PROPAGATED`,
  `AMPLIFIED`, `CORRECTED`).
- F3 First divergence reported **per root-to-leaf path**, not per graph.
- F4 A `DELEGATION_DRIFT` finding at a propagated hop cites the originating finding as its
  cause, and the report does not raise an independent alarm downstream.
- F5 Depth sweep: each depth is a separate scenario file with a distinct `compiled_hash`, so
  results cannot be accidentally pooled.
- F6 Divergence reported as a **rate per hop**, with the excluded-trial count per depth
  alongside — depth and total probe count are confounded, and the analysis must expose that.

## Non-functional requirements
A depth-6 run against the fake under 15 s.

## Security requirements
- S1 Depth bounded by `SafetyEnvelope.max_delegation_depth`; exceeding it is a compile error.
- S2 Each hop's credential tracked and scrubbed independently.

## Tests
The AUTHORIZATION_MODEL §7 worked example reproduced end to end: divergence at hop 3
classified `ORIGINATED`, hop 4 `PROPAGATED`, first divergence reported as hop 3, and hop 4's
finding citing hop 3.

## Negative controls
`nc-non-monotone-chain.yaml` must be detected. Additionally construct a fake configuration
where hop 3 gains and hop 4 drops the same capability, and assert hop 4 classifies
`CORRECTED` — a benchmark that reports that as a failure would flag working defense-in-depth
as a problem.

## Acceptance criteria
1. Depths 2–6 all run against the fake and produce correct per-hop attribution.
2. `nc-non-monotone-chain` detected; the `CORRECTED` case classified correctly.
3. First divergence is per path and correct for a branching graph.
4. Depth sweep output includes divergence rate per hop and exclusions per depth.
5. Downstream propagated findings cite their cause rather than duplicating the alarm.

## Verification commands
```bash
for d in two three four five six; do
  chainbreak run scenarios/delegation-drift/$d-hop.yaml --provider fake --seed 23 || break
done
chainbreak analyze --aggregate --scenario-family delegation-drift
pytest -m integration tests/integration/test_depth_sweep.py -q
```

## Definition of done
Acceptance criteria met; RESEARCH_METHODOLOGY H8/RQ5 notes updated with the confound
treatment actually implemented; `PROJECT_STATUS.md` updated.

## Out of scope
Mutations, timing, tasks, AWS.

## Risks
The depth/probe-count confound is easy to ignore and would produce a spurious "deeper chains
drift more" result. F6 is not optional.
