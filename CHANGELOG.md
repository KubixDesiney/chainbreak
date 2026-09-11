# Changelog

All notable changes to CHAINBREAK are recorded here.

## v0.1.1 - 2026-09-10

First release published to PyPI. `v0.1.0` was tagged and released on GitHub but never uploaded
to any package index; the defects below were found during publication preparation, and PyPI
versions are immutable, so they were fixed under a new version rather than shipped once and
corrected afterwards.

- Fixed the source distribution, which carried 744 untracked files from `.claude/worktrees/`
  (4.83 MB, 48% of the unpacked tarball, two stale duplicates of the working tree). Hatchling's
  default sdist selection is "everything under the project root that `.gitignore` does not
  match", which includes untracked files, so the published archive was a function of the
  builder's working directory rather than of the tagged commit — the same tag built on a clean
  clone produced a different tarball, contradicting `REPRODUCIBILITY.md`. `pyproject.toml` now
  declares an explicit sdist allowlist. No credential or account ID had reached the archive;
  the defect was reproducibility and uncontrolled contents, not disclosure.
- Added `scripts/check_dist_contents.py` and wired it into CI. It asserts that both artifacts
  carry the full 24-scenario corpus, all 12 runtime schema files, the capability catalog and
  the typing marker, and that the sdist's top-level entries match the declared allowlist.
- Fixed the CI `wheel` job, which built `--wheel` only and never built or inspected the sdist.
  That is why the defect above survived to a tagged release. It now builds both artifacts and
  runs the contents check.
- Added `.github/workflows/release.yml`, publishing through GitHub Trusted Publishing (OIDC).
  No PyPI API token exists for this project and none is to be created.
- Replaced the deprecated PEP 621 `license = { text = ... }` table with the PEP 639 SPDX
  expression `license = "Apache-2.0"` plus explicit `license-files`, and raised the Hatchling
  floor to `>=1.27` accordingly. The licence itself is unchanged.
- Corrected `Development Status :: 2 - Pre-Alpha` to `3 - Alpha`. Pre-Alpha asserts the project
  is not usable, which 1,815 passing tests, a shipped CLI and published real-AWS measurements
  contradict. Beta would assert feature-completeness and a stable API, which the `v1alpha1`
  scenario schema and the v0.2+ provider work contradict just as plainly. Alpha is the claim
  the evidence actually supports.
- Expanded the classifier set and added `Repository`, `Changelog` and `Security` project URLs.
- Added the `src/chainbreak/py.typed` marker. `mypy --strict` has been a merge gate throughout,
  but the marker's absence meant none of that typing reached anyone who installed the package.
- Rewrote all 28 relative links in `README.md` as absolute URLs. PyPI does not rewrite relative
  links the way GitHub does, so every one of them — the whole documentation map — resolved to a
  404 on the package page. Replaced the Mermaid architecture diagram, which PyPI renders as raw
  source, with a plain-text diagram that renders on both surfaces.
- Shortened the README status blockquote from 62 lines to 11, keeping the measured-only
  caveat and delegating the per-milestone detail to `PROJECT_STATUS.md`.
- Removed a stale empty `.release-gate-temp-*` directory from the repository root.

## v0.1.0 - 2026-09-04

- Replaced the `LICENSE` stub with the complete, unmodified Apache-2.0 text, and moved the
  acceptable-use statement out of `LICENSE` into a separate `NOTICE` file so the licence is
  unambiguously Apache-2.0 with no added terms. The same statement remains in `SECURITY.md`.
- Pointed `SECURITY.md` at GitHub Security Advisories only; the previous pointer to a
  maintainer address in `pyproject.toml` was broken, because no such address exists there.

- Completed three valid real-AWS M17 blocks on 2026-08-18 (`n=32`, `n=23`, `n=32`), with all
  six negative controls `DETECTOR_OK`, complete analysis/export, and exact cleanup. Added the
  valid run index and measured-only results record; earlier AWS attempts remain excluded.
- Exercised AWS compare, cross-operator confidence, heterogeneous refusal/lower-confidence
  behavior, empty-directory archive analysis, and synthetic bundle migration on valid AWS
  bundles. The results record preserves the measured `n`, mechanism, region, and scope.
- Fixed public-export account-ID boundaries so decimal timing values remain valid JSON; hardened
  public export against live benchmark namespaces and session names; fixed ARN scrubbing so
  adjacent JSON fields remain valid; generated a valid-block scrubbed report and sample archive.
- Reconciled M17/M18/M19 status across the code, schemas, methods, README, portfolio story,
  reports, run index, and lab log; recorded the owner-only publication boundary.
- Restored the fake provider's stale-authority negative-control contract so the full suite and
  AWS repair path model future-issuance denial while preserving an existing session.
- Added the platform-specific Windows wheel hash observed during verification; the lock remains
  generated for and verified against the CI Linux target.
- Added the M17 W03 exclusion record, explicitly labelled fake-provider apparatus outputs, and
  recorded the current tree/history scan. Scrubbed the confirmed historical account-ID finding
  from active Git history and retained a private local recovery bundle. No v0.1.0 tag or
  publication was created.

### Scope of what the v0.1.0 release measures

Three valid real-AWS blocks in `eu-west-3` on 2026-08-18 (`n=32`, `n=23`, `n=32` — 87 analyzed
runs). All six negative controls `DETECTOR_OK` in each block. Blocks 05, 06 and 07 remain
explicitly excluded and are labelled as such. Every other benchmark family result in this
candidate comes from the deterministic fake provider and is labelled an apparatus check, not an
AWS measurement. Measured values hold for that account, that region, and that time only.

IAM cleanup completed 2026-09-01 — the temporary benchmark `sts:AssumeRole` permission was
removed and the account verified clean. The final read-only release gate passed on 2026-09-04;
the annotated `v0.1.0` tag and GitHub release were published from the green release commit.

Historical M17/M18 bundles, lab records, and synthetic fixtures intentionally retain
`0.1.0a0` in their `chainbreak_version` provenance. Those values describe the runtime that
created the historical evidence and are not current package-version metadata.

The `v0.1.0` release is published with the verified wheel and scoped release notes.
