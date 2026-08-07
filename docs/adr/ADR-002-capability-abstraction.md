# ADR-002: Capability abstraction instead of provider permission strings

**Status:** Accepted · **Date:** 2026-08-07

## Context

The obvious representation of "what an identity can do" is a set of provider action strings
(`s3:GetObject`). Divergence would then be a set difference over strings.

## Decision

Authority is modeled as a set of abstract **capabilities** (`objectstore.read`). Provider
action strings appear only inside provider adapter bindings.

## Rationale

`s3:GetObject` is not a unit of authority. Its effect depends on the resource ARN, the
condition block, the bucket policy, and whether the caller also holds `s3:ListBucket` —
which changes the *error code* on a missing key and therefore changes what the benchmark can
conclude. Diffing action strings produces syntactically tidy, semantically meaningless
results.

A capability is defined by an *observable, benign, verifiable operation*. That definition
forces every unit of authority to be testable, which is the property the entire measurement
approach rests on: if you cannot probe it, it is not a capability, and CHAINBREAK will not
pretend to measure it.

The cross-provider benefit is real but secondary. The primary benefit is that the capability
definition and the probe definition are the same act.

## Consequences

**Positive.** Every capability is testable by construction. The engine has no AWS knowledge
(ARCH-1). Cross-provider comparison becomes possible later.

**Negative.** A translation layer to maintain and keep honest, enforced by CAP-1 (no silent
skips) and CAP-2/SI-3 (a binding may narrow, never broaden). Capability granularity is a
modeling choice that must be stated in every report: `objectstore.read` means "can read
*this marker*", not "can read anything".
