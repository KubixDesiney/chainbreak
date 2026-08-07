# M2 — Capability model and catalog

## Purpose
Complete the capability layer: catalog loading, binding validation, resolution, and the
runtime operation-allowlist mechanism that makes SI-3 enforceable rather than aspirational.

## Dependencies
M1.

## Existing work to preserve
`capabilities/catalog.yaml` (10 capabilities, version 1.0.0) and `capabilities/loader.py`
(`load_catalog`, `resolve_bindings`, `validate_binding`, `assert_no_dangerous`) exist and
pass tests. Extend.

## Required components
`capabilities/registry.py` (per-provider binding registry with registration and lookup),
`capabilities/guard.py` (`OperationAllowlist` — records invoked operations during a probe
and asserts the set is a subset of the binding's declared actions),
`capabilities/preconditions.py` (precondition declarations and the verification interface
the executor calls with the provisioning identity).

## Files expected
```
src/chainbreak/capabilities/{registry,guard,preconditions}.py
tests/unit/{test_capability_catalog,test_binding_validator,test_operation_allowlist,test_catalog_safety}.py
tests/fixtures/bad_bindings.py
```

## Functional requirements
- F1 Registry keyed by `(provider, capability_id)`; duplicate registration is an error.
- F2 `resolve_bindings` raises `CapabilityResolutionError` naming every missing capability
  (CAP-1). Never a silent skip, never a partial result.
- F3 `OperationAllowlist` context manager: records operations, and on exit raises
  `CapabilityBroadeningError` if any operation is outside the binding's `actions`.
- F4 Precondition declarations resolve to verifier callables; a failed precondition yields
  `ERROR_INFRASTRUCTURE` for the whole matrix, never a set of denials.
- F5 `assert_no_dangerous` requires both config and CLI switches (SI-9).

## Non-functional requirements
Catalog load under 50 ms. `OperationAllowlist` adds under 1 ms per probe.

## Security requirements
- S1 SI-3: the allowlist is the enforcement mechanism. In the AWS adapter it will be wired
  to a botocore `before-call` hook (M8); design the interface for that now.
- S2 SI-9: two independent switches in two different places.
- S3 The catalog loader rejects unknown YAML tags.

## Tests
`bad_bindings.py` provides an over-broad binding (extra action), a wrong-provider binding, a
wrong-probe-kind binding, and one omitting a required precondition. Each must be rejected
with a specific message. `test_operation_allowlist.py` asserts an unlisted operation raises,
and that the raise happens even when the probe itself would have "succeeded".

## Negative controls
Register a binding declaring `actions=["fake:Read"]` whose probe invokes `fake:Write`;
assert `CapabilityBroadeningError`. Add a `DANGEROUS` capability to a test catalog; assert
loading fails without both switches and succeeds with both.

## Acceptance criteria
1. All 10 capabilities load, validate and resolve against a test binding set.
2. Every `bad_bindings.py` fixture is rejected with a message naming the problem.
3. The operation allowlist catches a broadening probe.
4. The shipped catalog contains zero `DANGEROUS` entries (asserted).
5. Coverage ≥ 90% on `capabilities/`.

## Verification commands
```bash
pytest -m unit tests/unit/test_capability_catalog.py tests/unit/test_binding_validator.py \
  tests/unit/test_operation_allowlist.py tests/unit/test_catalog_safety.py -q
python -c "from chainbreak.capabilities.loader import load_catalog; c=load_catalog(); print(c.version, len(c.capabilities), c.dangerous())"
```

## Definition of done
Acceptance criteria met; CAPABILITY_MODEL.md updated if the binding interface changed;
`PROJECT_STATUS.md` updated.

## Out of scope
AWS or fake bindings (M5, M8). Probe implementations. Adding capabilities.

## Risks
Making the allowlist too coarse to catch a real broadening. Verify with the negative control,
not by inspection.
