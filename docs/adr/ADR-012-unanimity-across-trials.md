# ADR-012: A probe cell is ALLOWED only if every trial was ALLOWED

**Status:** Accepted · **Date:** 2026-08-07

## Context

Each (identity, capability) cell runs `trials` times, default 3. The trials can disagree —
throttling, a transient 5xx, a connection reset. Something must decide the cell's value.

## Decision

Unanimity. All trials `ALLOWED` ⇒ cell is `ALLOWED`. All denials ⇒ the denial (or
`DENIED_UNATTRIBUTED` if attributions differ). All errors ⇒ that error. Anything mixed ⇒
`INDETERMINATE`, with the full trial vector recorded.

Majority voting is explicitly rejected.

## Rationale

The failure modes are asymmetric. A transient error misread as a denial produces a false
`AUTHORITY_NARROWING` — a claim that authority is missing when it is not. A transient error
misread as an allow produces a false `AUTHORITY_EXPANSION` — a claim that authority exists
when it does not. The second is the more damaging error for a security benchmark, since it
manufactures an alarming finding out of noise.

Unanimity makes both harder and, crucially, makes disagreement *visible* as `INDETERMINATE`
rather than smoothing it into a confident value. With 3 trials, majority voting would let a
single anomalous result be outvoted and disappear from the record. Under unanimity it
surfaces, is excluded from the authority set, is counted in the exclusion table, and lowers
the confidence of anything derived from it.

This is the same principle as reporting timing as an interval: where the data is ambiguous,
the output should be ambiguous.

## Consequences

**Positive.** No finding is built on a noisy cell. Disagreement is recorded, not hidden.
Coverage naturally drops when the environment is unreliable, which is the correct signal.

**Negative.** More `INDETERMINATE` cells in a throttled environment, lowering coverage and
therefore confidence. Correct behavior: a flaky measurement *should* report low confidence.
