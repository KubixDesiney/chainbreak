# M1 — Domain model and authorization graph

## Purpose
Complete the domain model and implement the divergence algorithms that turn expected and
observed authority into structured statements about where a delegation chain went wrong.

## Dependencies
M0.

## Existing work to preserve
`core/enums.py`, `core/errors.py`, `core/ids.py`, `core/secrets.py`, `core/models.py` and
`tests/unit/test_domain_contract.py` exist and pass. **Extend, do not rewrite.** They are the
authoritative expression of [AUTHORIZATION_MODEL.md](../../../AUTHORIZATION_MODEL.md).

## Required components
`graph/builder.py` (construct an `AuthorizationGraph` from nodes and edges, enforcing
G-1…G-5), `graph/divergence.py` (all algorithms in AUTHORIZATION_MODEL §4),
`graph/paths.py` (root-to-leaf enumeration, per-path analysis), `core/canonical.py`
(canonical JSON: sorted keys, fixed float formatting, UTC ISO-8601 with microseconds).

## Files expected
```
src/chainbreak/graph/{builder,divergence,paths}.py
src/chainbreak/core/canonical.py
tests/unit/{test_divergence,test_first_divergence,test_graph_invariants,test_paths,test_canonical}.py
```

## Functional requirements
- F1 Per-node divergence: `unexpected_gain`, `unexpected_loss`, `agreement`.
- F2 Per-edge divergence: `attenuation_correct`, `survived_incorrectly`,
  `dropped_incorrectly`, computed against the source's **observed** authority, with the
  expected-based variant computed alongside.
- F3 `first_divergence(path)` returning a `DivergencePoint` or `None`, handling unmeasured
  nodes as `UNMEASURED` rather than skipping them.
- F4 Drift classification: `ORIGINATED`, `PROPAGATED`, `AMPLIFIED`, `CORRECTED`.
- F5 `PathAnalysis` with set- and cardinality-monotonicity computed separately.
- F6 Graph invariants G-1…G-5 with per-invariant error messages, and the negative-control
  downgrade path (a listed invariant becomes a recorded warning, not an error).
- F7 Canonical JSON producing byte-identical output for logically identical input.

## Non-functional requirements
Pure functions, no I/O, no logging. A depth-6, 10-capability graph analyzes in under 10 ms.

## Security requirements
- S1 `core/` and `graph/` import nothing from CHAINBREAK beyond `core/` (ARCH-1).
- S2 No model may hold `SecretMaterial` outside `TemporaryCredential`.

## Tests
Table-driven divergence tests over hand-computed cases, **including `CORRECTED`** — a hop
that cleans up upstream drift. A naive implementation misclassifies it as `PROPAGATED`, and
that error would make CHAINBREAK report a working defense-in-depth control as a failure.
Also: branching graphs, single-node graphs, unmeasured nodes, and the AUTHORIZATION_MODEL §7
worked example reproduced exactly.

## Negative controls
Feed a graph where hop 3 gains a capability: assert `first_divergence.hop_index == 3` and
hop 4 classifies `PROPAGATED`, not `ORIGINATED`. Feed a graph where hop 3 gains and hop 4
drops it: assert hop 4 is `CORRECTED`.

## Acceptance criteria
1. Every algorithm in AUTHORIZATION_MODEL §4 implemented and tested.
2. The §7 worked example reproduces exactly, including the drift classes.
3. G-1…G-5 each have a violating fixture that raises with a message naming the invariant.
4. Coverage ≥ 95% on `core/` and `graph/`.
5. Canonical JSON round-trips identically across two processes.

## Verification commands
```bash
pytest -m unit tests/unit/ -q
pytest --cov=chainbreak.core --cov=chainbreak.graph --cov-report=term-missing -m unit
python -c "from chainbreak.core.canonical import dumps; print(dumps({'b':1,'a':2.0}))"
```

## Definition of done
Acceptance criteria met; AUTHORIZATION_MODEL.md updated if any algorithm was refined;
`PROJECT_STATUS.md` updated.

## Out of scope
Scenario parsing. Provider code. Evidence writing. Anything that performs I/O.

## Risks
Subtle set-algebra errors that pass shallow tests. Mitigate with the hand-computed table and
the worked example. Do not "optimize" `AuthoritySet` into raw `frozenset` — canonical
ordering is what makes evidence diffable.
