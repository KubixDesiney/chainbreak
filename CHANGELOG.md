# Changelog

All notable changes to CHAINBREAK are recorded here.

## v0.1.0 - 2026-09-04

- Replaced the `LICENSE` stub with the complete, unmodified Apache-2.0 text, and moved the
  acceptable-use statement out of `LICENSE` into a separate `NOTICE` file so the licence is
  unambiguously Apache-2.0 with no added terms. The same statement remains in `SECURITY.md`.
- Pointed `SECURITY.md` at GitHub Security Advisories only; the previous pointer to a
  maintainer address in `pyproject.toml` was broken, because no such address exists there.

- Completed three valid real-AWS M17 blocks on 2026-08-18 (`n=32`, `n=23`, `n=32`), with all
  six negative controls `DETECTOR_OK`, complete analysis/export, and exact cleanup. Added the
  valid run index and measured-only results record; earlier AWS attempts remain excluded.
- Exercised AWS compare, cross-operator confidence, heterogeneous refusal/lower-confidence
  behavior, empty-directory archive analysis, and synthetic bundle migration on valid AWS
  bundles. The results record preserves the measured `n`, mechanism, region, and scope.
- Fixed public-export account-ID boundaries so decimal timing values remain valid JSON; hardened
  public export against live benchmark namespaces and session names; fixed ARN scrubbing so
  adjacent JSON fields remain valid; generated a valid-block scrubbed report and sample archive.
- Reconciled M17/M18/M19 status across the code, schemas, methods, README, portfolio story,
  reports, run index, and lab log; recorded the owner-only publication boundary.
- Restored the fake provider's stale-authority negative-control contract so the full suite and
  AWS repair path model future-issuance denial while preserving an existing session.
- Added the platform-specific Windows wheel hash observed during verification; the lock remains
  generated for and verified against the CI Linux target.
- Added the M17 W03 exclusion record, explicitly labelled fake-provider apparatus outputs, and
  recorded the current tree/history scan. Scrubbed the confirmed historical account-ID finding
  from active Git history and retained a private local recovery bundle. No v0.1.0 tag or
  publication was created.

### Scope of what the v0.1.0 release measures

Three valid real-AWS blocks in `eu-west-3` on 2026-08-18 (`n=32`, `n=23`, `n=32` — 87 analyzed
runs). All six negative controls `DETECTOR_OK` in each block. Blocks 05, 06 and 07 remain
explicitly excluded and are labelled as such. Every other benchmark family result in this
candidate comes from the deterministic fake provider and is labelled an apparatus check, not an
AWS measurement. Measured values hold for that account, that region, and that time only.

IAM cleanup completed 2026-09-01 — the temporary benchmark `sts:AssumeRole` permission was
removed and the account verified clean. The final read-only release gate passed on 2026-09-04;
the annotated `v0.1.0` tag and GitHub release were published from the green release commit.

Historical M17/M18 bundles, lab records, and synthetic fixtures intentionally retain
`0.1.0a0` in their `chainbreak_version` provenance. Those values describe the runtime that
created the historical evidence and are not current package-version metadata.

The `v0.1.0` release is published with the verified wheel and scoped release notes.
