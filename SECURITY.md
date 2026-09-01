# Security Policy

## Reporting a vulnerability in CHAINBREAK

Report privately via GitHub's Private Vulnerability Reporting on this repository
(Security tab → Report a vulnerability). Please do not open a public issue for a
security-relevant defect.

Include: the version or commit, the invariant you believe is violated (see
[SECURITY_MODEL.md](SECURITY_MODEL.md) for the SI-* list), reproduction steps, and impact.

Expect acknowledgement within 7 days and an assessment within 21. Coordinated disclosure is
preferred; credit is given unless you ask otherwise.

**Highest-priority classes** — anything that could cause CHAINBREAK to:

- write credential material into evidence, logs, or reports (SI-1);
- act on a resource outside its declared namespace (SI-2);
- act in an account not in the operator's allowlist (SI-6);
- execute code from a scenario or evidence file (SI-11, T-10);
- leave infrastructure or policy mutations behind after a run (SI-4).

## Reporting a finding *about a cloud provider*

If a CHAINBREAK measurement suggests a genuine defect in a cloud provider's authorization
behavior — as distinct from the documented behaviors listed in
[AWS_PROVIDER_SPEC §10](AWS_PROVIDER_SPEC.md#10-known-aws-behaviors-the-benchmark-must-not-misreport) —
the correct sequence is:

1. Reproduce it. n=1 on a shared control plane is not a finding.
2. Run the full negative-control suite in the same block to confirm the instrument works.
3. Rule out the documented behaviors and the known measurement hazards.
4. Report privately to the provider's security team.
5. Publish only after the provider has had reasonable opportunity to respond.

Publishing an unreproduced measurement as a provider vulnerability would be both wrong and
damaging to the project's credibility. The methodology is explicit that most measurements
here characterize *documented* behavior; that is the contribution.

## Scope of acceptable use

CHAINBREAK is a defensive measurement tool. It may be used only against cloud accounts and
identities the operator owns or is explicitly authorized to test. Using it against
third-party infrastructure without authorization is outside the license's intended use and
likely unlawful in most jurisdictions.

## Contributions that will be declined

Per [SECURITY_MODEL §6](SECURITY_MODEL.md#6-what-chainbreak-will-never-implement), pull
requests adding credential harvesting or discovery, authentication bypass, privilege
escalation against non-benchmark identities, persistence mechanisms, monitoring evasion,
automated exploitation of findings, or any code path that acts outside the account allowlist
will be closed.

If a *measurement* genuinely requires something that superficially resembles the above, open
an issue first with a proposed ADR explaining why the measurement cannot be obtained
otherwise and how it stays inside the benchmark namespace.

## Operator responsibilities

- Use a **dedicated AWS account** with no production workloads.
- Populate `allowed_account_ids` explicitly. Never wildcard it.
- Prefer short-lived credentials (SSO or OIDC). Never static keys in CI.
- Run `chainbreak infra verify-clean` after every experiment block.
- Review the scrub diff before publishing any bundle.
- Keep an eye on the Budgets alarm the `benchmark-account` module provisions.

## Supported versions

v0.1 is pre-release. Security fixes land on `main` only. A supported-version table will
appear at the first tagged release.
