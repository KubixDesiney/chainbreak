# Examples

## Current contents

- `reports/sample-scope-attenuation-fake.html` — a self-contained HTML report (M16) rendered
  from `chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake --seed 1729`
  followed by `chainbreak analyze` and `chainbreak report --format html`. Its header and every
  figure caption are stamped `FAKE-PROVIDER APPARATUS CHECK` — this demonstrates the report
  structure, the finding layout and the figures, and says nothing about AWS.
- `reports/apparatus-check-fake-scope-attenuation.html` and its `.tar.gz` archive — a second
  scrubbed apparatus check used for the offline M18 compare/archive exercise. It is labelled
  fake-provider apparatus and excluded from AWS evidence.
- `reports/aws-m17-block04-excluded-scrubbed-report.md` and its sample archive — scrubbed
  outputs from an excluded AWS apparatus block. They are labelled excluded and are not AWS
  evidence.
- `reports/aws-m17-block07-scrubbed-report.md` and its sample archive are a scrubbed AWS
  apparatus sample from excluded block 07; they are not publishable M17 evidence.
- `reports/aws-m17-valid-block01-scrubbed-report.md` and
  `reports/aws-m17-valid-block01-scrubbed-sample.tar.gz` are scrubbed outputs from valid M17
  AWS run `01M0A5WS8Q912NJSP0FEH1DWSK`. They are evidence for this account, region, and time;
  they do not support general AWS claims. Fake-provider outputs remain apparatus checks, and
  the historical AWS outputs above remain excluded.

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
