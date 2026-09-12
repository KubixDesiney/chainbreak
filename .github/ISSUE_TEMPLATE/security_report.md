---
name: "🔒 Security-relevant report"
about: "Stop — read this before filing. Do not describe a vulnerability in a public issue."
title: ""
labels: []
---

**Do not describe a security vulnerability here.** This tracker is public; anything you
post here is visible to everyone before a fix exists.

If you believe you've found a defect that could let CHAINBREAK do one of the things listed
as highest-priority in [SECURITY.md](../../SECURITY.md) — leak credential material, act
outside its namespace, act in a non-allowlisted account, execute code from a scenario or
evidence file, or leave infrastructure behind after a run — report it privately instead:

**[Open a private vulnerability report](https://github.com/KubixDesiney/chainbreak/security/advisories/new)**
(GitHub Security tab → "Report a vulnerability")

See [SECURITY.md](../../SECURITY.md) for what to include and what to expect.

If instead you're reporting a suspected defect in a **cloud provider's** authorization
behavior (not in CHAINBREAK itself), that has a separate process — see
[SECURITY.md § Reporting a finding about a cloud provider](../../SECURITY.md#reporting-a-finding-about-a-cloud-provider).
It also should not be filed here.

If, on reflection, this isn't actually security-relevant, please use the
[Bug report](https://github.com/KubixDesiney/chainbreak/issues/new?template=bug_report.yml)
or
[Scenario / measurement question](https://github.com/KubixDesiney/chainbreak/issues/new?template=scenario_or_measurement_question.yml)
template instead.
