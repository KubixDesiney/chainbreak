# Scenarios

Declarative authorization experiments. Format: [`chainbreak.dev/v1alpha1`](../SCENARIO_SPECIFICATION.md).

## Layout

| Directory | Family | Files |
|---|---|---|
| `scope-attenuation/` | Does a delegated identity ever exceed its hop's grant? | `basic.yaml` |
| `delegation-drift/` | Where does a multi-hop chain first diverge? | `four-hop.yaml` |
| `revocation/` | How long does authority survive a policy change? | `inline-deny.yaml`, `trust-policy-null-condition.yaml` |
| `stale-authority/` | Does deferred execution use current or historical authority? | `deferred-execution.yaml` |
| `silent-narrowing/` | Does a workload fail observably when authority is short? | `two-step-pipeline.yaml` |
| `_negative-controls/` | Scenarios that **must** produce a finding | six files, one per defect kind |

## Reading a scenario

Two fields are easy to confuse and carry different meanings:

- `delegations[].intended_capabilities` — a **design statement**: what this hop is meant to
  grant. Expected authority is *derived* from it as `parent.expected ∩ intended`.
- `expectations[].allow` / `.deny` — **assertions** the analysis checks. Redundant by design,
  because a reviewer must be able to read a scenario and state what it claims.

The `deny` list is mandatory on `node_authority`. You cannot detect authority expansion by
listing only what should be allowed.

## Two scenarios that look like failures but are not

`revocation/trust-policy-null-condition.yaml` expects **no** transition. A trust policy gates
credential issuance, not the use of an already-issued credential, so a live session should be
unaffected. It is control C-5: if CHAINBREAK reports a fast transition there, the apparatus is
wrong and the whole block is discarded. Run it in every revocation block.

`_negative-controls/nc-no-revocation.yaml` also expects no transition, for a different reason:
the mutation targets an identity that is not the one being polled. Its purpose is to confirm
the harness reports an honest negative rather than manufacturing a transition.

## Negative controls

Each declares `negative_control.expect_finding`. After analysis the harness asserts the
declared finding was produced; if it was not, CHAINBREAK emits `DETECTOR_FAILURE` and every
positive result in the same block is unvalidated.

They live in their own directory *and* are marked in the schema *and* must use an `nc-` id
prefix — three redundant signals, because a reviewer mistaking a negative control for a health
check would misread the entire suite. `tests/scenarios/test_scenario_corpus.py` asserts all
three agree.

## Rules for a new scenario

1. No ARNs, account IDs, regions or external URLs. Reference infrastructure only through
   `provider_binding.terraform_output`. This is what makes a scenario safe to publish.
2. A `deny` list on every `node_authority` expectation.
3. `timing_sensitive: true` requires `concurrency: 1`.
4. An assertive `revocation_within` expectation requires a written justification —
   CHAINBREAK does not assert normative propagation times without one.
5. Each depth variant is its own file, so `compiled_hash` differs and results cannot be
   accidentally pooled.
6. A new detection pattern needs a matching negative control.

Validate with `chainbreak scenario validate <file>`. Exit codes: 2 schema, 3 semantic,
4 binding, 5 safety.
