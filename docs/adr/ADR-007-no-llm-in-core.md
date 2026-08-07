# ADR-007: No LLM required in the benchmark core

**Status:** Accepted · **Date:** 2026-08-07

## Context

CHAINBREAK is motivated by agentic systems. The silent-narrowing family measures how a
workload behaves when its authority is insufficient — which is most interesting for an
autonomous agent.

## Decision

v0.1 workloads are deterministic implementations of a `TaskWorker` Protocol. No model call
is made anywhere in the benchmark. Real agent workers are a v0.4 extension implementing the
same Protocol.

## Rationale

A non-deterministic workload would make every measurement non-reproducible, and CHAINBREAK's
value proposition is reproducible evidence. Worse, it would confound the thing being
measured: if an LLM agent silently produces partial output, is that the cloud's
authorization behavior, the agent's behavior, or prompt phrasing? With four of the five
families measuring cloud behavior, adding an uncontrolled variable to the fifth would
contaminate the suite.

The analysis contract is defined over the `TaskOutcome` object rather than over worker
internals, so swapping in an LLM worker later changes nothing downstream. The plumbing is
built now so the comparison — deterministic worker vs. real agent, same scenario, same
contract — is possible later. That comparison is more valuable than an LLM in v0.1 would be.

## Consequences

**Positive.** Reproducible, free, fast, offline-testable. No model dependency, no API key,
no rate limit, no cost.

**Negative.** v0.1's failure-transparency results describe the harness, not real agent
behavior. Stated in the scenario description, in the category result, and in every report
that includes the family. This is a genuine scope limitation, not a hedge.
