# ADR-014: Negative controls are a first-class scenario feature, not a convention

**Status:** Accepted · **Date:** 2026-08-07

## Context

A benchmark that only ever reports PASS has not demonstrated it can detect a failure. The
usual approach is a set of "known bad" test fixtures maintained beside the real tests.

## Decision

`negative_control` is a block in the scenario schema. It declares the injected defect kind,
a rationale, and an `expect_finding` the run **must** produce. The harness asserts the
declared finding appeared; if it did not, CHAINBREAK emits `DETECTOR_FAILURE` — a
first-class finding type — and the block's positive results are marked unvalidated.

Every `NegativeControlKind` must be covered by at least one shipped scenario, asserted by
`tests/scenarios/test_scenario_corpus.py`.

## Rationale

Making this a schema feature rather than a convention buys three things a fixture directory
does not.

First, the graph invariant downgrade is principled. A negative control deliberately violates
G-3 (intent exceeds parent). `suppress_graph_check: [G-3]` downgrades that one check for
that one scenario, rather than requiring a global flag that would weaken every scenario.

Second, `DETECTOR_FAILURE` is the only finding type that says something about CHAINBREAK
rather than about the system under test. Having it in the taxonomy means a detector
regression appears in the same output stream as everything else, at the same severity as a
real finding, and blocks publication via the checklist.

Third, the declared `expect_finding` documents intent. A reader of
`nc-surviving-authority.yaml` can see exactly which detector it validates and why the defect
is injected through the role's identity policy rather than the session policy — which
matters, because session policies intersect and cannot grant, so injecting there would
validate nothing.

## Consequences

**Positive.** Detector coverage is machine-checkable. A regression in the analysis layer is
caught by the negative-control integration suite, which is a merge gate.

**Negative.** Extra Terraform (deliberately-defective roles behind
`enable_negative_controls`) and extra run time in every experiment block. Both required:
a control applied to different infrastructure than the scenarios it validates proves less.
