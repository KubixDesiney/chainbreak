# Contributing to CHAINBREAK

CHAINBREAK is a security research artifact. The bar for merging is "would this survive
review by a cloud security engineer who is skeptical of the result?" — which is a higher bar
than "the tests pass".

---

## Setup

```bash
git clone <repo> && cd chainbreak
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,aws,report,analysis]"
pre-commit install
pytest -m "unit or integration"
```

The verification path must not install Checkov into this environment: Terraform CI invokes the
SHA-pinned Checkov action. For a release check, use `python -m build --wheel` followed by
`python scripts/smoke_installed_wheel.py dist/chainbreak-*.whl`; that smoke test creates a
temporary environment and runs from outside the checkout.

No AWS account is needed to develop, test, or run scenarios — use `--provider fake`.

---

## The invariants you must not casually change

Before touching any of these, read the linked document and open an ADR:

| Invariant | Document |
|---|---|
| ARCH-1 layer dependency rule | [ARCHITECTURE §2](ARCHITECTURE.md#dependency-rule-invariant-arch-1) |
| CAP-1/CAP-2 capability and binding rules | [CAPABILITY_MODEL §4](CAPABILITY_MODEL.md#binding-rules-invariant-cap-2) |
| AUTH-1 observed authority contains only ALLOWED | [AUTHORIZATION_MODEL §1.2](AUTHORIZATION_MODEL.md#12-authority-entities) |
| G-1…G-5 graph invariants | [AUTHORIZATION_MODEL §2](AUTHORIZATION_MODEL.md#2-the-authorization-graph) |
| PROV-1 adapters may narrow, never broaden | [ARCHITECTURE §3.8](ARCHITECTURE.md#38-providersbase) |
| INFRA-1/2 Terraform vs. runtime planes | [ARCHITECTURE §7](ARCHITECTURE.md#7-where-infrastructure-comes-from) |
| SI-1…SI-12 security invariants | [SECURITY_MODEL §3](SECURITY_MODEL.md#3-the-ten-invariants) |
| EV-1 no secrets in evidence | [EVIDENCE_SCHEMA §5](EVIDENCE_SCHEMA.md#5-credentialsjsonl--metadata-only) |

"Casually" means: without an ADR, without updating the affected documents, and without a
test demonstrating the new behavior is still safe.

---

## Workflow

1. Open an issue describing the problem before writing code, unless it is a typo or an
   obvious bug fix.
2. Branch: `feat/…`, `fix/…`, `docs/…`, `adr/…`, `scenario/…`.
3. Small, reviewable commits. Conventional-commit prefixes preferred.
4. Update the documents your change affects **in the same PR**. A code change that
   contradicts a specification is a bug in one of them; leaving them inconsistent is worse
   than either.
5. Update `PROJECT_STATUS.md` if you completed or advanced a milestone.
6. Run `pytest -m "unit or integration"`, `ruff check .`, `mypy` before pushing.

---

## Adding things

**A capability** — follow [CAPABILITY_MODEL §7](CAPABILITY_MODEL.md#7-adding-a-capability).
All six steps, including the fake-provider binding. A capability that cannot be exercised in
CI is not accepted.

**A scenario** — must include a `deny` list on every `node_authority` expectation (you cannot
detect expansion without one), must contain no ARNs/account IDs/regions, must pass
`chainbreak scenario validate`, and must have a matching negative control if it introduces a
new detection pattern.

**A provider adapter** — must implement the full `ProviderAdapter` Protocol, pass the shared
contract test suite unmodified, provide bindings for every core capability or explicitly
declare them unsupported, and ship with an ADR. Do not weaken a contract test to make an
adapter pass; that is the one change that makes the whole apparatus untrustworthy.

**A finding type** — requires: a precise predicate in
[AUTHORIZATION_MODEL §6](AUTHORIZATION_MODEL.md#6-from-divergence-to-finding), a confidence
rule, at least one negative control that produces it, and report rendering that keeps
observation separate from interpretation.

**A dependency** — justify it. The core has six runtime dependencies and that is deliberate
(T-14). Anything cloud-specific belongs in an extra, not the core.

---

## Writing about results

The language rules in [EXPERIMENT_PROTOCOL §7](EXPERIMENT_PROTOCOL.md#7-reporting-language-rules)
apply to documentation and commit messages, not only to generated reports.

Never describe a measurement that has not been taken. Never write a README example with
plausible-looking numbers unless they came from a real run and the run ID is cited. If you
need an illustrative table, label it "illustration of the algorithm, not a measured result" —
this repository does that consistently and it is not optional.

---

## Code style

- Python 3.12, `ruff` (line length 100), `mypy --strict`. Both are merge gates.
- All timestamps timezone-aware UTC. Naive datetimes are a lint error (`DTZ`).
- All intervals from `time.monotonic_ns()`. Never subtract wall-clock times.
- No `print()` outside `reporting/` (`T20`).
- Type everything. `Any` needs a comment explaining why.
- Pydantic models for anything crossing a boundary; plain dataclasses for internal-only value
  objects where validation would be dead weight.
- Errors: raise a domain exception from `core/errors.py`, never a bare `Exception`, and never
  swallow an exception without recording an `Observation` or event explaining it.

---

## Review checklist

Reviewers check, in this order:

1. Does it violate an invariant? If yes, is there an ADR?
2. Could it cause a credential to be serialized anywhere?
3. Could it cause an action outside the benchmark namespace?
4. Does it make a claim the evidence does not support?
5. Are observation and interpretation still separate?
6. Do the affected documents still agree with the code?
7. Tests: unit for logic, integration for behavior, a negative control if it is a detector.
8. Does it add cost or runtime? Is that bounded?

---

## Code of conduct

Be straightforward, be specific, assume competence. Disagreement about technical direction
is expected and welcome; it belongs in an issue or an ADR. Harassment is not tolerated.
