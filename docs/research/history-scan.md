# Tracked tree and Git history scan

Scan date: 2026-09-04. The scan covered every path from `git ls-files`, every commit reachable
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
- Pre-scrub historical live account finding: the account-ID pattern occurred in
  `docs/implementation/NEXT_PROMPTS.md` in commits
  `1c934ea5fd2d860d15ad9b679530980d4e9c1bc4` and
  `c500ed83fe10cf43ff879c42e87c198840421e98`. The value is not reproduced here. This is the
  exact finding that was remediated. Active refs were rewritten and rescanned with zero
  historical account-ID matches; the pre-scrub objects are retained only in a private local
  recovery bundle outside the repository refs.
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

The current tree is scrubbed for the scanned classes. The two pre-scrub historical account-ID
findings are reported exactly by path and commit above without printing the value; active refs now
contain zero matches. Temporary benchmark IAM cleanup completed 2026-09-01 with the account
verified clean. The final release gate completed on 2026-09-04; the annotated `v0.1.0` tag and
GitHub release were published from the verified release commit. This scan records the scrubbed
state that preceded publication.

---

## Addendum: archive-member scan, 2026-09-12

The scan above covered the tracked tree and Git history **as text**. It did not look inside
gzip members, and one live value was hiding there.

Scan date: 2026-09-12, covering every file staged for the GitHub Pages site and every archive
staged as a v0.1.0 release asset, using `scripts/verify_public_site_scrub.py` — which imports
the exporter's own compiled patterns and walks `.tar.gz` members and HTML-entity-decoded text
in addition to raw bytes. Values are deliberately omitted, as above.

- **Finding.** `examples/reports/aws-m17-block04-excluded-scrubbed-sample.tar.gz` carried a live
  `cb-` benchmark namespace in 67 places: `environment.json` (1) and `observations.jsonl` (66).
  The archive was committed 2026-08-17 in `795d5c4`; `NAMESPACE_PATTERN` was added to
  `chainbreak.evidence.export._scrub_text` on 2026-08-18 in `a72ce2c`. The archive therefore
  predated namespace scrubbing by one day while being labelled scrubbed. Both artifacts are in
  `_PUBLIC_ARTIFACTS` and would be scrubbed by the current exporter.
- **Why the 2026-09-04 scan did not report it.** That scan searched the tracked tree and Git
  diffs as text. The namespace was inside a gzip blob, which a text scan cannot see.
- **Remediation.** Re-ran the current `_scrub_text` over every `_PUBLIC_ARTIFACTS` member and
  repackaged, then re-asserted with the exporter's own `_assert_clean`. 67 identifiers stripped.
  The archive's sha256 changed from `49c1c675…b5b097` to `4398ae44…7e6239`.
- **Other archives.** `aws-m17-block07-scrubbed-sample.tar.gz`,
  `aws-m17-valid-block01-scrubbed-sample.tar.gz` and
  `apparatus-check-fake-scope-attenuation.tar.gz` were produced on or after 2026-08-18 and carry
  only the `cb-00000000` redaction placeholder. No ARN, hostname, session name, policy document
  or credential-shaped value was found in any scanned file, in any container.
- **Integrity note, not a finding.** All four scrubbed archives fail `manifest.verify()`, with
  mismatches confined to exactly the artifacts the scrub rewrote. This is inherent to scrubbing
  after sealing and is why reading a published bundle requires `--allow-unsealed`; see
  `docs/site-provenance.md`.

### Release implication

The site and the release assets are clean for the scanned classes as of 2026-09-12. The gate now
runs in CI (`.github/workflows/pages.yml`) upstream of the upload step, and its exemptions are
regression-tested against this exact finding in `tests/unit/test_public_site_scrub_gate.py`.
