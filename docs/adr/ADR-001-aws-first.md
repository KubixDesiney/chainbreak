# ADR-001: AWS-first, single provider for v0.1

**Status:** Accepted · **Date:** 2026-08-07 · **Supersedes:** — · **Superseded by:** —

## Context

CHAINBREAK's roadmap names five identity systems (AWS, OIDC federation, SPIFFE/SPIRE,
Azure, GCP). The temptation is to design for all of them at once so the abstractions are
"validated" from the start.

## Decision

v0.1 implements exactly one provider adapter: AWS, using IAM and STS. No other provider is
implemented, not even partially.

## Rationale

The measurements CHAINBREAK makes depend on details that only exist per-provider: denial
message shapes, the 403/404 ambiguity on object reads, session-policy intersection
semantics, the 3600-second role-chaining cap. An abstraction designed against two providers
in the abstract would encode neither correctly.

AWS specifically because its delegation model (`AssumeRole` + session policies) expresses
attenuation, chaining, and revocation more explicitly than the alternatives, which makes it
the richest single target for the five benchmark families.

A half-built second adapter is worse than none: it makes the abstraction look validated when
it is not, and every subsequent design decision inherits that false confidence.

## Consequences

**Positive.** Correctness per provider. A finishable v0.1. Honest external-validity claims
("this account, this region, this time") rather than implied generality.

**Negative.** The provider abstraction is validated by exactly one implementation plus the
deterministic fake. Mitigated by the shared provider contract test suite, which both must
pass — the fake is a second implementation of the interface even though it is not a second
cloud.

**Obligation.** No CHAINBREAK output may make a cross-provider claim until a second adapter
exists and has run the suite.
