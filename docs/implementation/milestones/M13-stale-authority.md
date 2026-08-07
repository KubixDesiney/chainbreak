# M13 — Stale authority benchmark (Family D)

## Purpose
Implement deferred execution against a pinned credential, and the paired fresh-credential
comparison that makes the result interpretable.

## Dependencies
M12.

## Required components
`execution/deferred.py` (credential pinning and reuse, virtual-clock-aware waiting),
`execution/credential_store.py` (per-phase credential registry),
`analysis/stale.py` (the six-row classification).

## Files expected
```
src/chainbreak/execution/{deferred,credential_store}.py
src/chainbreak/analysis/stale.py
scenarios/stale-authority/{short-defer,long-defer,post-expiry}.yaml
tests/integration/{test_stale_authority,test_credential_pinning,test_post_expiry}.py
```

## Functional requirements
- F1 `credential_source: phase:<name>` resolves to the credential minted at that phase; the
  deferred probe uses it without refresh.
- F2 `WAIT` phases do not touch the credential — no keepalive, no refresh. The waiting is the
  experiment.
- F3 Immediately after the deferred probe, the same capability is probed with a **freshly
  minted** credential. The pair is the measurement.
- F4 Classification per the six-row table, requiring both outcomes.
- F5 `EXPIRED_CREDENTIAL_HONORED` is a distinct, high-severity classification — it is the one
  outcome contradicting documented provider behavior.
- F6 Deferral intervals as an independent variable {30, 120, 600} s.
- F7 Post-expiry scenario: let a credential pass `expires_at` and probe, testing H6.

## Non-functional requirements
Real waits against AWS; virtual-clock waits against the fake so a 600 s deferral test runs
instantly in CI while the measurement code still uses the clock abstraction.

## Security requirements
- S1 A pinned credential is still scrubbed at run end.
- S2 Credential store is in-memory only; never serialized (EV-1).
- S3 SI-7 deadline accounts for deferral time — a 600 s deferral inside a 900 s run must not
  silently truncate the experiment.

## Tests
`test_credential_pinning.py` asserts the deferred probe used the pinned credential ID and not
a fresh one — verified from the evidence stream, not from the code path, so a refactor cannot
silently break it.

## Negative controls
`nc-stale-credential-reuse.yaml`. Critically, also test the *ambiguous* case: fake configured
so the policy change has not propagated at all. Both probes succeed, and the correct
classification is "not propagated", **not** stale authority. A harness that ignores the pair
conflates these, and this test is what catches that.

## Acceptance criteria
1. All six classifications reachable and tested against the fake.
2. Credential pinning verified from evidence.
3. The ambiguous case classifies as "not propagated", not as stale authority.
4. Post-expiry scenario correctly yields `CREDENTIAL_EXPIRED`.
5. Reports state that stale authority on a live bearer token is documented behavior, in the
   same paragraph as the result.

## Verification commands
```bash
chainbreak run scenarios/stale-authority/deferred-execution.yaml --provider fake --fake-profile eventual --seed 13
chainbreak analyze <run-id> && jq '.findings[]|select(.type=="STALE_AUTHORITY")' runs/<run-id>/findings.json
chainbreak run scenarios/_negative-controls/nc-stale-credential-reuse.yaml --provider fake --seed 13
pytest -m integration tests/integration/test_stale_authority.py -q
```

## Definition of done
Acceptance criteria met; AUTHORIZATION_MODEL §5.2 updated if the table changed;
`PROJECT_STATUS.md` updated.

## Out of scope
AWS. Real long waits in CI.

## Risks
Omitting the paired fresh credential would make every result ambiguous and the family
worthless. It is F3 for a reason.
