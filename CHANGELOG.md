# Changelog

All notable changes to CHAINBREAK are recorded here.

## Unreleased - release candidate pending owner decision

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
  recorded the current tree/history scan. No v0.1.0 tag or publication was created.

## v0.1.0

Not released. The owner still decides history handling, tag, publication, and final release after
the temporary benchmark IAM permission is removed by an authorized administrator.
