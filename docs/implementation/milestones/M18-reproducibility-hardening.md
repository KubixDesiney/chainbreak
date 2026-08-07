# M18 — Reproducibility and hardening

## Purpose
Make runs comparable, bundles archivable, and the whole thing runnable by someone who is not
the author.

## Dependencies
M17.

## Required components
`analysis/compare.py` (three-level comparison), `evidence/archive.py`,
`evidence/migrate.py`, a Dockerfile, and the CI hardening deferred from M0.

## Files expected
```
src/chainbreak/analysis/compare.py
src/chainbreak/evidence/{archive,migrate}.py
Dockerfile
.dockerignore
docs/research/lab-log.md                  # completed for v0.1
tests/unit/{test_compare,test_archive,test_migrate}.py
```

## Functional requirements
- F1 `chainbreak compare A B` reports per measurement: identical / structurally identical /
  distributionally consistent / divergent, mapped to the three levels in
  [REPRODUCIBILITY §1](../../../REPRODUCIBILITY.md#1-three-levels-of-reproducibility).
- F2 Refuse to compare across differing `compiled_hash`, `adapter_version` or
  `catalog_version` without `--allow-heterogeneous`, which lowers confidence.
- F3 `--cross-operator` relaxes environment checks and prints a prominent note that
  environment equivalence is assumed and unverified.
- F4 `evidence export --archive` produces a tarball with the bundle, the resolved scenario,
  the catalog **as it was at run time**, the JSON Schemas, and a generated `REPRODUCE.md`
  with exact commands and versions. Schemas are included because a bundle without its schema
  is uninterpretable once schemas evolve.
- F5 Format migration between evidence versions, preserving the original.
- F6 Docker image producing byte-identical fake-provider runs across machines.

## Non-functional requirements
Docker image under 500 MB. `compare` under 2 s for two 10 000-observation bundles.

## Security requirements
- S1 `--archive` implies `--public` scrubbing; there is no unscrubbed archive path.
- S2 The Docker image contains no credentials and no AWS configuration.
- S3 Dependency lockfile with hashes; `pip install --require-hashes` in CI (T-14).

## Tests
`test_compare.py` covers all three levels including the negative case: two runs that should
be structurally identical but are not, which is itself a finding about non-determinism in
authorization behavior.

## Negative controls
Run the same fake scenario twice with the same seed; `compare` must report identical. Change
the seed; must report distributionally consistent but not identical. Change the catalog
version; must refuse without the flag.

## Acceptance criteria
1. `compare` correctly classifies all three levels.
2. Archive is self-contained: a fresh machine can interpret it with no repository access.
3. Docker produces byte-identical fake runs on two different hosts.
4. Migration preserves the original bundle.
5. `pip install --require-hashes` succeeds in CI.

## Verification commands
```bash
chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake --seed 42
chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake --seed 42
chainbreak compare <run-a> <run-b>                        # expect: identical
chainbreak evidence export <run-a> --archive -o /tmp/a.tar.gz && tar tzf /tmp/a.tar.gz
docker build -t chainbreak . && docker run --rm chainbreak run \
  scenarios/scope-attenuation/basic.yaml --provider fake --seed 42
```

## Definition of done
Acceptance criteria met; REPRODUCIBILITY.md updated to match what was implemented;
`PROJECT_STATUS.md` updated.

## Out of scope
Signing (v0.2). Remote state. A hosted results database.

## Risks
An archive that silently depends on repository files. Test by extracting into a container
with no repo checkout.
