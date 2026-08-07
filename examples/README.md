# Examples

## Current contents

Nothing yet. This directory will hold:

- `reports/` — a scrubbed sample HTML report (M16 adds a fake-provider sample; M19 adds one
  from a real run).
- `bundles/` — a small exported evidence bundle demonstrating the format.

## Reading a sample report

Every report carries a provenance header. Check it first:

- **`provider: fake`** means the report was produced by the deterministic laboratory. It
  demonstrates the analysis, the finding structure and the rendering — and it says **nothing
  about AWS**. Fake-provider runs are stamped in the header and in every figure caption, by
  the rendering layer rather than by operator discipline, so this cannot be missed.
- **`provider: aws`** means real measurement, and the header carries the run ID, region hash,
  adapter version and block ID needed to interpret it.

## Trying it yourself, without AWS

```bash
pip install -e ".[dev,report]"
chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake --seed 1729
chainbreak analyze <run-id>
chainbreak report <run-id> --format terminal
```

This produces a real, sealed, schema-valid evidence bundle with known ground truth. It
reproduces exactly, on any machine. It proves the analysis is correct; it proves nothing about
AWS.

(Available from milestone M5 onward — see [PROJECT_STATUS.md](../PROJECT_STATUS.md).)
