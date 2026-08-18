# Tracked tree and Git history scan

Scan date: 2026-08-18. The scan covered every path from `git ls-files`, every commit reachable
from `git rev-list --all`, and Git diffs searched with account-ID, ARN, namespace, hostname,
session-name, and credential-shaped patterns. Values are deliberately omitted.

## Findings

- Current tracked tree: no account-specific live account ID, ARN, hostname, namespace, session
  name, access key, private-key block, or credential value was found. The 12-digit account-ID
  pattern appears only in documented fake/example/fixture paths, including
  `chainbreak.example.toml`, `EVIDENCE_SCHEMA.md`, `infra/terraform/environments/aws-sandbox/
  terraform.tfvars.example`, `infra/terraform/environments/local-development/variables.tf`,
  `src/chainbreak/cli/run.py`, provider test fixtures, and redaction tests. These are apparatus
  inputs or construction code, not live account evidence.
- Historical live account finding: the account-ID pattern occurred in
  `docs/implementation/NEXT_PROMPTS.md` in commits
  `1c934ea5fd2d860d15ad9b679530980d4e9c1bc4` and
  `c500ed83fe10cf43ff879c42e87c198840421e98`. The value is not reproduced here. This is the
  exact history finding that requires an owner decision before publication; history was not
  rewritten.
- Historical namespace-shaped matches occur in `docs/research/lab-log.md`, `PROJECT_STATUS.md`,
  and `docs/implementation/NEXT_PROMPTS.md` across the historical experiment commits. Current
  code/test matches are intentional placeholders and fixtures in
  `src/chainbreak/evidence/redaction.py`, `src/chainbreak/providers/aws/`,
  `src/chainbreak/providers/fake/`, `tests/fixtures/`, and `tests/unit/`; live namespaces are
  scrubbed from current public documentation and artifacts. Exact namespace values are omitted.
- ARN-shaped matches in the current tree are construction/example/test paths:
  `AWS_PROVIDER_SPEC.md`, `CAPABILITY_MODEL.md`, `infra/terraform/`, `scripts/bootstrap_aws_config.py`,
  `src/chainbreak/providers/aws/`, `tests/aws/`, `tests/fixtures/`, and `tests/unit/`. No
  account-specific live ARN was found in the current tree or history. Exact ARN values are
  omitted.
- Hostname-shaped matches are generic AWS endpoints in
  `infra/terraform/modules/benchmark-account/main.tf`,
  `infra/terraform/modules/observability/main.tf`,
  `infra/terraform/modules/resources/main.tf`, `scripts/bootstrap_aws_config.py`, and AWS
  tests. No account-specific resource hostname was found. Exact hostnames are omitted.
- Session-name matches are schema fields, format examples, and construction code in
  `src/chainbreak/providers/aws/`, `src/chainbreak/providers/fake/session.py`, schemas, and
  tests. No live session name was found. Exact values are omitted.
- Credential-shaped matches are deliberate schema names and test fixtures in
  `src/chainbreak/core/secrets.py`, `src/chainbreak/providers/aws/session.py`,
  `src/chainbreak/evidence/redaction.py`, `tests/unit/test_secrets.py`,
  `tests/unit/test_redaction.py`, `tests/unit/test_logging_filter.py`, and
  `tests/unit/test_domain_contract.py`. No access key, private-key block, secret value, or
  credential-shaped live value was found. The history regex also matched fixture/schema changes
  in commits `20a71bfdcea54cd6ab58ff18af4ba965a5cba988`,
  `464aecd7c127a9f47c33659077fbb95b81239e19`,
  `830b4199afebe794a8252379365aaf0e5390fc56`,
  `832f240c56808637fb1ff61536cb1c8952a7f160`,
  `879f766ae41ca4886691c88671af18be01613b0a`,
  `c4f32bd99263e13ee68c96898f454f21ba348f34`, and
  `ed0fa3ba1982550a3743f950310b4ad9b6a6d069`; these are code/schema/test additions, not
  credential disclosures.

## Release implication

The current tree is scrubbed for the scanned classes. The two historical account-ID findings
remain in Git history and are reported exactly by path and commit above without printing the
value. The owner must decide whether to rewrite history before publication. This pass did not
rewrite history, force-push, tag, create a GitHub release, or publish anything.
