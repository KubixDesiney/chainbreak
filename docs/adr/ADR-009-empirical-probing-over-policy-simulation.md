# ADR-009: Empirical probing is ground truth; policy simulation is corroboration only

**Status:** Accepted · **Date:** 2026-08-07

## Context

AWS offers `iam:SimulatePrincipalPolicy`, which evaluates whether a principal would be
allowed an action. It is cheap, fast, needs no resources, and returns a clean verdict.
Building CHAINBREAK on it would be far simpler than provisioning buckets and markers.

## Decision

Effective authority is determined by **executing a benign action against a benchmark-owned
resource and classifying the response**. Simulation results, when enabled, are stored in a
separate `simulations.jsonl` and never contribute to `ObservedAuthority`.

## Rationale

Simulation answers "what does the policy evaluator say about this request as I described
it". Probing answers "what happened". Those differ whenever the description is incomplete —
and it usually is. Simulation does not fully account for session policies as actually
issued, for resource policies, for service-specific authorization behavior, or for the
propagation state at this instant. The revocation family in particular is *about* the gap
between the control plane's state and the data plane's behavior, which simulation by
construction cannot observe.

There is a subtler reason. A benchmark built on simulation would measure AWS's policy
evaluator against AWS's policy evaluator. The finding would be tautological. Probing puts an
independent observation between the policy and the conclusion.

Simulation is retained as a diagnostic because disagreement between simulation and empirical
result is itself informative: it localizes whether a surprise is in the policy or in the
propagation.

## Consequences

**Positive.** Ground truth is what actually happened. The revocation and stale-authority
families become measurable at all.

**Negative.** Requires provisioned resources, markers, precondition verification and
response disambiguation — most of the complexity in the AWS adapter. Probes cost fractions
of a cent and take real time. Both accepted; the alternative measures the wrong thing.
