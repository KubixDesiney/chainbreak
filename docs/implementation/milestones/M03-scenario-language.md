# M3 — Scenario language, validation and compiler

## Purpose
Complete the five-stage validation pipeline and implement the compiler that turns a scenario
document into a `CompiledScenario`: authorization graph, probe matrices, ordered plan, and a
deterministic `compiled_hash`.

## Dependencies
M2.

## Existing work to preserve
`scenarios/schema.py` (full v1alpha1 Pydantic model), `scenarios/safety.py` (stage 5 plus the
restricted loader), `scenarios/export_schema.py`, `schemas/scenario.v1alpha1.schema.json`,
12 scenario files, `tests/scenarios/test_scenario_corpus.py`. All pass. Extend.

## Required components
`scenarios/loader.py` (orchestrates stages 1–5, collecting all failures per stage before
stopping), `scenarios/compiler.py`, `scenarios/policy_synthesis.py` (provider-neutral
interface for deriving a session policy from a capability set), `scenarios/plan.py`
(`PlanStep` ordering including auto-inserted `SNAPSHOT` phases).

## Files expected
```
src/chainbreak/scenarios/{loader,compiler,policy_synthesis,plan}.py
src/chainbreak/core/models.py                     # add CompiledScenario, ProbeMatrix, PlanStep
tests/unit/{test_scenario_loader,test_scenario_compiler,test_probe_matrix,test_scenario_safety}.py
tests/fixtures/scenarios/                          # one invalid fixture per failure mode
```

## Functional requirements
- F1 Five stages with distinct exit codes: 0 valid, 2 schema/structural, 3 semantic,
  4 binding, 5 safety. All failures within a stage reported before stopping.
- F2 Expected-authority derivation: `node.expected = parent.expected ∩ edge.intended`
  (intersection, not assignment). If `expect_capabilities` is also declared, assert
  agreement and fail naming both values.
- F3 Probe matrix construction honoring `probe_universe`: `declared` (node's expected),
  `scenario` (union of all capabilities the scenario names — the default), `catalog` (all).
  `identity.whoami` is added to every universe.
- F4 A `SNAPSHOT` phase is auto-inserted immediately before and after every `MUTATE`.
- F5 `compiled_hash` = SHA-256 over canonical spec + catalog version + adapter version.
  Byte-identical for identical input across processes.
- F6 Negative-control handling: listed invariants downgrade to `CompileWarning`; the
  `expect_finding` is carried into the compiled artifact for the harness to assert.
- F7 Session-policy synthesis produces a document under the provider's size limit; exceeding
  it is a **compile-time** error naming the limit, not a runtime failure.

## Non-functional requirements
Compilation of a depth-6 scenario under 100 ms. Pure and deterministic.

## Security requirements
- S1 SI-11 stage 5 runs even in `--offline` and cannot be skipped by any flag.
- S2 An inline session policy referencing a resource outside the namespace is a compile error.

## Tests
Determinism (compile twice in separate processes, compare hashes). Every invalid fixture
produces the expected exit code and message. Probe universe correctness — in particular that
`scenario` universe includes capabilities the node is *not* expected to hold, since that is
what makes expansion detectable.

## Negative controls
Compile `nc-scope-expansion.yaml`: assert G-3 is downgraded to a warning and the run
proceeds. Remove `suppress_graph_check`: assert compilation now fails. Craft a scenario whose
`expect_capabilities` contradicts the derived value: assert the error names both.

## Acceptance criteria
1. All 12 shipped scenarios compile; `chainbreak scenario validate` exits 0 for each.
2. Each invalid fixture yields its documented exit code.
3. `compiled_hash` is stable across processes and changes when the catalog version changes.
4. `nc-*` scenarios compile with warnings, not errors.
5. Coverage ≥ 90% on `scenarios/`.

## Verification commands
```bash
pytest -m unit tests/unit/test_scenario_compiler.py tests/scenarios/ -q
for f in scenarios/**/*.yaml; do chainbreak scenario validate "$f" || echo "FAIL $f"; done
python -c "from chainbreak.scenarios.loader import load_and_compile as c; import sys; \
  print(c('scenarios/delegation-drift/four-hop.yaml').compiled_hash)"
```

## Definition of done
Acceptance criteria met; SCENARIO_SPECIFICATION.md updated if the schema changed *and*
`schemas/` regenerated; `PROJECT_STATUS.md` updated.

## Out of scope
Executing anything. Provider bindings. Actual session-policy JSON (that is AWS-specific,
M8) — M3 defines the interface and the size check.

## Risks
Non-determinism creeping into `compiled_hash` via dict ordering or float formatting. Use
`core/canonical.py` from M1 exclusively; never `json.dumps` directly.
