# M8 — AWS provider adapter

## Current status

Complete. Dedicated-account acceptance passed on 2026-08-15: all 21 AWS-marked adapter tests,
the wrong-account call-log gate, the fixed-role contract setup, and the documented response-shape
fixture suite passed. The response fixtures are transcriptions of AWS shapes, not live captures;
their provenance files document that boundary. M17 remains a separate experiment milestone and
has zero valid/publishable blocks.

## Purpose
Implement the AWS adapter: preflight, STS delegation, probes with response disambiguation,
controlled mutations, and policy snapshots. The first milestone that touches a cloud.

## Dependencies
M7. **Requires an operator-owned AWS benchmark account for the `aws` test layer.**
Non-AWS parts are developable with `moto`.

## Required components
`providers/aws/{adapter,preflight,session,bindings,probes,mutation,policy,disambiguation,
policy_synthesis,retry}.py`.

## Files expected
```
src/chainbreak/providers/aws/*.py
tests/aws/{test_adapter_moto,test_adapter_real,test_disambiguation}.py
tests/fixtures/provider_responses/*.json + *.provenance.json
```

## Functional requirements
- F1 Preflight P1–P11 in the documented order.
- F2 Delegation for all five mechanisms; report requested vs granted lifetime and emit
  `LIFETIME_CAPPED`.
- F3 Session-policy synthesis from bindings only — never hand-written per scenario — with the
  2048-character limit checked at compile time (M3) and re-asserted here.
- F4 Probes for all 10 capabilities per the probe table, with **content verification** on
  success: a read is `ALLOWED` only if the returned digest matches. "No exception" is not
  success.
- F5 Disambiguation: parse denial messages for explicit-vs-implicit attribution; populate
  `disambiguation_path`; return `DENIED_UNATTRIBUTED` when the phrase is absent rather than
  guessing. Distinguish Lambda `FunctionError` (a function fault) from `AccessDeniedException`.
- F6 Marker precondition verification by the **bootstrap** identity before every read matrix;
  failure ⇒ `ERROR_INFRASTRUCTURE` for the whole matrix.
- F7 Mutation choke point: namespace assert, benchmark-agent assert, read-after-write
  confirmation, receipt with `t_M` = send instant and confirmation latency recorded separately.
- F8 Retry on transient classes only, full-jitter backoff, retries recorded; `AccessDenied`
  is **never** retried.
- F9 Regional STS endpoint pinned and recorded.
- F10 Optional `iam:SimulatePrincipalPolicy` corroboration into a separate
  `simulations.jsonl`, never feeding `ObservedAuthority`. Off by default.

## Non-functional requirements
A 180-call probe matrix under 60 s at concurrency 4. Cost per full suite under $0.10.

## Security requirements
- S1 SI-6: `GetCallerIdentity` first; on account mismatch it is the only call made.
- S2 SI-2: `assert_namespace` plus an independent botocore `before-call` hook inspecting
  every outbound request's resource parameters.
- S3 SI-3: the M2 `OperationAllowlist` wired to the same hook.
- S4 SI-12: mutation refuses `bootstrap` and `principal` targets.
- S5 No credential ever leaves memory; sessions live in a context manager that scrubs on exit.

## Tests
`test_adapter_real.py` (marker `aws`) is where IAM semantics are validated:
role-chain duration cap; session policy cannot grant; explicit deny wins; **denial message
attribution** (the canary for AWS changing its error format, which would silently break
classification); the S3 403/404 ambiguity; missing marker ⇒ `CONFIGURATION_ERROR`;
`whoami` never denied; out-of-namespace probe refused before the call.

`test_adapter_moto.py` covers call shapes only. Every moto test carries a docstring stating
that moto's policy evaluation is an approximation and is **not** ground truth.

## Negative controls
Point the adapter at an account not in the allowlist; assert exactly one AWS call. Delete the
S3 marker; assert `ERROR_INFRASTRUCTURE`, not a wave of denials. Attempt a probe against an
out-of-namespace ARN; assert refusal before any network call.

## Acceptance criteria
1. The AWS adapter passes the shared M5 contract assertions; fixed-role AWS
   setup is supplied through the contract suite's provider-specific identity
   hooks, without overriding the behavioral assertions.
2. All `test_adapter_real.py` tests pass against a real benchmark account.
3. Recorded response fixtures cover every outcome class and drive the disambiguation tests.
4. Preflight ordering verified by call log.
5. No `boto3` import outside `providers/aws/` (M0 boundary test still green).

## Verification commands
```bash
pytest -m unit tests/unit/test_import_boundaries.py -q
pytest tests/aws/test_adapter_moto.py -q
CHAINBREAK_ALLOW_AWS_TESTS=1 pytest -m aws tests/aws/test_adapter_real.py -q
pytest -m integration tests/integration/test_provider_contract.py -q   # both adapters
```

## Definition of done
Acceptance criteria met **with real AWS output pasted**; AWS_PROVIDER_SPEC.md updated if
behavior differed from the spec; `PROJECT_STATUS.md` records which AWS tests actually ran,
when, and in which account (hashed).

## Out of scope
Terraform (M9). Running full experiments (M17).

## Risks
The 403/404 ambiguity is the highest-risk detail in the project: get the precondition control
wrong and every `objectstore.read` measurement is meaningless. Implement F6 before F4 and
test it first. AWS changing denial message wording would silently degrade attribution — the
canary test is the mitigation, and it must fail loudly rather than fall back to a guess.
