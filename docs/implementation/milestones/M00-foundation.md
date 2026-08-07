# M0 — Repository foundation and toolchain

## Purpose
Make the repository buildable, lintable, type-checkable and testable, with CI enforcing the
structural rules the rest of the project depends on. Nothing measures anything yet; the
point is that every later milestone lands on rails.

## Dependencies
None. Some artifacts already exist (see "Existing work to preserve").

## Existing work to preserve
`pyproject.toml`, `.gitignore`, every root document, `src/chainbreak/` package skeleton with
`core/{enums,errors,ids,secrets,models}.py`, `capabilities/{catalog.yaml,loader.py}`,
`scenarios/{schema,safety,export_schema}.py`, `schemas/*`, `scenarios/*`,
`tests/unit/test_domain_contract.py`, `tests/scenarios/test_scenario_corpus.py`.
**Do not rewrite these.** M0 adds tooling around them.

## Required components
Editable install; ruff + mypy configured (already in `pyproject.toml`); `import-linter`
contracts encoding ARCH-1; pre-commit hooks; GitHub Actions CI; a `Makefile` or `justfile`
for the common commands; `chainbreak.example.toml`.

## Files expected
```
.github/workflows/ci.yml
.github/workflows/aws-experiment.yml        # workflow_dispatch only, OIDC, no static keys
.pre-commit-config.yaml
.importlinter                                # or [tool.importlinter] in pyproject
Makefile
chainbreak.example.toml
tests/unit/test_import_boundaries.py
tests/conftest.py                            # shared fixtures, marker enforcement
```

## Functional requirements
- F1 `pip install -e ".[dev]"` succeeds on Python 3.12 and 3.13.
- F2 `make lint`, `make types`, `make test`, `make schemas` all work.
- F3 `make schemas` regenerates `schemas/*.json` and CI fails if the diff is non-empty.
- F4 Pytest markers `unit`, `integration`, `aws`, `e2e`, `slow` are registered and
  `--strict-markers` is on.
- F5 `aws` and `e2e` markers skip with an explanatory message unless
  `CHAINBREAK_ALLOW_AWS_TESTS=1`.

## Non-functional requirements
`pytest -m unit` under 30 s. CI under 5 minutes. Every third-party action pinned to a full
commit SHA.

## Security requirements
- S1 CI's default workflow requires **no** cloud credentials (T-12).
- S2 `aws-experiment.yml` is `workflow_dispatch` only, bound to a GitHub environment with
  required reviewers, uses OIDC role assumption, and is never triggered by `pull_request`.
- S3 A CI job fails the build on a state-shaped file (`*.tfstate`, `*.tfvars`) in the diff.
- S4 `bandit -r src/` and `pip-audit` run and must pass.
- S5 Minimum `permissions:` per job.

## Tests
`test_import_boundaries.py`: `core/` imports nothing from CHAINBREAK; `graph/` imports only
`core/`; no `boto3` import outside `providers/aws/`; no AWS service string
(`s3:`, `arn:aws`, `dynamodb:`, `sts:`) outside `providers/` and `AWS_PROVIDER_SPEC.md`.
Plus a CI lint asserting no workflow uses `pull_request_target` and every action is
SHA-pinned.

## Negative controls
Add a temporary file importing `boto3` in `src/chainbreak/graph/`; confirm the boundary test
fails. Add a file with a naive `datetime.now()`; confirm `ruff` DTZ fails. Remove both.

## Acceptance criteria
1. Fresh clone → `pip install -e ".[dev]"` → `make test` green.
2. `make lint`, `make types`, `make schemas` clean; schema diff empty.
3. `test_import_boundaries.py` passes and demonstrably fails on a planted violation.
4. CI green on a PR with no AWS credentials configured.
5. `pytest -m aws` skips with a clear message.

## Verification commands
```bash
pip install -e ".[dev]" && make lint && make types && make test && make schemas
git diff --exit-code schemas/
pytest -m aws -q            # expect: skipped, with reason
```

## Definition of done
All acceptance criteria demonstrated with pasted output; `PROJECT_STATUS.md` shows M0
complete and M1 as the next action.

## Out of scope
Any benchmark logic. Provider code. Terraform. Docker (deferred to M18).

## Risks
Over-strict `mypy --strict` on Pydantic without the plugin — the plugin is already
configured, keep it. Import-linter contracts that are too coarse to catch real violations;
verify with the planted-violation control rather than assuming.
