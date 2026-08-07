# ADR-013: Provider identifiers are salted-hashed in evidence, not omitted

**Status:** Accepted · **Date:** 2026-08-07

## Context

Evidence must let an analyst tell that two observations targeted the same resource, or were
produced by the same credential. It must not disclose the operator's account structure when
published (T-13).

## Decision

Every provider identifier (ARN, account ID, region, session name, access key ID, resource
URL) is stored as `sha256(run_salt + value)` where `run_salt` is derived from the run ID.
The identifiers are never stored in cleartext. Denial *messages* are redacted in place —
ARNs replaced with `<REDACTED_ARN>` — rather than dropped.

## Rationale

Omitting identifiers entirely would break correlation: the analysis could not tell whether
two probes hit the same target, and `identity_ref_hash` is how graph nodes are matched to
observations. Storing them in cleartext would make bundles unpublishable.

Salted hashing preserves equality relationships within a bundle while disclosing no
identifier. Because the salt is per-run, hashes do not correlate across bundles, so
publishing many runs does not accumulate into a fingerprint of the environment.

Messages are redacted in place because the *sentence shape* is what carries the explicit-vs-
implicit denial attribution. Dropping the field would destroy the ability to distinguish
`DENIED_EXPLICIT` from `DENIED_IMPLICIT`, which several findings depend on. A digest of the
original message is stored alongside, so two runs can be compared for message identity
without either storing the original.

**The honest limitation** (residual risk R-14): the salt derives from the run ID, which is
present in the bundle. An adversary who already has a candidate ARN can confirm it by
recomputing. Bundles therefore disclose *equality relationships*, not identifiers. This is
documented rather than hidden, because a reader who assumed otherwise would be misled.

## Consequences

**Positive.** Bundles are publishable. Correlation works. Denial attribution survives.

**Negative.** Confirmable against a known candidate. Debugging is harder — mitigated by
`--debug-unhashed`, which is refused unless the provider is `fake`.
