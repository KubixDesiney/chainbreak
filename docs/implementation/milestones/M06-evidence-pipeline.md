# M6 — Evidence pipeline, redaction and sealing

## Purpose
Produce sealed, schema-valid, secret-free evidence bundles, and make redaction structurally
impossible to bypass. This is the highest-stakes milestone for SI-1 and EV-1.

## Dependencies
M5.

## Required components
`evidence/writer.py` (append-only JSONL streams, manifest, sealing), `evidence/redaction.py`
(the single choke point), `evidence/manifest.py`, `evidence/index.py` (SQLite),
`evidence/reader.py` (bounded, streaming, schema-validated ingest of possibly-untrusted
bundles), `evidence/export.py` (`--public` scrub with a printed diff).

## Files expected
```
src/chainbreak/evidence/{writer,redaction,manifest,index,reader,export}.py
tests/unit/{test_redaction,test_evidence_schema,test_sealing,test_bundle_ingest_safety,test_public_export_scrub}.py
tests/fixtures/bundles/{golden,tampered,malicious}/
```

## Functional requirements
- F1 Bundle layout exactly as [EVIDENCE_SCHEMA §1](../../../EVIDENCE_SCHEMA.md#1-bundle-layout).
- F2 JSONL streams are append-only and flushed per record, so an aborted run yields usable
  partial evidence.
- F3 Sealing: per-artifact SHA-256 plus a root over sorted `name:hash` pairs.
- F4 `analyze` verifies the root and refuses to produce findings on mismatch without
  `--allow-unsealed`, which stamps `bundle_root_verified: false` into every finding.
- F5 SQLite index built from bundles; `runs reindex` rebuilds from disk.
- F6 `evidence export --public` asserts zero redaction violations, no unhashed account ID,
  no ARN, no policy document unless opted in, no hostname, no cleartext session name — and
  prints a diff of what it stripped.
- F7 All identifiers salted-hashed per ADR-013; denial messages redacted **in place**,
  preserving sentence structure so `denial_attribution` survives.

## Non-functional requirements
Writing 10 000 observations under 2 s. Reader is streaming with a per-line length cap so a
hostile bundle cannot exhaust memory.

## Security requirements
- S1 SI-1: every record passes through `redact()`. A lint rule bans `json.dump` and
  `open(..., "w")` inside `evidence/` outside `writer.py`.
- S2 `redact()` **raises** `SecretLeakError` on a hit; it does not sanitize and continue.
- S3 T-10: bundle ingest is schema-validated and size-bounded; no `eval`, no dynamic import.
- S4 Coverage on `evidence/redaction.py` must be **100%**. A missed branch is a credential leak.

## Tests
`test_redaction.py` is property-based: discover every Pydantic model by reflection, populate
every string field from a synthetic secret corpus (fake AKIA/ASIA keys, JWT, PEM block,
base64 blob, session-token shape), serialize a bundle, and assert either `SecretLeakError`
or zero corpus values in the output bytes — *and* that the secret appears in no `repr`,
`str`, `format`, traceback or log record. New model fields are covered automatically because
discovery is by reflection.

## Negative controls
Seed a bundle with an ARN in every field and run `export --public`; assert all are stripped
and the diff lists them. Tamper with a golden bundle's observations; assert
`BundleIntegrityError`. Feed the malicious bundle fixture; assert bounded rejection, not a
crash.

## Acceptance criteria
1. A fake-provider run produces a sealed bundle validating against every schema in `schemas/`.
2. Redaction property test passes with 100% coverage on `redaction.py`.
3. Tamper detection works; `--allow-unsealed` stamps every finding.
4. `runs reindex` reconstructs the index from bundles alone.
5. `export --public` strips everything listed in F6 and prints the diff.

## Verification commands
```bash
pytest -m unit tests/unit/test_redaction.py --cov=chainbreak.evidence.redaction --cov-fail-under=100 -q
chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake --seed 7
python -m chainbreak.evidence.verify runs/<run-id>     # recompute root, compare
chainbreak evidence export <run-id> --public --dry-run
grep -RIEn '(AKIA|ASIA)[0-9A-Z]{16}' runs/ || echo "no key-shaped strings in evidence"
```

## Definition of done
Acceptance criteria met; EVIDENCE_SCHEMA.md updated if any field changed *and* `schemas/`
regenerated; `PROJECT_STATUS.md` updated.

## Out of scope
Findings (M7). Reports (M16). Signing (deferred to v0.2; the manifest reserves the key).

## Risks
A future model field carrying a secret without passing through `redact()`. The reflection-based
property test plus the lint rule are the mitigations; do not weaken either.
