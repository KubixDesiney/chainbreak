# ADR-003: Declarative YAML scenarios, not a Python DSL

**Status:** Accepted · **Date:** 2026-08-07

## Context

Scenarios must express identities, delegations, phases, tasks and expectations. A Python DSL
would be more expressive and easier to write.

## Decision

Scenarios are YAML documents validated by a JSON Schema and a Pydantic model, loaded with a
restricted `SafeLoader` subclass that rejects unknown tags outright.

## Rationale

Two reasons, one security and one epistemic.

**Security.** The project intends scenarios to be shareable — that is how a benchmark gets
replicated. A DSL makes a shared scenario *executable code*, turning malicious scenario input
(T-09) from a parsing problem into a code-execution problem. Declarative data with a
restricted loader keeps it a parsing problem, and parsing problems can be bounded with size
caps, node caps, and depth caps.

**Epistemic.** A reviewer must be able to read a scenario and state what it asserts without
running it. A DSL with helper functions, loops and inheritance defeats that. Security
artifacts that require execution to understand do not get reviewed.

The expressiveness loss is real and accepted. Repetition across scenario files is the price
of reviewability, and it is a price worth paying for a research artifact.

## Consequences

**Positive.** Untrusted scenarios are safe to validate. Scenarios are diffable, reviewable,
and publishable. Compilation is pure, so `compiled_hash` is meaningful.

**Negative.** Verbose files with repetition between depth variants. Complex parameterization
(e.g. depth 2–6) requires separate files — which is arguably correct anyway, since each
depth must have a distinct `compiled_hash` so results are never accidentally pooled.
