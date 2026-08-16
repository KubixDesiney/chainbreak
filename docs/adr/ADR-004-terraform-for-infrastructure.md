# ADR-004: Terraform for provisioned infrastructure; runtime STS for delegation

**Status:** Accepted · **Date:** 2026-08-07

## Context

CHAINBREAK needs roles, policies and resources. It could create them with boto3 at runtime,
which would avoid a Terraform dependency and make runs self-contained.

## Decision

Two planes, strictly separated (INFRA-1):

- **Provisioned identity plane** — roles, trust policies, permission policies, buckets,
  tables, functions, queues, markers. Terraform only.
- **Delegation plane** — `AssumeRole` calls, session policies, credential issuance, and
  controlled policy mutations on agent roles. Runtime only.

CHAINBREAK never creates an IAM role or attaches a managed policy at runtime.

## Rationale

Runtime-created infrastructure has no `plan`. An operator cannot review what a run is about
to create in their account, which is unacceptable for a tool that creates identities.

Terraform also gives deterministic destruction, which is the mitigation for the most likely
real cost risk (forgetting to clean up, T-06). Cleanup verification
(`infra verify-clean`) uses native service enumerators and exact
`Project=CHAINBREAK` plus namespace tags; Terraform applies `default_tags` uniformly where
the AWS service supports tags, while an unsupported or failed enumerator is unsafe.

Delegation cannot be Terraform, because credential issuance is inherently per-run and
per-second. Trying to express it declaratively would be a category error.

The boundary is enforced in code, not convention: runtime mutation is limited to inline
policies and trust policies on roles carrying the benchmark namespace tag, checked at a
single choke point.

## Consequences

**Positive.** Reviewable `plan` before anything is created. Deterministic `destroy`.
Uniform tagging. A clear answer to "what did this tool do to my account".

**Negative.** Terraform is a required dependency and a second language in the repo.
Terraform outputs become a stable interface between two languages that must not drift —
mitigated by preflight P5 failing loudly on a missing output, and by `capability_ceiling`
being cross-checked against scenario assumptions in `chainbreak validate`.
