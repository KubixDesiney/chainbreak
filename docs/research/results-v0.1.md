# CHAINBREAK v0.1 research results

## Release-gate status

No M17 block is publishable. Blocks `cb-m17-20260817-05`,
`cb-m17-20260817-06`, and `cb-m17-20260817-07` each completed the AWS suite and cleanup,
but each produced `DETECTOR_FAILURE` for two negative controls. M17 explicitly invalidates a
block containing any detector failure, so all measurements below are excluded apparatus
measurements, not AWS results. The account, region, and time scope for every record is: this
benchmark account, `eu-west-3`, the recorded run window only.

The three excluded blocks contained respectively `n=32`, `n=23`, and `n=32` completed AWS
runs. Their windows were 2026-08-17T20:00:39Z–21:23:40Z,
2026-08-17T21:31:13Z–22:22:29Z, and 2026-08-17T22:38:03Z–23:58:38Z; mechanism was the
CHAINBREAK AWS adapter against the Terraform sandbox; region was `eu-west-3`; scope was
this account, this region, this time. The complete run-ID lists are in
[m17-run-index.md](m17-run-index.md), and the detector-failure run IDs are listed below.

## Exclusion that invalidated every block

`nc-non-monotone-chain` returned `DETECTOR_FAILURE` in `n=3` runs,
`01M08NBZW62JSMJP4XTWJDP2C5`, `01M08TR9JG16BN4ZQGNWAC5PN9`, and
`01M08YB93C5MT3A1V1JEYKV8Q3`. The measured mechanism was the AWS role-chain negative
control; interval is not applicable to this set-valued control; region was `eu-west-3`; scope
was this account, this region, this time. The expected `DELEGATION_DRIFT` finding was not
matched at the declared identity/capability, so the block is excluded rather than relabelled.

`nc-stale-credential-reuse` returned `DETECTOR_FAILURE` in `n=3` runs,
`01M08NE3QWCSRB22CV6GESB7QJ`, `01M08TTVNF9K29W6TR97QJ9SAV`, and
`01M08YDA5REA3KVP1EEE4D1NT1`. The measured mechanism was an AWS inline-deny mutation
followed by a pinned and freshly delegated credential pair; interval is not applicable to
this set/pair control; region was `eu-west-3`; scope was this account, this region, this time.
The deferred and fresh observations both denied the declared capability, so no stale-authority
finding was produced. This is recorded as measured control behavior, not as a detector pass.

These failures were repeated across three infrastructure blocks and are therefore not treated
as a one-run flake. The non-monotone control's infrastructure/scenario identity mapping and the
stale-control's AWS mutation premise require repair and a fresh full M17 campaign before any
timing or family result can be published.

## Excluded timing observations

The following values were computed from sealed AWS bundles in the three excluded blocks. They
are included to preserve the measured record only; they are not claims about AWS generally.
Every interval is the analyzer's monotonic transition interval in seconds. Mechanism, region,
and scope for every row are respectively the named AWS IAM mutation, `eu-west-3`, and this
account, this region, this time. Each row has `n=5`, with two runs in block 05, one in block 06,
and two in block 07; the five scenario run IDs are enumerated by block in
[m17-run-index.md](m17-run-index.md).

| Scenario / mechanism | n | measured interval | status |
|---|---:|---:|---|
| `revocation-inline-deny` / `iam:PutRolePolicy` explicit deny | 5 | 11.734–14.672 s | excluded: block detector failures |
| `revocation-revoke-older-sessions` / `iam:PutRolePolicy` with `aws:TokenIssueTime` | 5 | 11.359–14.781 s | excluded: block detector failures |
| `revocation-delete-session-scope` / issuance-scope control | 5 | no transition observed within the configured poll window | excluded: block detector failures |
| `revocation-remove-policy` / `iam:DeleteRolePolicy` | 5 | no transition observed within the configured poll window | excluded: block detector failures |
| `revocation-trust-policy-null-condition` / `iam:UpdateAssumeRolePolicy` | 5 | no transition observed within the configured poll window | excluded: block detector failures |

The stale-authority rows were also `n=5` per scenario, with the same three-block distribution,
AWS adapter mechanism, `eu-west-3` region, and this-account/region/time scope. The measured
deferred intervals were 31.078–31.938 s for `short-defer`, 121.109–123.344 s for
`deferred-execution`, and 600.953–603.782 s for `long-defer`; the post-expiry run had no stale
window because the credential was expired at execution. The observed classifications were
`CURRENT_AUTHORITY` or `INDETERMINATE` for the first three scenarios and
`CREDENTIAL_EXPIRED` for `post-expiry`; these are excluded measurements, not published stale-
authority conclusions. Region and scope are `eu-west-3` and this account, this region, this
time; the mechanism is the pinned-credential/fresh-credential pair after the named AWS
mutation or expiry wait.

## M18 apparatus checks, excluded from AWS results

M18 compare, archive, and migration were exercised against sealed AWS bundles from excluded
block 07. These checks are labelled excluded because M17 invalidated the source block. A
same-scenario compare passed for `n=2` AWS runs
(`01M08YGAN600DXR03J0CVDDV25`, `01M08YRZQZ2VTMVWHTTZKJNZJT`) with no divergent measurements;
mechanism was `chainbreak compare`, region was `eu-west-3`, and scope was this account, this
region, this time. A cross-operator compare of the same two run IDs also exited successfully
while printing that environment equivalence was assumed and unverified; it is lower-confidence
by design.

A different-compiled-scenario pair (`01M08XZTVR9S4WNZM9W87KB5MF`,
`01M08Y0W927ZR04AW3YW8BK4AR`) was refused without `--allow-heterogeneous` and, with the flag,
reported every verdict as lower-confidence and reported divergence. This was `n=2`, no timing
interval applicable to the heterogeneous refusal itself, AWS bundles in `eu-west-3`, and
this-account/region/time scope. The heterogeneous result is not presented as agreement.

A public archive for run `01M08YHCCBE9E58W0VRQHVYT1C` was extracted into a newly created empty
directory and analyzed successfully with `--allow-unsealed`; the same scrubbed archive was
refused without that flag because public scrubbing changes the source integrity root. This was
`n=1`, interval not applicable, mechanism the self-contained public archive, region `eu-west-3`,
and scope this account, this region, this time. Synthetic format migration of that same source
`(1,99)` copied a valid bundle byte-for-byte into a new directory while preserving the original
format-1 source; this was `n=1`, interval not applicable, mechanism
`copy_bundle_verbatim`/`migrate_bundle`, region `eu-west-3`, and scope this account, this region,
this time. Because the source block was excluded, these are apparatus checks, not publishable
AWS reproducibility claims.

## Scrubbing and remaining scope

The valid-format scrubber regression test measured that decimal timing values remain valid JSON;
the check was `n=1`, interval not applicable, mechanism public export scrubbing, region not
applicable to the unit fixture, and scope this repository/fixture/time. The AWS block-07 sample
report and archive contain zero scanned account-ID, ARN, live-namespace, and hostname patterns,
and every JSON member parses; this was `n=1` sample, interval not applicable, mechanism public
export, region `eu-west-3`, and scope this account, this region, this time. The block-04 sample
remains explicitly labelled excluded.

Unmeasured and blocked scope: no publishable M17 family result, no publishable timing estimate,
no valid three-block timing distribution, and no release candidate. A new campaign must first
repair and revalidate both failing controls, then repeat all five families and six controls in
three clean blocks before M19 can pass. No tag, history rewrite, force-push, GitHub release, or
publication is authorized by this document.
