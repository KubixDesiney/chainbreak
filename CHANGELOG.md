# Changelog

All notable changes to CHAINBREAK are recorded here.

## Unreleased - release candidate blocked

- Completed three real-AWS M17 suite attempts with exact scrubbed archives and cleanup; all
  remain excluded because the non-monotone-chain and stale-credential-reuse controls returned
  `DETECTOR_FAILURE` in each block. Added the measured run index and excluded results record.
- Exercised AWS compare, cross-operator confidence, heterogeneous refusal/lower-confidence
  behavior, empty-directory archive analysis, and synthetic bundle migration against excluded
  AWS bundles. No result is promoted to release evidence.
- Fixed public-export account-ID boundaries so decimal timing values are not replaced inside
  JSON numbers; added a regression test.
- Hardened public export against live benchmark namespaces and session names, and fixed ARN
  scrubbing so adjacent JSON fields remain valid; regenerated the block-07 sample archive.
- Added the M17 W03 exclusion record and the gated, measurement-free
  `docs/research/results-v0.1.md`.
- Added an explicitly labelled, scrubbed fake-provider apparatus report and archive.
- Corrected shared report limitations so fake-provider output does not claim execution in a
  real AWS account.
- Recorded excluded W04/W05 live attempts, including the Terraform apply failure and the
  IAM-user `sts:AssumeRole` authorization boundary; both were cleaned.
- Made bootstrap retain an IAM-user operator principal and made the live budget check handle
  AWS's dedicated notification/subscriber response projection.
- Recorded the current tree/history scan and the remaining owner decisions in the release
  handoff. No v0.1.0 tag or publication was created.

## v0.1.0

Not released. This heading remains reserved until valid M17 blocks exist and the owner approves
the history/publication decision.
