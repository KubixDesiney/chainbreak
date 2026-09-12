## What this changes and why

<!-- Link the issue this follows up on, per CONTRIBUTING.md's "open an issue before writing
     code" rule, unless this is a typo or an obvious bug fix. -->

Closes #

## Type of change

- [ ] `fix:` — bug fix
- [ ] `feat:` — new capability, capability binding, or scenario
- [ ] `docs:` — documentation only
- [ ] `adr:` — architecture decision record
- [ ] `scenario:` — new or changed benchmark scenario
- [ ] `chore:` — everything else (dependency bumps, CI tweaks, etc.)

If this changes the behavior of a gate, a validator, a precondition, or a safety invariant,
it must be `fix:`, never `chore:` — see [CONTRIBUTING.md § Commit messages](../CONTRIBUTING.md#commit-messages)
for why that distinction is load-bearing here, not cosmetic.

## Invariants

- [ ] This does not touch an ARCH-1/CAP-1/CAP-2/AUTH-1/G-1…G-5/PROV-1/INFRA-1/2/SI-1…SI-12/EV-1
      invariant (see the table in [CONTRIBUTING.md](../CONTRIBUTING.md#the-invariants-you-must-not-casually-change)), **or** it does, and an ADR is linked here: #
- [ ] The affected specification documents (ARCHITECTURE.md, SECURITY_MODEL.md,
      AUTHORIZATION_MODEL.md, CAPABILITY_MODEL.md, EVIDENCE_SCHEMA.md, etc.) are updated in
      **this same PR**, not a follow-up
- [ ] `PROJECT_STATUS.md` is updated if this completes or advances a milestone

## Contribution boundary (SECURITY_MODEL §6)

- [ ] This PR does **not** add credential harvesting/discovery, authentication bypass,
      privilege escalation against non-benchmark identities, a persistence mechanism,
      monitoring/detection evasion, automated exploitation of a finding, or any code path
      that can act outside the operator's account allowlist.

PRs that add any of the above will be closed per
[SECURITY_MODEL.md § 6](../SECURITY_MODEL.md#6-what-chainbreak-will-never-implement) and
[SECURITY.md § Contributions that will be declined](../SECURITY.md#contributions-that-will-be-declined).
If a measurement genuinely needs something that superficially resembles one of these, open
an issue first with a proposed ADR — don't lead with the PR.

## Checklist (mirrors what CI enforces)

- [ ] `ruff check .` and `ruff format --check .` pass (`lint`)
- [ ] `mypy` passes (`types`)
- [ ] `lint-imports` passes and the import-boundary test is green (`boundaries`)
- [ ] `bandit -r src/` and `pip-audit` are clean; no `.tfstate`/`.tfvars`, no
      credential-shaped strings added anywhere in the tree (`security`)
- [ ] `pytest -m "unit or integration"` passes, including redaction coverage (100%) and
      SafetyGate coverage (100%) if those modules are touched (`test`)
- [ ] If a Pydantic model changed: `python -m chainbreak.scenarios.export_schema schemas`
      was re-run and the diff is committed (`schemas`)
- [ ] If a scenario was added or changed: it has a `deny` list on every `node_authority`
      expectation, contains no ARNs/account IDs/regions, passes
      `chainbreak scenario validate`, and — if it introduces a new detection pattern — ships
      with a matching negative control (`scenarios`, and see
      [CONTRIBUTING.md § Adding things](../CONTRIBUTING.md#adding-things))
- [ ] If Terraform changed: `terraform fmt -check -recursive infra/terraform`, `validate`,
      the no-wildcard-IAM check, and Checkov all pass (`terraform`)
- [ ] Every new third-party GitHub Action is pinned to a full commit SHA, and nothing here
      uses `pull_request_target` (`guards`)
- [ ] New logic has unit tests; new externally-observable behavior has an integration test;
      new detectors have a negative control

## Notes for the reviewer

<!-- Anything that doesn't fit above: added cost/runtime and whether it's bounded, a
     deliberate scope cut, or context a reviewer working through CONTRIBUTING.md's review
     checklist would otherwise have to reconstruct. -->
