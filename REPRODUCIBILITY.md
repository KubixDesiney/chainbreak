# CHAINBREAK Reproducibility

What must be recorded for a run to be reproducible, what "reproducible" honestly means for a
cloud-timing experiment, and how to re-run someone else's work.

---

## 1. Three levels of reproducibility

CHAINBREAK distinguishes three claims, because conflating them is how cloud research
overclaims.

**Level 1 — Analytical reproducibility.** Given the same evidence bundle, re-running
`chainbreak analyze` produces byte-identical findings. **Guaranteed** for a given CHAINBREAK
version, and tested (`test_analyze_idempotence.py`). This holds across machines and across
time because analysis is a pure function of the bundle.

**Level 2 — Structural reproducibility.** Given the same commit, the same scenario, and an
equivalently provisioned AWS account, set-valued results (observed authority, divergence,
first divergence hop) reproduce **exactly**. Expected to hold, because a policy either grants
or does not. A Level 2 failure is a real finding: it means authorization behavior is
non-deterministic where it should not be.

**Level 3 — Distributional reproducibility.** Timing results reproduce as *distributions*,
not as values. A second operator should observe an overlapping interval with a comparable
median; they will not observe the same numbers. Anyone claiming exact timing reproducibility
on a shared cloud control plane is mistaken.

Every report states which level applies to each result. Timing tables carry the sentence:
"Timing results are Level 3 (distributional). Exact values are not expected to reproduce."

---

## 2. What every run records

Automatically, in `manifest.json` and `environment.json`:

| Category | Fields |
|---|---|
| Code | `chainbreak_version`, `git_commit`, `git_dirty` |
| Definitions | `scenario.id`, `scenario.version`, `api_version`, `compiled_hash`, `capability_catalog_version`, `capability_catalog_fingerprint` |
| Provider | `provider`, `provider_adapter_version`, STS endpoint, partition, `region_hash`, `account_id_hash` |
| Infrastructure | `infrastructure_fingerprint` (hash of Terraform outputs), Terraform version, module versions |
| Configuration | `config_fingerprint` (hash of the resolved config with secrets excluded), full resolved config with values redacted |
| Randomization | every seed used (probe order shuffle, jitter, fake-provider RNG) |
| Environment | OS, arch, Python version, boto3/botocore versions, container flag |
| Timing context | clock offset estimate and method, network RTT distribution, `block_id` |
| Execution | trial counts, polling interval, concurrency setting, timeouts |

`git_dirty: true` is not blocked, but it is rendered prominently in every report and the
publication checklist ([EXPERIMENT_PROTOCOL §9](EXPERIMENT_PROTOCOL.md#9-publication-checklist))
requires a clean tree.

---

## 3. Deterministic components

These must be bit-reproducible, and each has a test:

| Component | Determinism guarantee |
|---|---|
| Scenario compilation | same doc + catalog + adapter version ⇒ identical `compiled_hash` |
| Capability resolution | catalog is a static file, version-pinned |
| Session policy synthesis | generated from bindings with sorted keys; identical bytes |
| Divergence algorithms | pure set operations over canonically ordered sets |
| Finding generation | pure function of the bundle |
| Scoring | pure function of findings |
| Evidence serialization | canonical JSON: sorted keys, fixed float formatting, UTC ISO-8601 with microseconds |
| Fake provider | fully seeded |

Canonical JSON matters more than it sounds: without fixed key ordering and float formatting,
two logically identical bundles produce different hashes, and hash comparison becomes
useless as a change-detection mechanism.

---

## 4. Non-deterministic components — and how they are handled

| Source | Handling |
|---|---|
| Network latency | Measured per probe; RTT distribution recorded; enters uncertainty |
| IAM propagation | The subject of measurement; distribution reported, never a single value |
| Provider-side load | Uncontrolled; mitigated by block randomization (C-7); `block_id` recorded |
| Throttling | Retries recorded; affected probes flagged; excluded trials counted |
| Clock drift | Monotonic-only interval math; offset recorded, never used to correct |
| ULID run IDs | Unique by design; not a reproducibility concern |
| Probe ordering | Shuffled with a **recorded seed**, so the order is reproducible on demand |

---

## 5. Re-running an experiment

**Your own run**

```bash
git checkout <git_commit_from_manifest>
chainbreak validate                                   # must pass, same allowlist
chainbreak infra apply aws-sandbox
chainbreak run scenarios/<scenario_from_manifest> --seed <seed_from_manifest>
chainbreak analyze <new_run_id>
chainbreak compare <original_run_id> <new_run_id>
```

`chainbreak compare` reports, per measurement: identical / structurally identical /
distributionally consistent / divergent, and refuses to compare runs whose `compiled_hash`,
`adapter_version`, or `catalog_version` differ without `--allow-heterogeneous` (which stamps
the comparison as lower confidence).

**Someone else's run**

You will not reproduce their `account_id_hash` or `infrastructure_fingerprint`, and that is
expected — the hashes are salted per run and the infrastructure is yours, not theirs. What
should match: `compiled_hash` (same scenario, same versions), set-valued results (Level 2),
and the *shape* of timing results (Level 3).

`chainbreak compare --cross-operator` relaxes the environment checks and reports only Level
2 and Level 3 comparisons, printing a prominent note that environment equivalence is assumed
and unverified.

---

## 6. Infrastructure reproducibility

Terraform provider versions are pinned in `versions.tf` with `~>` minor pinning, and the
lock file is committed (the *Terraform* lock file is committed; the `.terraform` directory
and state are not). Module inputs are recorded in the run's `infrastructure_fingerprint`.

An unavoidable gap: Terraform can reproduce the *declared* configuration, not the provider's
internal state. Two accounts with identical Terraform can behave differently in propagation
timing. This is named as an external-validity threat in
[RESEARCH_METHODOLOGY §9](RESEARCH_METHODOLOGY.md#9-threats-to-validity) rather than papered
over.

---

## 7. Reproducing without AWS

Every analysis path is reproducible offline against the fake provider:

```bash
chainbreak run scenarios/delegation-drift/four-hop.yaml \
  --provider fake --fake-profile deterministic --seed 1729
```

This produces a real, sealed, schema-valid evidence bundle with known ground truth. It
reproduces exactly, on any machine, forever. It proves the analysis is correct; it proves
nothing about AWS. Reports generated from a fake-provider run are stamped
`provider: fake` in the header and in every figure caption, so a fake-provider report can
never be mistaken for a measurement. This is enforced in the reporting layer, not left to
the operator.

---

## 8. Archival

A bundle intended for long-term reference should be exported with
`chainbreak evidence export <run> --archive`, which produces a self-contained `.tar.gz`
containing the scrubbed bundle, the resolved (compiled) scenario, the capability catalog as
it was at run time, the JSON Schemas, and a `REPRODUCE.md` generated with the exact commands
and versions. Schemas are included because a bundle without its schema is uninterpretable
once the schema evolves. `--archive` implies `--public` scrubbing unconditionally
(`evidence/archive.py`) -- there is no flag combination that produces an unscrubbed archive.

`--archive` refuses to run rather than silently mislabeling the environment if the
packaged `catalog.yaml` does not match the run's recorded `capability_catalog_version` or
`capability_catalog_fingerprint`, and refuses if the installed distribution does not carry
its packaged JSON Schemas. It loads both through `importlib.resources`, so an archive does
not require a repository checkout.

Bundles are gitignored by default. Publishing one is a deliberate, reviewed action.

---

## 9. Version compatibility

| Change | Effect on comparability |
|---|---|
| CHAINBREAK patch | Findings comparable; analyzer version recorded |
| CHAINBREAK minor | Analysis may change; re-run `analyze` on stored bundles to compare fairly |
| Capability catalog minor (new capability) | Old bundles remain valid; new capability is `NOT_MEASURED` in them |
| Capability catalog major (renamed/changed semantics) | Bundles **not** comparable; `compare` refuses |
| Adapter version minor | Probe behavior may differ; comparison allowed with a warning |
| Scenario version bump | Different `compiled_hash`; not directly comparable |
| Evidence format version | Migration tool provided; original preserved |

The rule underneath all of these: **the evidence bundle is the durable artifact, and it
carries everything needed to interpret itself.** Reports are disposable; bundles are not.
