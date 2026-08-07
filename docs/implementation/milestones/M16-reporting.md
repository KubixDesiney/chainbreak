# M16 — Reporting and visualization

## Purpose
Render evidence into terminal, Markdown and self-contained HTML output, with the language
rules enforced by lint rather than by good intentions.

## Dependencies
M15.

## Required components
`reporting/terminal.py` (rich), `reporting/markdown.py`, `reporting/html.py` (Jinja2,
autoescape on), `reporting/figures.py` (Plotly), `reporting/language.py` (the rule set),
`reporting/templates/`.

## Files expected
```
src/chainbreak/reporting/{terminal,markdown,html,figures,language}.py
src/chainbreak/reporting/templates/*.html.j2
tests/unit/{test_report_language,test_no_unsafe_template_filters}.py
tests/integration/test_report_generation.py
```

## Functional requirements
- F1 Terminal report matching [SCORING_MODEL §4](../../../SCORING_MODEL.md#4-report-shape).
- F2 Markdown and self-contained HTML (no external assets, no CDN).
- F3 Figures: authorization graph, per-hop intended vs effective, gain/loss per hop,
  revocation timeline with the transition window shaded, stale-authority window, repeatability
  across trials, scenario comparison. All generated **from evidence**, never from
  hand-written numbers.
- F4 Every finding renders `observation`, `expected_state`, `observed_state`,
  `security_interpretation` under separate headings, in that order.
- F5 Mandatory limitations section naming: single account, single region, simple policies,
  deterministic worker, small n.
- F6 A `provider: fake` run is stamped as non-measurement output in the header **and in every
  figure caption**. Enforced in the rendering layer, not left to the operator.
- F7 `git_dirty: true` and `bundle_root_verified: false` render prominently.

## Non-functional requirements
HTML report under 2 MB and under 3 s to generate. Readable without JavaScript for the text
content.

## Security requirements
- S1 T-10: Jinja2 autoescape on; **no `|safe` anywhere**, asserted by a test that greps the
  template directory. A third-party bundle is a plausible XSS vector into a generated report.
- S2 No network fetches at render time.
- S3 Reports contain only redacted values — they are rendered from the bundle, which is
  already redacted, and the renderer adds nothing.

## Tests
`test_report_language.py` implements
[EXPERIMENT_PROTOCOL §7](../../../EXPERIMENT_PROTOCOL.md#7-reporting-language-rules): required
elements present, forbidden words absent, no timing value without an interval, no percentage
without a denominator.

## Negative controls
Render a report from a bundle whose `security_interpretation` contains `<script>`; assert it
is escaped. Hand-edit a template to say "AWS is vulnerable"; assert the language test fails.
Render a fake-provider run; assert every figure caption carries the non-measurement stamp.

## Acceptance criteria
1. All three formats render from a fake-provider bundle.
2. Language lint passes and demonstrably fails on a planted violation.
3. No `|safe` in any template; XSS fixture escaped.
4. Fake-provider runs stamped in header and captions.
5. Limitations section present in every format.

## Verification commands
```bash
chainbreak report <run-id> --format terminal
chainbreak report <run-id> --format markdown -o /tmp/r.md
chainbreak report <run-id> --format html -o /tmp/r.html && du -h /tmp/r.html
grep -rn '|safe' src/chainbreak/reporting/templates/ && echo FAIL || echo "no unsafe filters"
pytest -m unit tests/unit/test_report_language.py -q
```

## Definition of done
Acceptance criteria met; a sample HTML report from a fake run committed under `examples/`
with a header stating it is fake-provider output; `PROJECT_STATUS.md` updated.

## Out of scope
Interactive dashboards. A web server. Real measurements (M17).

## Risks
A report that reads as a verdict. The language lint is the control; keep it strict, and add a
rule whenever a draft sentence overclaims.
