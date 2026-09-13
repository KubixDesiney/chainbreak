# CHAINBREAK

[![CI](https://github.com/KubixDesiney/chainbreak/actions/workflows/ci.yml/badge.svg)](https://github.com/KubixDesiney/chainbreak/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/KubixDesiney/chainbreak/blob/main/LICENSE)
[![Python versions](https://img.shields.io/pypi/pyversions/chainbreak.svg)](https://pypi.org/project/chainbreak/)
[![Latest release](https://img.shields.io/github/v/release/KubixDesiney/chainbreak)](https://github.com/KubixDesiney/chainbreak/releases/latest)
[![PyPI](https://img.shields.io/pypi/v/chainbreak.svg)](https://pypi.org/project/chainbreak/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/KubixDesiney/chainbreak/badge)](https://scorecard.dev/viewer/?uri=github.com/KubixDesiney/chainbreak)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22723886.svg)](https://doi.org/10.5281/zenodo.22723886)

**An empirical benchmark for authorization behavior in delegated and agentic cloud systems.**

CHAINBREAK measures the gap between the authority a security policy *intended* to grant
and the authority a delegated workload *actually* holds when it executes.

**[See a real report &rarr;](https://kubixdesiney.github.io/chainbreak/)** &mdash; a rendered
AWS scope-attenuation measurement and a fake-provider apparatus check, side by side, no install
required. Every page on that site carries its provider stamp and its measured-scope caveat, and
every published file passed
[the scrub gate](https://github.com/KubixDesiney/chainbreak/blob/main/docs/site-provenance.md)
first.

> **Status: v0.1.1 — M0–M16 complete, including dedicated-account acceptance for M8/M9.**
> Three valid real-AWS M17 blocks completed on 2026-08-18 (`n=32`, `n=23`, `n=32`), with all six
> negative controls `DETECTOR_OK`, complete analysis and export, and exact cleanup; M18
> compare/archive/migration was exercised on those bundles, including honest lower-confidence
> cross-operator and heterogeneous behavior. 1,815 tests pass in the current unit/integration
> gate, and CI enforces lint, types, import boundaries, security scans, schema/scenario/Terraform
> checks and offline tests on every push. **The M17 numbers are measurements for one account, one
> region and one point in time, and nothing more**; the remaining scope is stated in
> [docs/research/results-v0.1.md](https://github.com/KubixDesiney/chainbreak/blob/main/docs/research/results-v0.1.md).
> [PROJECT_STATUS.md](https://github.com/KubixDesiney/chainbreak/blob/main/PROJECT_STATUS.md) is the authoritative per-milestone record;
> [CHANGELOG.md](https://github.com/KubixDesiney/chainbreak/blob/main/CHANGELOG.md) is the release history.

---

## The problem

Modern cloud systems hand authority down chains of identities. A human authorizes a
service, the service assumes a role, that role assumes another role, a workload receives
short-lived credentials, and somewhere at the end of the chain an autonomous process
performs an action. Every hop is supposed to *attenuate* authority — grant a subset, never
a superset — and every policy change is supposed to propagate promptly.

Those are assumptions. They are rarely measured.

CHAINBREAK asks two questions and answers them with reproducible evidence rather than
assertion:

1. **Does effective authority evolve the way the policy intended?**
   (intended authority vs. effective authority)
2. **Does authority at execution time still match authority at delegation time?**
   (delegation-time authority vs. execution-time authority)

## What CHAINBREAK is not

CHAINBREAK is a **defensive measurement instrument**, not an offensive tool. It operates
exclusively on infrastructure the operator creates for the benchmark, in an AWS account
the operator explicitly declares, using resources under a unique namespace prefix, with
only benign read/write/invoke probes against benchmark-owned markers.

It contains no capability for credential theft, authentication bypass, privilege
escalation against third parties, persistence, or monitoring evasion — and contributions
adding such capability will be rejected. See [SECURITY_MODEL.md](https://github.com/KubixDesiney/chainbreak/blob/main/SECURITY_MODEL.md) for the
enforced invariants and [THREAT_MODEL.md](https://github.com/KubixDesiney/chainbreak/blob/main/THREAT_MODEL.md) for the risk analysis.

## The five benchmark families

| Family | Question it answers | Primary measurement |
|---|---|---|
| **Scope attenuation** | Does a delegated identity ever hold authority beyond what the hop granted? | Set difference: observed capabilities − intended capabilities |
| **Delegation drift** | Across a multi-hop chain, where does effective authority first diverge from intent? | First divergence hop, per-hop gain/loss vectors |
| **Revocation propagation** | How long does previously granted authority remain effective after a policy change? | Interval between last success and first denial, with uncertainty bounds |
| **Stale authority** | Does a deferred task execute with current or historical authority? | Authority state classification at execution time |
| **Silent narrowing** | When authority is legitimately reduced, does the workload fail loudly or produce quiet partial output? | Failure transparency classification |

Each family ships with **negative controls** — intentionally misconfigured benchmark
scenarios whose divergence CHAINBREAK *must* detect. A benchmark that only ever reports
PASS has not demonstrated it can detect a failure.

## Architecture in one diagram

```text
      chainbreak CLI
            |
            v
       Safety Gate
            |
            v
     Scenario Loader
            |
            v
    Scenario Compiler
            |
            v
   Authorization Graph .......... intended authority
            |
            v
    Provider Adapter ---------->  [ controlled benchmark infrastructure ]
      (aws | fake)
            |
            v
     Execution Engine ........... delegation + probes
            |
            v
    Observation Engine .......... raw outcomes
            |
            v
  [ normalized evidence ] ....... JSONL + manifest
            |
            v
         Analysis ............... observed authority, divergence
            |
            v
         Findings
            |
            v
  Per-category scoring
            |
            v
          Report ................ terminal / HTML
```

Plain text on purpose: this file is the package description on PyPI, which renders no
diagrams. [ARCHITECTURE.md](https://github.com/KubixDesiney/chainbreak/blob/main/ARCHITECTURE.md)
carries the rendered component and data-flow diagrams.

The core benchmark engine has **no dependency on AWS IAM semantics**. Scenarios are written
against abstract *capabilities* (`objectstore.read`), which a provider adapter maps to
provider actions (`s3:GetObject`) and probe implementations. That indirection is what makes
the v0.2+ roadmap (OIDC, SPIFFE, Azure, GCP) possible without rewriting v0.1.

## Offline quickstart

```bash
chainbreak scenario validate scenarios/scope-attenuation/basic.yaml
chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake --seed 1729
chainbreak analyze <run-id>
chainbreak report <run-id> --format html
```

The wheel ships the complete 24-scenario corpus, the capability catalog, and the runtime JSON
Schemas. `chainbreak scenario list` and `chainbreak validate` use that packaged corpus by
default, so validation, fake runs, analysis, reporting, and `evidence export --archive` work
from an empty directory after installation. Repository paths such as
`scenarios/scope-attenuation/basic.yaml` remain convenient authoring paths when working from a
checkout.

The `infra` and `--provider aws` workflows are real-account operations documented in
[EXPERIMENT_PROTOCOL.md](https://github.com/KubixDesiney/chainbreak/blob/main/EXPERIMENT_PROTOCOL.md); they are not part of this offline quickstart.

## Verify this release yourself

Everything above asks you to trust a description. This section instead gives a reader who
trusts nothing a path to the same conclusion, using only a downloaded wheel, a network
connection, and no repository checkout, credentials, or AWS account.

**1. Verify the wheel.** Download `chainbreak-<version>-py3-none-any.whl` from the
[GitHub Release](https://github.com/KubixDesiney/chainbreak/releases) alongside its
`SHA256SUMS`, and check the digest:

```bash
sha256sum -c SHA256SUMS --ignore-missing
```

For a release that also carries `provenance.sigstore.json`, verify the wheel was built by this
repository's own release workflow from the tagged commit, not substituted or hand-built,
before you install it:

```bash
gh attestation verify chainbreak-<version>-py3-none-any.whl --repo KubixDesiney/chainbreak
```

See [REPRODUCIBILITY.md](https://github.com/KubixDesiney/chainbreak/blob/main/REPRODUCIBILITY.md)
for what each artifact proves and why no maintainer can publish one by hand.

**2. Install into a clean venv, from an empty directory.**

```bash
mkdir verify-chainbreak && cd verify-chainbreak
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install /path/to/chainbreak-<version>-py3-none-any.whl
```

**3. Run a packaged scenario against the fake provider, analyze it, and report it** — the
same offline quickstart above, run here against the *installed wheel* with nothing else on
disk:

```bash
scenario=$(chainbreak scenario list | grep -i 'scope-attenuation.*basic\.yaml')
chainbreak run "$scenario" --provider fake --seed 1729 --runs-root runs --run-id-file run-id.txt
chainbreak analyze "$(cat run-id.txt)" --runs-root runs
chainbreak report "$(cat run-id.txt)" --format html --runs-root runs -o report.html
```

If this completes, the wheel is not just present — it runs its whole offline pipeline
end to end.

**4. Reproduce a known-good analysis byte-for-byte.** Download this repository's
[`examples/reports/verify-golden-scope-attenuation-fake-seed1729.tar.gz`](https://github.com/KubixDesiney/chainbreak/blob/main/examples/reports/verify-golden-scope-attenuation-fake-seed1729.tar.gz)
and its sibling
[`...findings.json`](https://github.com/KubixDesiney/chainbreak/blob/main/examples/reports/verify-golden-scope-attenuation-fake-seed1729.findings.json)
— a sealed evidence bundle from the same scenario and seed as step 3, and the `findings.json`
already computed from it — then analyze the bundle exactly as it was sealed and diff:

```bash
tar xzf verify-golden-scope-attenuation-fake-seed1729.tar.gz
run_id=$(ls -d 01*/ | head -n1 | tr -d /)
chainbreak analyze "$run_id" --runs-root .
diff verify-golden-scope-attenuation-fake-seed1729.findings.json "$run_id/findings.json"
```

The diff is empty. This is REPRODUCIBILITY.md's
[Level 1 — analytical reproducibility](https://github.com/KubixDesiney/chainbreak/blob/main/REPRODUCIBILITY.md#1-three-levels-of-reproducibility):
given the same evidence bundle, `chainbreak analyze` is a pure function of its content, so
re-running it reproduces `findings.json` byte for byte. That is a stronger, different claim
than step 3 matching this bundle: every `chainbreak run` mints its own observation, event, and
finding IDs at execution time, salted per run by design (`core/ids.py`), so two independent
runs of the identical scenario and seed are never byte-identical to *each other* — only
re-analyzing one fixed, already-sealed bundle is. (`chainbreak compare` is the tool for
comparing two independent runs, and it reports `STRUCTURALLY_IDENTICAL`, never `IDENTICAL`,
for exactly this reason.) The bundle is committed unscrubbed on purpose: the fake provider's
account and namespace fields are already synthetic placeholders, so there is nothing in it to
redact, and `tests/integration/test_readme_verification_golden_bundle.py` re-checks this exact
pairing on every CI run.

**What this does not verify.** This procedure reproduces the apparatus — the wheel's contents,
its installation, and its analysis pipeline's determinism — not the AWS measurements in
[docs/research/results-v0.1.md](https://github.com/KubixDesiney/chainbreak/blob/main/docs/research/results-v0.1.md).
Those are measurements for one account, one region, and one point in time, made against
infrastructure an operator provisions and destroys under
[EXPERIMENT_PROTOCOL.md](https://github.com/KubixDesiney/chainbreak/blob/main/EXPERIMENT_PROTOCOL.md).
Reproducing them takes a dedicated AWS account of your own, not this wheel alone — follow that
protocol for that path.

## Run it in a container

Every tagged release publishes a container image to
`ghcr.io/kubixdesiney/chainbreak`, tagged with both the release version (e.g. `v0.1.1`)
and the commit SHA. It wraps the same offline, fake-provider path as the quickstart
above and nothing else — no `boto3`, no `aws` extra, no credentials, no default account
configuration (see the Dockerfile). Mount a directory for the run output and drive the
CLI exactly as above:

```bash
mkdir -p out && chmod 0777 out   # the image runs as a fixed non-root uid, not your host user

docker run --rm -v "$(pwd)/out:/home/chainbreak/runs" \
  ghcr.io/kubixdesiney/chainbreak:v0.1.1 \
  run scenarios/scope-attenuation/basic.yaml --provider fake --seed 1729 --runs-root runs

docker run --rm -v "$(pwd)/out:/home/chainbreak/runs" \
  ghcr.io/kubixdesiney/chainbreak:v0.1.1 \
  analyze <run-id> --runs-root runs
```

Replace `v0.1.1` with the release you want, or pin to the commit-SHA tag; see
[REPRODUCIBILITY.md](REPRODUCIBILITY.md) for how to verify an image against its build
provenance.

This container is scoped to the offline workflow only. `--provider aws` and `chainbreak
infra` are real-account operations governed by
[EXPERIMENT_PROTOCOL.md](https://github.com/KubixDesiney/chainbreak/blob/main/EXPERIMENT_PROTOCOL.md),
and this image cannot run them — it has no AWS SDK installed and no way to accept
credentials. Real-account work happens outside the container, following that protocol.

## Documentation map

**Start here**
- [The rendered reports](https://kubixdesiney.github.io/chainbreak/) — a real AWS measurement and an apparatus check, in a browser
- [ARCHITECTURE.md](https://github.com/KubixDesiney/chainbreak/blob/main/ARCHITECTURE.md) — components, boundaries, data flow, extension points
- [docs/GLOSSARY.md](https://github.com/KubixDesiney/chainbreak/blob/main/docs/GLOSSARY.md) — precise meaning of every term used in this repo
- [docs/CLAUDE_CODE_HANDOFF.md](https://github.com/KubixDesiney/chainbreak/blob/main/docs/CLAUDE_CODE_HANDOFF.md) — implementation contract and per-milestone prompts

**Model specifications**
- [AUTHORIZATION_MODEL.md](https://github.com/KubixDesiney/chainbreak/blob/main/AUTHORIZATION_MODEL.md) — authorization graph, divergence algorithms
- [CAPABILITY_MODEL.md](https://github.com/KubixDesiney/chainbreak/blob/main/CAPABILITY_MODEL.md) — capability abstraction and provider mapping rules
- [SCENARIO_SPECIFICATION.md](https://github.com/KubixDesiney/chainbreak/blob/main/SCENARIO_SPECIFICATION.md) — declarative scenario language v1alpha1
- [EVIDENCE_SCHEMA.md](https://github.com/KubixDesiney/chainbreak/blob/main/EVIDENCE_SCHEMA.md) — evidence bundle format and redaction contract
- [SCORING_MODEL.md](https://github.com/KubixDesiney/chainbreak/blob/main/SCORING_MODEL.md) — per-category results and why there is no composite score
- [AWS_PROVIDER_SPEC.md](https://github.com/KubixDesiney/chainbreak/blob/main/AWS_PROVIDER_SPEC.md) — IAM/STS mechanics, probe design, Terraform contract

**Security and method**
- [SECURITY_MODEL.md](https://github.com/KubixDesiney/chainbreak/blob/main/SECURITY_MODEL.md) — hard invariants and how each is enforced in code
- [THREAT_MODEL.md](https://github.com/KubixDesiney/chainbreak/blob/main/THREAT_MODEL.md) — assets, threats, mitigations, residual risk
- [RESEARCH_METHODOLOGY.md](https://github.com/KubixDesiney/chainbreak/blob/main/RESEARCH_METHODOLOGY.md) — hypotheses, variables, statistics, validity threats
- [EXPERIMENT_PROTOCOL.md](https://github.com/KubixDesiney/chainbreak/blob/main/EXPERIMENT_PROTOCOL.md) — step-by-step protocol per benchmark family
- [TESTING.md](https://github.com/KubixDesiney/chainbreak/blob/main/TESTING.md) — four-layer test strategy
- [REPRODUCIBILITY.md](https://github.com/KubixDesiney/chainbreak/blob/main/REPRODUCIBILITY.md) — what must be recorded for a run to be reproducible
- [docs/site-provenance.md](https://github.com/KubixDesiney/chainbreak/blob/main/docs/site-provenance.md) — how the published site is produced and what was proved about every file on it

**Project management**
- [PROJECT_STATUS.md](https://github.com/KubixDesiney/chainbreak/blob/main/PROJECT_STATUS.md) — durable source of truth
- [ROADMAP.md](https://github.com/KubixDesiney/chainbreak/blob/main/ROADMAP.md) — v0.1 through v0.5
- [docs/DECISIONS.md](https://github.com/KubixDesiney/chainbreak/blob/main/docs/DECISIONS.md) — ADR index
- [docs/implementation/MILESTONES.md](https://github.com/KubixDesiney/chainbreak/blob/main/docs/implementation/MILESTONES.md) — M0–M19 index

## Requirements

- Python 3.12+
- Terraform 1.9+
- An AWS account **created for this benchmark** with no production workloads
- Estimated cost per full experiment suite: **under USD 1.00** (see [AWS_PROVIDER_SPEC.md](https://github.com/KubixDesiney/chainbreak/blob/main/AWS_PROVIDER_SPEC.md#9-cost-model))

For an installed offline distribution, build or download a wheel and run `pip install
chainbreak-*.whl`. The wheel carries the complete 24-scenario corpus, runtime schemas, and
capability catalog; no checkout is needed for the fake-provider workflow or archives.

CI does **not** require AWS credentials. Unit and integration layers run entirely against a
deterministic fake provider.

## License

Apache-2.0 — the unmodified licence text is in [LICENSE](https://github.com/KubixDesiney/chainbreak/blob/main/LICENSE). [NOTICE](https://github.com/KubixDesiney/chainbreak/blob/main/NOTICE) carries an
informational statement of the authors' intended scope of use; it is not a licence term and
modifies nothing. See [SECURITY.md](https://github.com/KubixDesiney/chainbreak/blob/main/SECURITY.md) for vulnerability reporting and the same scope
of acceptable use stated at length.

## How to cite

If you use CHAINBREAK in published or reproducible research, please cite the software
itself rather than only linking to the repository. Machine-readable metadata is in
[CITATION.cff](https://github.com/KubixDesiney/chainbreak/blob/main/CITATION.cff) (use
GitHub's "Cite this repository" button, or `cffconvert`, to derive other formats).

Plain citation:

> KubixDesiney. (2026). *CHAINBREAK* (Version 0.1.1) [Computer software].
> https://github.com/KubixDesiney/chainbreak. DOI: [10.5281/zenodo.22723886](https://doi.org/10.5281/zenodo.22723886)

BibTeX:

```bibtex
@software{chainbreak,
  author  = {KubixDesiney},
  title   = {{CHAINBREAK}: An empirical benchmark for authorization behavior in
             delegated and agentic cloud systems},
  year    = {2026},
  version = {0.1.1},
  url     = {https://github.com/KubixDesiney/chainbreak},
  doi     = {10.5281/zenodo.22723886}
}
```

The `doi` field above is the **concept DOI** (`10.5281/zenodo.22723886`), which always
resolves to the latest archived version. The `v0.1.1` snapshot specifically is archived
under its own version DOI, [10.5281/zenodo.22723887](https://doi.org/10.5281/zenodo.22723887);
future archived versions will get their own version DOIs under the same concept DOI.
