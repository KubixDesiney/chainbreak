# M12 — Revocation propagation benchmark (Family C)

## Purpose
Implement mutation phases, serial polling, and interval mathematics with honest uncertainty.
The first family whose output is a measurement rather than a comparison.

## Dependencies
M11.

## Required components
`execution/mutation.py`, `execution/polling.py` (serial poller with stability detection),
`analysis/timing.py` extensions (window computation, oscillation handling),
`execution/revert.py` (mutation reversion with a pre-written revert log).

## Files expected
```
src/chainbreak/execution/{mutation,polling,revert}.py
scenarios/revocation/{remove-policy,revoke-older-sessions,delete-session-scope}.yaml
tests/integration/{test_revocation,test_polling,test_revert}.py
tests/unit/test_revocation_math.py
```

## Functional requirements
- F1 All five mutation kinds; mechanism recorded with every measurement.
- F2 Serial polling at the configured interval (floor 100 ms) with stability detection
  (`STABLE_DENIAL` / `STABLE_ALLOW` / `TIMEOUT`) and a per-poll RTT record.
- F3 Warm baseline before mutation: poll to stable allow so the first post-mutation poll is
  not systematically slower than the rest.
- F4 `t_M` = monotonic send instant; confirmation latency recorded separately; an unconfirmed
  mutation makes the measurement `INCONCLUSIVE`.
- F5 Window `[t_last_allow − t_M, t_first_deny − t_M]`, midpoint estimate, half-width.
  **No scalar representation anywhere.**
- F6 `NON_MONOTONIC_TRANSITION` preserved with the full timeline, never smoothed.
- F7 `NO_TRANSITION_OBSERVED_WITHIN_WINDOW` with the window length — an honest negative, not
  a pass.
- F8 Reversion in a `finally`, with the revert log written **before** each mutation so a
  SIGKILL still leaves recovery information (T-06, R-7).
- F9 Between trials: revert, confirm, and wait for stable allow before the next mutation.

## Non-functional requirements
Polling overhead under 5% of the interval. A 300 s window with 600 polls must not accumulate
drift.

## Security requirements
- S1 SI-12: mutations refuse `bootstrap` and `principal`.
- S2 SI-2: mutation targets namespace-asserted before the call.
- S3 The revert log is human-actionable: exact commands, not just identifiers.

## Tests
`test_known_truth_timing.py` from M7 extended across profiles: fake
`propagation_delay_ms ∈ {0, 500, 2000, 10000}`; the measured window must contain the true
value in every case. This is the only place the interval math can be validated against a
known answer, so it is the most important test in the milestone.

## Negative controls
`nc-no-revocation.yaml` (mutation on the wrong identity) must yield
`NO_TRANSITION_OBSERVED`. `revocation/trust-policy-null-condition.yaml` must show **no**
transition — control C-5. Fake oscillation mode must produce `NON_MONOTONIC_TRANSITION`.

## Acceptance criteria
1. All five mechanisms execute and are recorded with their measurements.
2. Known-truth timing tests pass at all four delay settings.
3. Both negative controls behave as declared.
4. A killed run leaves a complete, actionable revert log.
5. No scalar timing value appears in any output (asserted by a test over `findings.json`).

## Verification commands
```bash
chainbreak run scenarios/revocation/inline-deny.yaml --provider fake --fake-profile eventual --seed 5
chainbreak analyze <run-id> && jq '.findings[]|select(.type=="REVOCATION_DELAY")' runs/<run-id>/findings.json
chainbreak run scenarios/revocation/trust-policy-null-condition.yaml --provider fake --seed 5
chainbreak run scenarios/_negative-controls/nc-no-revocation.yaml --provider fake --seed 5
pytest -m integration tests/integration/test_revocation.py -q
```

## Definition of done
Acceptance criteria met; EXPERIMENT_PROTOCOL §3 updated if the procedure changed;
`PROJECT_STATUS.md` states plainly that no AWS revocation measurement exists yet.

## Out of scope
AWS measurement (M17). Cross-run aggregation (M18).

## Risks
Reporting a scalar. Treating eventual consistency as a defect. Losing a `NON_MONOTONIC`
result to well-intentioned smoothing. All three are guarded by tests; do not relax them.
