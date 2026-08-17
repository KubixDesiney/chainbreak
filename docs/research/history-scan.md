# Tracked tree and Git history scan

Scan date: 2026-08-17. The scan covered `git ls-files` in the working tree and every commit
reachable from `git rev-list --all`. Values are deliberately omitted from this report.

## Findings

- Live account ID: none in the current tracked tree. The historical diff for
  `docs/implementation/NEXT_PROMPTS.md` contains the live account ID in commits
  `1c934ea5fd2d860d15ad9b679530980d4e9c1bc4` and
  `c500ed83fe10cf43ff879c42e87c198840421e98`. This is a history finding; it was not rewritten.
- Live-account ARN: no match was found in the current tree or history for an ARN containing
  that account. Generic ARN examples and generated/test ARN strings remain in code and tests,
  including `AWS_PROVIDER_SPEC.md`, `src/chainbreak/providers/aws/`, `infra/terraform/`, and
  `tests/`; they are not account-specific evidence.
- Namespaces: historical excluded-attempt namespace strings are recorded in
  `docs/research/lab-log.md` and `PROJECT_STATUS.md`; the current public wording uses
  `NAMESPACE_SCRUBBED` instead of a live namespace. The scan also finds synthetic
  `cb-xxxxxxxx` fixtures in `tests/fixtures/`, provider code, and tests. Exact values are
  omitted here.
- Hostnames: current matches are generic AWS service endpoints in
  `src/chainbreak/providers/aws/`, Terraform modules, bootstrap code, and AWS tests. No
  account-specific resource hostname was found. Historical bundles are ignored runtime data;
  their `sts.example.invalid` endpoint is explicitly non-real apparatus.
- Session names: current matches are role/session format examples and construction code in
  `src/chainbreak/providers/aws/` and `tests/`; no live session name was found in the tracked
  tree or history.
- Credential-shaped strings: current matches are deliberate redaction/secrets fixtures in
  `tests/unit/test_secrets.py`, `tests/unit/test_redaction.py`,
  `tests/unit/test_logging_filter.py`, and `tests/unit/test_domain_contract.py`. No live key,
  private-key block, or credential value was found. The same fixture paths recur in history;
  they are test inputs, not credentials.

## Release implication

The historical live-account finding requires an owner decision about history rewriting before
any publication. This task did not rewrite history, force-push, tag, create a GitHub release,
or publish anything.
