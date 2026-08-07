# ADR-010: No composite security score in v0.1

**Status:** Accepted · **Date:** 2026-08-07

## Context

Benchmarks are expected to produce a number. A single score would make results comparable at
a glance and would be excellent for a portfolio demonstration.

## Decision

CHAINBREAK emits six independent `CategoryResult`s, each with its own status, measurements,
coverage and confidence. No composite score. `SCORING_MODEL.md §6` states the five
conditions under which one could be introduced, and doing so requires an ADR superseding
this one.

## Rationale

A composite would weight incommensurable quantities — a set difference, a duration, and a
behavioral classification — with weights we would have invented. Any reader could reasonably
disagree, and the score would then be doing rhetorical rather than analytical work.

It also destroys the useful information. "Score 72/100" tells an engineer nothing. "Hop 3
grants `keyvalue.read` that hop 3's session policy did not intend; confidence HIGH; probe
IDs obs_… obs_… obs_…" tells them what to fix.

And a published score invites comparison, comparison invites gaming, and a gamed security
benchmark produces worse security. A benchmark that publishes measurements invites
replication instead.

`CONSISTENT` is likewise a description of a measurement, not a grade. It does not mean
"secure", and every report says so. `NOT_MEASURED` is rendered with the literal sentence
"NOT_MEASURED is not a pass", because the most common way a benchmark misleads is by letting
absence of measurement read as absence of problems.

## Consequences

**Positive.** Nothing is overclaimed. Raw measurements stay visible. Category results remain
actionable.

**Negative.** Harder to summarize in a headline; less immediately impressive. Accepted —
defensibility under technical questioning is worth more here than a memorable number.
