# ADR-006: Observation is separated from security conclusion

**Status:** Accepted · **Date:** 2026-08-07

## Context

The natural output of a security tool is a list of problems. It would be simpler to have
probes emit findings directly.

## Decision

`Observation` and `Finding` are different objects with different lifetimes. Observations are
immutable and written by `run`. Findings are derived by `analyze`, a pure function over a
sealed bundle, and can be regenerated. `findings.json` can be deleted; `observations.jsonl`
cannot be reconstructed.

Within a `Finding`, `observation`, `expected_state`, `observed_state` and
`security_interpretation` are separate fields, rendered under separate headings.

## Rationale

The distinction is the project's central methodological commitment. "Authorization remained
effective for 37.2–39.0 s after the policy change request" is data. "AWS has broken
revocation" is an unsupported claim that generalizes from one account and ignores documented
eventual consistency. A structure that stores them in the same string invites the second.

Separation also means analysis can improve without re-running experiments. When a
classification is later found to be wrong, `disambiguation_path` identifies every affected
observation and historical bundles can be re-analyzed correctly. In a benchmark whose
measurements are expensive and environment-dependent, that is worth a great deal.

## Consequences

**Positive.** Re-analyzable evidence. Language discipline enforced structurally rather than
by good intentions — the report language lint (`test_report_language.py`) has separate
fields to check. Third parties can disagree with our interpretation while accepting our data.

**Negative.** Two commands (`run`, then `analyze`) where a user might expect one. Accepted:
the CLI prints the `analyze` command on run completion.
