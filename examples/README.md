# Examples

## Current contents

- `reports/sample-scope-attenuation-fake.html` — a self-contained HTML report (M16) rendered
  from `chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake --seed 1729`
  followed by `chainbreak analyze` and `chainbreak report --format html`. Its header and every
  figure caption are stamped `FAKE-PROVIDER APPARATUS CHECK` — this demonstrates the report
  structure, the finding layout and the figures, and says nothing about AWS. M19 adds a sample
  from a real run.
- `bundles/` — not yet populated; will hold a small exported evidence bundle demonstrating the
  format.

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
