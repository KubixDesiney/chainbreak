# ADR-011: Timing-sensitive scenarios execute strictly serially

**Status:** Accepted · **Date:** 2026-08-07

## Context

A probe matrix of 6 identities × 10 capabilities × 3 trials is 180 calls. Running them
concurrently would cut wall-clock time substantially, and `asyncio` makes it easy.

## Decision

Scenarios declaring `timing_sensitive: true` must set `concurrency: 1` (enforced by the
schema) and every probe runs serially with recorded inter-probe intervals. Non-timing
scenarios may run a bounded number of probes concurrently, default 4.

## Rationale

Concurrency destroys a timing measurement. The revocation family's resolution is bounded by
the polling interval; if concurrent requests queue behind a shared connection pool, are
throttled together, or are reordered, the observed `t_last_allow` and `t_first_deny` no
longer bracket the true transition — and the error is invisible in the output, which is the
worst kind.

Concurrency would also introduce load the benchmark itself generates, confounding a
measurement whose subject is provider-side propagation under load.

Serial execution costs wall-clock time. A 300-second polling window at 500 ms is 600 calls;
running them serially is the whole point.

The split is scenario-declared rather than global because the authority-axis families
(scope attenuation, delegation drift) are genuinely insensitive to it — a set difference does
not care about ordering — and those are the families with the largest matrices.

## Consequences

**Positive.** Timing measurements mean what they claim. Uncertainty is bounded by a
controlled variable rather than by scheduler behavior.

**Negative.** Longer runs for timing families. Mitigated by `probe_universe: declared`,
which narrows the timing scenarios' matrices to the capability actually under test.
