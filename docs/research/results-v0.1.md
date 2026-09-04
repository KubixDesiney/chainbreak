# CHAINBREAK v0.1 research results

## Release-gate status

The runtime and package version for this release candidate is `0.1.0`. Historical M17/M18
bundles retain their original `0.1.0a0` `chainbreak_version` provenance; changing the package
version does not rewrite historical evidence.

Three M17 real-AWS blocks are valid: `cb-m17-20260818-01` (`n=32`),
`cb-m17-20260818-02` (`n=23`), and `cb-m17-20260818-03` (`n=32`). The exact run IDs are
listed in [m17-run-index.md](m17-run-index.md). Every run was analyzed and publicly exported;
all six negative controls were `DETECTOR_OK` in every block; and the two destroy passes plus
exact `verify-clean` passed after each block. Mechanism was the CHAINBREAK AWS adapter against
the Terraform sandbox; region was `eu-west-3`; scope was this account, this region, this time.
The block windows were `2026-08-18T10:11:02Z–11:32:57Z`,
`2026-08-18T11:40:12Z–12:25:37Z`, and `2026-08-18T12:31:54Z–13:53:36Z`.

The valid-block result is a measured record for this account, this region, and this time only.
It is not a claim about AWS generally, other accounts, other regions, or other times. Historical
AWS attempts remain in the excluded section of the run index and lab log; they are not included
in any value below.

## M17 measured timing observations

Each timing row has `n=5` runs, with one run in each valid block and the remaining two runs
distributed across the three blocks. The interval is the observed run-level envelope in seconds;
mechanism, region, and scope are stated per row. Exact run IDs are included so the row can be
reproduced from the sealed bundles.

| Scenario / mechanism | Exact run IDs | n | Measured interval | Region and scope |
|---|---|---:|---:|---|
| `revocation-inline-deny` / `iam:PutRolePolicy` explicit deny | `01M0A625EY3957YEFYQXV2WGFG`, `01M0A84C16F38Q4GQZ1P31PH5A`, `01M0AB56338FCAWX29WWSADG6F`, `01M0AE3XJHCFDD56YTDNA92TP7`, `01M0AG62VZ7GGG5FYQ6574427H` | 5 | `10.500–12.265 s` | `eu-west-3`; this account, this region, this time |
| `revocation-revoke-older-sessions` / `iam:PutRolePolicy` with `aws:TokenIssueTime` | `01M0A669ZP7QJ7VPANXD727270`, `01M0A88EX0242XQERCCAG5N4HM`, `01M0AB948QBHYA05YWGPVWYJYB`, `01M0AE7YDE9C25F07C397WDYA5`, `01M0AGA6TP4852MC6DD0D4429C` | 5 | `10.046–11.375 s` | `eu-west-3`; this account, this region, this time |
| `revocation-delete-session-scope` / issuance-scope control | `01M0A604YC8013CWA2QEKSPN8P`, `01M0A826FPA65C84NJE58RP4V6`, `01M0AB39X19EQ2D1YY41YJV7XW`, `01M0AE21799VDHSYZQQ27ZE628`, `01M0AG429374VTVT6P4N59KQ74` | 5 | No transition observed within the configured poll window | `eu-west-3`; this account, this region, this time |
| `revocation-remove-policy` / `iam:DeleteRolePolicy` | `01M0A63BNTF5ZY84ZB9YYVCVS6`, `01M0A85GYAB833C0KYJE3NBW8M`, `01M0AB69WF2E3DEAMMSAV7FVH4`, `01M0AE51389YNZEF6XNRASKTC5`, `01M0AG7AXY0C832J15ZKBX4CZ5` | 5 | No transition observed within the configured poll window | `eu-west-3`; this account, this region, this time |
| `revocation-trust-policy-null-condition` / `iam:UpdateAssumeRolePolicy` null condition | `01M0A67CKFA3SPMB1J808D5K3D`, `01M0A89H7P407TA32FYP1GDEEW`, `01M0ABA8R8849YET57K7YZT67S`, `01M0AE91HVEKFE3EF25HV1Q17X`, `01M0AGB94B2SDJ6TXQ41VJBCPD` | 5 | No transition observed within the configured poll window | `eu-west-3`; this account, this region, this time |

The three rows with no observed transition are not estimates of a longer interval. They are
right-censored observations under the configured poll window, with the mechanism, region, and
scope shown above.

For stale authority, each row has `n=5` runs and two declared capabilities per run. The interval
is the envelope across those two capability measurements; mechanism was the pinned-credential
and freshly delegated-credential pair after the named trust-policy mutation or expiry wait;
region was `eu-west-3`; scope was this account, this region, this time.

| Scenario / wait | Exact run IDs | n | Measured interval |
|---|---|---:|---:|
| `stale-authority-short-defer` / 20 s | `01M0A80CVR1VMQX6S59357SYQD`, `01M0AA2TKJ2Z7C4TSP28HWJG7R`, `01M0AD3D1T4NPE2SK0HN9PJ0JT`, `01M0AG263XFQYAP14Z5R61KRQ9`, `01M0AJ4CTDF8STMVEW2G04XGBJ` | 5 | `30.907–31.062 s` |
| `stale-authority-deferred-execution` / 120 s | `01M0A698XGEEETRTJMECB8Z9W0`, `01M0A8BMSZDG4HVMVH8HV5FEHR`, `01M0ABC5S29PJN3ZAHJK8HR7YD`, `01M0AEAYT63R79JAGFY7D6NV21`, `01M0AGD8KF0G651904KH85F89B` | 5 | `120.938–122.250 s` |
| `stale-authority-long-defer` / 600 s | `01M0A6DW77EYA7GFAMWKY0CHN0`, `01M0A8G7KF68EVHJW5BEQSZ4TF`, `01M0ABGSBZ4HB1GRS24M0K92TH`, `01M0AEFHKCF7RKEVF51VF69NXA`, `01M0AGHWA7ENTHY49ATQQRZ009` | 5 | `600.906–602.688 s` |
| `stale-authority-post-expiry` / 1000 s | `01M0A713EK78KTXQG9BYBWD5P3`, `01M0A93F0E3QAPTQSTHDWVSA7Z`, `01M0AC42P04TGF034420R9TTNE`, `01M0AF2V0N77WWEQCQE89CNFBD`, `01M0AH52XWA03PWZESNF3TPD8N` | 5 | No stale window recorded because the credential was expired at execution |

The stale rows characterize these configured waits and paired credentials; they do not
generalize beyond the stated account, region, and time.

## M18 measured reproducibility checks on valid AWS bundles

All M18 claims below use valid-block AWS bundles, the AWS adapter, region `eu-west-3`, and scope
this account, this region, this time. Timing intervals are not applicable to these artifact
operations.

- Same-scenario compare used runs `01M0A5WS8Q912NJSP0FEH1DWSK` and
  `01M0AB0FAF0JF8JDC72D75SKF5`; `n=2`; `chainbreak compare` returned 4 measurements,
  0 divergent, and `STRUCTURALLY_IDENTICAL` set-valued verdicts. This is a same-scenario
  comparison, not literal byte identity.
- Cross-operator compare used the same two run IDs; `n=2`; `chainbreak compare` returned 4
  measurements and 0 divergent, while explicitly stating that account, region, and
  infrastructure equivalence was assumed and unverified. Confidence is therefore lower by
  design; mechanism was `chainbreak compare`.
- Heterogeneous compare used `01M0A5WS8Q912NJSP0FEH1DWSK` and
  `01M0A5YA7MB9ZF1XMWDWMXVFHT`; `n=2`; without `--allow-heterogeneous` the command refused
  the compiled-hash/adapter/catalog mismatch; with the flag it returned 6 divergent
  measurements and lower-confidence verdicts. This is measured divergence, not agreement.
- Public archive extraction used run `01M0A5WS8Q912NJSP0FEH1DWSK`; `n=1`; an archive made
  from an empty directory was extracted into a fresh runs-root and analyzed successfully with
  `--allow-unsealed`; mechanism was the self-contained public archive. Public scrubbing changes
  the source integrity root, so the unsealed option is required for this check.
- Synthetic format migration used the same run ID; `n=1`; registered `(1,99)` migration
  mechanism `copy_bundle_verbatim` preserved the source and copied bytes identically into a new
  directory; mechanism was `copy_bundle_verbatim`/`migrate_bundle`.

## Scrubbed artifacts and excluded material

`examples/reports/aws-m17-valid-block01-scrubbed-report.md` and
`examples/reports/aws-m17-valid-block01-scrubbed-sample.tar.gz` are scrubbed outputs from the
valid AWS run `01M0A5WS8Q912NJSP0FEH1DWSK`; `n=1` sample, interval not applicable, mechanism
public evidence export, region `eu-west-3`, scope this account, this region, this time. The
fake-provider sample is labelled an apparatus check and excluded from AWS runs. Historical AWS
samples and the prior block-04 sample are labelled excluded and are not used above.

## Remaining unmeasured scope and release boundary

The measured rows do not cover other accounts, regions, times, clouds, permission boundaries,
SCPs, consequential resource policies, or production role graphs. No cross-account or
cross-operator equivalence has been established; the cross-operator M18 check above is
explicitly assumed and unverified. The confirmed historical account-ID finding was scrubbed from
active Git history and the active refs were rescanned with zero matches; the pre-scrub objects are
retained only in a private local recovery bundle. Publication of this repository and the
`v0.1.0` tag change none of the measured values above; they change only who can read them.

The temporary benchmark `sts:AssumeRole` permission was removed by the owner on 2026-09-01, and
the benchmark account was verified clean the same day: zero `cb-*` IAM roles, zero resources
tagged `Project=CHAINBREAK` in `eu-west-3`, and the benchmark budget removed. This is an
operational cleanup record and does not affect any measured value above — every row was sealed
before that removal and is reproducible only from its archived bundle, not from live
infrastructure, which no longer exists.
