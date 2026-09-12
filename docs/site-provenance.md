# Site and release-asset provenance

How the GitHub Pages site at <https://kubixdesiney.github.io/chainbreak/> is produced, and
what was proved about every file before it was published.

## What is published

| Page | Source bundle | Provider |
|---|---|---|
| `index.html` | — (landing page) | carries both stamps |
| `aws-scope-attenuation.html` | `examples/reports/aws-m17-valid-block01-scrubbed-sample.tar.gz`, run `01M0A5WS8Q912NJSP0FEH1DWSK` | `aws`, eu-west-3 |
| `apparatus-check-fake.html` | `examples/reports/apparatus-check-fake-scope-attenuation.tar.gz`, run `01M080YJ8MFNMNJE5VSTCF8CYD` | `fake` |

No report page is hand-written. `scripts/build_site.py` extracts the bundle from the committed
archive and re-renders it with `chainbreak report --format html`, then injects a site-level
provenance banner *ahead of* the report's own header. It adds a stamp; it never edits a
rendered finding. Rebuild and re-verify with:

```bash
python scripts/build_site.py
python scripts/verify_public_site_scrub.py site
```

Every page — landing included — carries the provider stamp and the measured-scope caveat. The
fake-provider page is stamped `FAKE-PROVIDER APPARATUS CHECK` by the rendering layer itself
(`reporting/language.py`), in the header and in every figure caption, *and* by the site banner.

## The scrub gate

`scripts/verify_public_site_scrub.py` is the publication gate. It does not reimplement the
scrubbing rules: it imports the same compiled patterns `chainbreak evidence export --public`
uses (`ARN_PATTERN`, `ACCOUNT_ID_PATTERN`, `HOSTNAME_PATTERN`, `NAMESPACE_PATTERN`,
`SESSION_NAME_PATTERN`, `_POLICY_DOCUMENT_PATTERN`, `_SECRET_PATTERNS`, `_BASE64_BLOB`) and
applies them to containers the exporter has no entry point for:

- rendered `.html` pages and `.md` reports,
- the HTML-entity-decoded text of the same bytes, so `&#34;arn:aws:…&#34;` cannot hide behind
  an escape that a browser will happily render,
- every member of every `.tar.gz`, read without extracting to disk.

Classes checked are the ones EVIDENCE_SCHEMA.md section 11 requires and
`docs/research/history-scan.md` scanned for: account ID, ARN, hostname, namespace, session
name, policy document, credential-shaped material.

Exemptions are narrow, named, and printed with counts in every run, because an exemption
nobody can see is indistinguishable from a leak nobody noticed. They are tested in
`tests/unit/test_public_site_scrub_gate.py` against the regression below — an exemption that
would have suppressed it is a bug.

## Why the exporter could not simply be re-run over these files

`export_public()` walks a *sealed bundle directory*: it reads `manifest.json`, verifies the
integrity root, and scrubs a fixed artifact list. Two consequences:

1. **It has no path for a rendered HTML or Markdown file.** A report is a derived artifact, not
   a bundle member. The gate above closes that gap; regenerating the page from the bundle, as
   `build_site.py` does, closes it from the other side.
2. **It refuses on an already-scrubbed bundle.** Scrubbing rewrites artifacts *after* sealing,
   so the manifest root no longer matches the bytes. All four scrubbed sample archives fail
   `verify()` for exactly this reason, with mismatches confined to the artifacts the scrub
   touched.

This is a real tension, not a bug: you can publish the measurement or you can publish a bundle
whose root verifies, not both. CHAINBREAK keeps the *original* root rather than re-sealing over
the scrub — re-sealing would produce a bundle that verifies against a document no measurement
ever produced — and stamps every derived finding `bundle_root_verified: false`. Both report
pages say so in their own header. Reading a published archive therefore requires
`--allow-unsealed`, and that flag is doing honest work.

## Regression this gate caught

`examples/reports/aws-m17-block04-excluded-scrubbed-sample.tar.gz` was committed on 2026-08-17
in `795d5c4`, labelled *scrubbed*. `NAMESPACE_PATTERN` was added to the exporter's `_scrub_text`
on 2026-08-18 in `a72ce2c`. The archive therefore predated namespace scrubbing by one day and
still carried a live `cb-` benchmark namespace in 67 places across `environment.json` (1) and
`observations.jsonl` (66) — both artifacts the exporter *would* scrub today.

`docs/research/history-scan.md` did not catch it: that scan covered the tracked tree and Git
history as text, and the namespace was inside a gzip member, invisible to a text scan of the
blob. It is the tar-walking pass in this gate that surfaced it.

Remediated on 2026-09-12 by re-running the current `_scrub_text` over every
`_PUBLIC_ARTIFACTS` member of the archive and repackaging, then re-asserting with the
exporter's own `_assert_clean`. The namespace value is deliberately not reproduced here, per
the convention `history-scan.md` follows.

| | |
|---|---|
| identifiers stripped | 67 (namespace) |
| sha256 before | `49c1c67540a729ae6f80e90d514fb7a016b8ba343182cacc6c9d2eafbdb5b097` |
| sha256 after | `4398ae44fd9af0bacb0c5468b35da9e9bb26012e92494ed49b948d76b77e6239` |

The other three archives (`block07`, `valid-block01`, `apparatus-check-fake`) were produced on
or after 2026-08-18 and carry only the `cb-00000000` redaction placeholder.

## Known scrubber artifact

`ACCOUNT_ID_PATTERN` matches any 12 consecutive decimal digits, including a run that occurs by
coincidence inside a SHA-256 hex digest. In the committed bundles this has already mangled
`provenance.capability_catalog_fingerprint`, which reads
`sha256:c420b269517eb743075d384a0c<REDACTED_ACCOUNT>f6e1e…`. The digest is cosmetically damaged
in the published copies; the unscrubbed value is intact in the run bundles. The gate recognises
this case (`account_id: 12 digits interior to a SHA-256 hex digest`) and does not block on it.
Narrowing the pattern so it does not fire inside a hex run is worth doing in v0.2.

## CI

`.github/workflows/pages.yml` rebuilds the site and runs the gate on every push to `main` that
touches the site inputs. **The deploy step is downstream of the gate**: a non-zero exit from
`verify_public_site_scrub.py` fails the job before anything is uploaded, so the published site
can never contain a file that has not passed.
