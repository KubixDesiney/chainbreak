# M19 — Portfolio and public release

## Purpose
Ship v0.1.0: a coherent, honest, reviewable open-source artifact.

## Dependencies
M18.

## Required components
Documentation consistency pass, the portfolio narrative, a release checklist, and a tag.

## Files expected
```
docs/PORTFOLIO_STORY.md      # exists; update with what was actually measured
docs/research/results-v0.1.md
CHANGELOG.md
examples/reports/             # scrubbed sample report from a real run
LICENSE                       # Apache-2.0
```

## Functional requirements
- F1 Full consistency review: scenario schema ↔ domain models ↔ graph ↔ provider abstraction
  ↔ capability model ↔ AWS adapter ↔ Terraform ↔ tests ↔ evidence ↔ findings ↔ scoring ↔
  README. Resolve every contradiction; do not paper over one.
- F2 `PORTFOLIO_STORY.md` updated to describe **only measured results**, each with its run ID.
- F3 `CHANGELOG.md` for v0.1.0.
- F4 A scrubbed sample report from a real run under `examples/`.
- F5 README status block matches `PROJECT_STATUS.md` exactly.
- F6 Every documented command works as documented, verified by executing each one.

## Non-functional requirements
A new reader reaches a running fake-provider benchmark within 10 minutes of the README.

## Security requirements
- S1 No published artifact contains an account ID, ARN, hostname, or session name. Verified
  by scanning every file in the release.
- S2 `SECURITY.md` reporting path is live.
- S3 No credential in git history — verified with a history scan, not just a working-tree scan.

## Tests
Full suite green. Every negative control `DETECTOR_OK`. Documentation link checker clean.
Every code block in the README executed.

## Negative controls
Grep the entire repository **and its history** for account-ID and key-shaped patterns. Ask a
reviewer unfamiliar with the project to follow the README from scratch on a clean machine and
record where they get stuck.

## Acceptance criteria
1. Consistency review complete; every contradiction resolved and recorded in DECISIONS.md.
2. No unmeasured result is described as measured, anywhere.
3. README status matches PROJECT_STATUS.md.
4. Every documented command executes successfully.
5. No sensitive value in the repository or its history.
6. Sample report published and scrubbed.
7. v0.1.0 tagged.

## Verification commands
```bash
make lint types test schemas
for f in scenarios/**/*.yaml; do chainbreak scenario validate "$f"; done
chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake --seed 1
git log -p | grep -nEi '(AKIA|ASIA)[0-9A-Z]{16}|aws_secret_access_key' && echo FAIL || echo clean
grep -rEn '(?<![0-9])[0-9]{12}(?![0-9])' --include='*.md' --include='*.yaml' . || echo "no account ids"
git tag -a v0.1.0 -m "CHAINBREAK v0.1.0"
```

## Definition of done
All acceptance criteria met. `PROJECT_STATUS.md` reflects the released state, including an
explicit list of what remains unmeasured.

## Out of scope
v0.2 features. Marketing. Conference submissions.

## Risks
The strongest temptation in the project arrives here: describing the *architecture* as if it
were *results*. The architecture is real and defensible; the measurements are whatever M17
actually produced. Say both, accurately, and the artifact is stronger than an overclaim would
have made it.
