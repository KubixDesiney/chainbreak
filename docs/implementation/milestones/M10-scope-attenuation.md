# M10 — Scope attenuation benchmark (Family A)

## Purpose
Wire the execution engine end to end for the simplest family: delegate, probe, compare.
Everything M11–M14 adds is a variation on the machinery this milestone builds.

## Dependencies
M7. Runs entirely against the fake provider; AWS execution is M17.

## Required components
`execution/orchestrator.py` (phase loop, deadline, cleanup `finally`),
`execution/matrix.py` (probe matrix execution, trial repetition, seeded order shuffle),
`execution/delegation.py` (walk edges, issue credentials, track lifetimes),
`execution/preconditions.py`, `execution/control.py` (`identity.whoami` calibration).

## Files expected
```
src/chainbreak/execution/{orchestrator,matrix,delegation,preconditions,control}.py
tests/integration/{test_scope_attenuation,test_probe_matrix_execution,test_control_capability}.py
```

## Functional requirements
- F1 Orchestrator: preflight → materialize identities → walk edges → run matrices → cleanup.
- F2 Probe order shuffled with a **recorded seed** (control C-6), so a capability probed last
  does not systematically carry more credential age and throttling pressure.
- F3 Trial repetition with per-trial observations; cell resolution by unanimity.
- F4 `identity.whoami` probed in every matrix; its failure raises
  `ControlCapabilityFailedError` and discards the matrix rather than recording denials.
- F5 Preconditions verified by the provisioning identity before every read matrix.
- F6 Credential lifetime checked before each matrix; re-delegate if remaining lifetime is
  under 2× the estimated matrix duration, recording the re-delegation as an event.
- F7 Concurrency bounded (default 4) and forced to 1 when `timing_sensitive`.

## Non-functional requirements
`scope-attenuation/basic.yaml` against the fake in under 5 s.

## Security requirements
- S1 SI-7: deadline checked at every phase boundary and every matrix.
- S2 Cleanup runs in a `finally`; unreverted state is printed with exact revert commands.
- S3 Write probes confined to `scratch/{run_id}/` — verified by asserting the target path.

## Tests
Full-family integration against the fake with known ground truth: correct attenuation
produces `EXPECTED_BEHAVIOR`; a fake configured to over-grant produces `AUTHORITY_EXPANSION`
at the right node with the right capabilities and confidence `HIGH`.

## Negative controls
`nc-scope-expansion.yaml` and `nc-surviving-authority.yaml` must both be detected. The
second is the important one: it fails if divergence is computed only at node level, because
the node's derived expectation can coincide with the observed set while the *edge*'s intent
was violated.

## Acceptance criteria
1. `scope-attenuation/basic.yaml` runs end to end against the fake and produces a sealed
   bundle plus findings.
2. Both scope-attenuation negative controls detected with the declared confidence.
3. Control-capability failure discards the matrix rather than reporting denials.
4. Probe order seed is recorded and replaying it reproduces the order.
5. Coverage ≥ 90% on `execution/`.

## Verification commands
```bash
chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake --seed 11
chainbreak analyze <run-id> && jq -r '.findings[].type' runs/<run-id>/findings.json
chainbreak run scenarios/_negative-controls/nc-scope-expansion.yaml --provider fake --seed 11
chainbreak run scenarios/_negative-controls/nc-surviving-authority.yaml --provider fake --seed 11
pytest -m integration tests/integration/test_scope_attenuation.py -q
```

## Definition of done
Acceptance criteria met; EXPERIMENT_PROTOCOL §1 updated if the procedure changed;
`PROJECT_STATUS.md` marks Family A implemented **and explicitly notes it has not been run
against AWS**.

## Out of scope
Multi-hop beyond depth 2 (M11). Mutations (M12). AWS.

## Risks
Building orchestration that only works for this family. Design the phase loop against the
full `PhaseKind` enum from the start, even though only `PROBE` is exercised here.
