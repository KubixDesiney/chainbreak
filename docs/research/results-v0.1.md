# CHAINBREAK v0.1 research results

## Gate status

This document intentionally contains no AWS measurement claims. As of 2026-08-17, M17 has
zero valid or publishable blocks. The new real-AWS attempts in this pass were both excluded
before any usable sealed scenario suite existed: W03 stopped at the live gate because the
available profile was an account-root session and AWS rejected `AssumeRole`; W04 stopped during
Terraform apply with `couldn't find resource`; W05 stopped on the first scenario because the
IAM-user operator lacked `sts:AssumeRole`. All infrastructures were cleaned and exact
`verify-clean` passed. See [lab-log.md](lab-log.md).

Because there is no valid AWS run ID, the measurement fields required by the protocol are not
applicable: n, interval, mechanism, region, and scope are intentionally absent rather than
invented. The scope of this document is therefore: this account, this region (`eu-west-3`),
this time, and no measured AWS outcome.

## Excluded apparatus

Historical AWS-labelled bundles use a non-real STS endpoint and are excluded from AWS runs.
Fake-provider bundles and their reports are explicitly labelled `FAKE-PROVIDER APPARATUS CHECK`
and are excluded from AWS results. They validate the analysis and reporting machinery only.

The offline M18 apparatus comparison used runs
`01M080YJ8MFNMNJE5VSTCF8CYD` and `01M080YSH10KBNKHEXVS9XHB6X`: 3 compared measurements,
no AWS timing interval, fake-provider deterministic mechanism, synthetic region
`fake-region-1`, and synthetic apparatus scope. It returned `STRUCTURALLY_IDENTICAL`.
The `--cross-operator` path emitted its required warning that environment equivalence was
assumed and unverified; that is an apparatus confidence limitation, not heterogeneous AWS
confidence. The heterogeneous comparison against a historical AWS-labelled bundle was
refused because that bundle is excluded and fails the current namespace contract. Migration
was exercised in the offline unit suite only. None of these observations is an AWS result.

## Remaining scope before publication

M17 still needs valid real-AWS blocks covering all five families, all six negative controls in
each block, the required trial counts, and timing windows distributed across at least three
separate hours. M18 still needs compare, archive, and migration exercised on those valid
real-AWS bundles. No release, tag, or publication is authorized by this file.
