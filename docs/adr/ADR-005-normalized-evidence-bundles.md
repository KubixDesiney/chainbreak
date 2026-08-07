# ADR-005: Normalized, sealed evidence bundles as the durable artifact

**Status:** Accepted · **Date:** 2026-08-07

## Context

A run produces probe results, timings, policy states and findings. These could be written as
a single JSON document at the end, or streamed into structured files as they happen.

## Decision

An evidence bundle is a directory of append-only JSONL streams plus JSON documents, sealed
at completion with a per-artifact SHA-256 and a root hash in `manifest.json`. The bundle —
not the report — is the deliverable.

## Rationale

**Append-only, written during the run.** A crash mid-experiment is then a data point rather
than a data loss. Given that one benchmark family deliberately runs long waits and another
polls for five minutes, partial evidence is not an edge case.

**Normalized across providers.** The analysis layer reads capability IDs and outcome
classes, never provider-specific shapes. That is what makes the same analysis code correct
for both the AWS adapter and the fake.

**Self-describing.** The bundle carries CHAINBREAK version, git commit, catalog version,
adapter version, compiled scenario hash, config fingerprint, infrastructure fingerprint and
seeds. A bundle without its schemas is uninterpretable once schemas evolve, so
`evidence export --archive` includes them.

**Sealed, not signed.** Hashing gives tamper-*evidence*, which is the appropriate bar for a
self-administered benchmark: it defends against accidental corruption and makes deliberate
falsification require deliberate effort. Detached signing is deferred to v0.2 and the
manifest reserves a `signatures` key.

## Consequences

**Positive.** Third-party re-analysis is possible, which is the only real mitigation for
systematic measurement error (R-12). Reports become disposable renderings.

**Negative.** More files than a single JSON blob. Canonical JSON (sorted keys, fixed float
formatting) is required for hashes to be meaningful, and that constraint has to be honored
by every writer.
