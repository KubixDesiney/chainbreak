# Module contract: `observability`

Optional provider-side corroboration. **Default off.** Implementation is milestone M9.

## Required inputs

`namespace`, `enable_cloudtrail` (default `false`), `trail_retention_days` (default `7`),
`enable_data_events` (default `false`).

## Required outputs

`trail_name`, `trail_bucket`, `log_group_names`.

## Why default off

CHAINBREAK's measurements are client-side by design: a probe outcome is observed directly,
not inferred from a log. CloudTrail is a *corroboration* mechanism, useful for confirming
that a benchmark session appears server-side with the expected `RoleSessionName` and for
cross-checking event timing against the local monotonic clock.

It is off by default because:

- The first management-events trail per account is free, but **data events are billed per
  event** and a probe-heavy run generates many. `enable_data_events` therefore defaults to
  `false` and its description says so in cost terms.
- CloudTrail delivery latency is minutes, which is orders of magnitude coarser than the
  sub-second intervals the revocation family measures. Treating CloudTrail timestamps as a
  timing source would be a methodological error, and the module's documentation says this
  explicitly so a future maintainer is not tempted.

## Requirements

1. If enabled, the trail bucket has `force_destroy = true` and a lifecycle rule expiring
   objects after `trail_retention_days`.
2. Log group retention is always explicit. Never rely on the default (never expire).
3. The module must never be a dependency of `identities` or `resources` — enabling or
   disabling observability must not change what is measured.
