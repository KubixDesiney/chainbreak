# ADR-008: Provider adapters behind a Protocol, with a shared contract test suite

**Status:** Accepted · **Date:** 2026-08-07

## Context

The engine needs to delegate, probe, mutate and snapshot. Those operations are inherently
provider-specific.

## Decision

A `ProviderAdapter` Protocol defines seven methods. Two implementations ship in v0.1: `aws`
and `fake`. A shared contract test suite lives in `tests/integration/test_provider_contract.py`
and **both must pass it unmodified** — the fake in every CI run, AWS in the opt-in layer.

## Rationale

A Protocol alone does not keep implementations honest; it only keeps signatures aligned. The
contract suite is what actually enforces behavioral equivalence: preflight rejects a wrong
account, out-of-namespace targets are refused before the call, every capability classifies
allow and deny correctly, delegation returns metadata without secrets, mutation returns a
confirmed receipt, lifetime capping is reported.

This is also what makes the fake provider trustworthy enough to develop against. If the fake
passes the same behavioral suite as AWS, a finding the fake produces incorrectly is an
analysis bug — discoverable in CI, in under a second, without a cloud account. Four of the
five families are developable entirely offline as a result.

The rule that matters most: **never weaken a contract test to make an adapter pass.** That
is the single change that would make the whole apparatus untrustworthy, and CONTRIBUTING.md
says so explicitly.

## Consequences

**Positive.** Offline development of every analysis path. New adapters have an objective
admission criterion. Fake-vs-real differential testing (control C-9) falls out for free.

**Negative.** The fake provider is real software — a policy evaluation model with explicit
deny precedence, credential lifetimes, an injectable consistency model and fault injection.
That is a meaningful implementation cost, and it is the right one.
