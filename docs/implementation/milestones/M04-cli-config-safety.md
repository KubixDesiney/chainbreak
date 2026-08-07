# M4 — CLI, configuration and the SafetyGate

## Purpose
Build the entry point and, more importantly, the gate every run must pass. This milestone is
where SI-5, SI-6, SI-7 and SI-8 become real.

## Dependencies
M1 (M3 not required: the CLI can be built against the compiler interface).

## Required components
`config/settings.py` (layered resolution and the `SafetyEnvelope`), `config/fingerprint.py`,
`core/safety.py` (`SafetyGate`), `core/clock.py` (monotonic run clock, deadline enforcement,
offset estimation interface), `cli/main.py` plus one module per command group,
`cli/logging.py` (structured logging with the redaction filter installed at startup).

## Files expected
```
src/chainbreak/config/{settings,fingerprint}.py
src/chainbreak/core/{safety,clock}.py
src/chainbreak/cli/{main,validate,scenario,run,analyze,report,runs,infra,logging}.py
chainbreak.example.toml
tests/unit/{test_config_layering,test_safety_gate,test_clock,test_logging_filter,test_cli_surface}.py
```

## Functional requirements
- F1 Config layering: defaults → repo `chainbreak.toml` → user config → `CHAINBREAK_*` env →
  CLI flags. Later wins. `config_fingerprint` is a hash of the resolved config with secret
  values excluded.
- F2 `SafetyEnvelope` is mandatory. A run without a resolved envelope raises
  `SafetyEnvelopeError`.
- F3 `chainbreak validate` checks: config resolves, account allowlist non-empty and explicit,
  regions valid, namespace pattern well-formed, catalog loads, scenarios in the repo compile,
  clock offset within tolerance. Human-readable table plus `--json`.
- F4 Command surface: `validate`, `scenario validate|list`, `infra plan|apply|destroy|status|verify-clean`,
  `run`, `analyze`, `report`, `runs list|show|reindex`, `evidence export`, `compare`.
  Commands not yet implemented exit 2 with "not implemented until M<n>" — never a stack trace.
- F5 Run clock: monotonic deadline armed at start, checked at every phase boundary and poll
  iteration; expiry seals the bundle with `ABORTED_TIMEOUT`.
- F6 Cost estimator: static per-probe cost table × compiled plan call count; abort above
  `max_estimated_cost_usd`.

## Non-functional requirements
`chainbreak --help` under 500 ms (defer heavy imports). CLI is a thin adapter: no business
logic.

## Security requirements
- S1 SI-5: no `--skip-preflight`, `--no-safety`, `--force` or equivalent. `test_cli_surface.py`
  introspects every Typer command and fails if such an option exists.
- S2 SI-10: the redaction log filter is installed before any other import that may log, and
  covers third-party loggers (botocore logs request headers at DEBUG).
- S3 SI-7 ceiling of 14400 s is not configurable upward.
- S4 SI-8 cost estimate must be **conservative** — a test asserts the estimate is ≥ the true
  call count times the table.

## Tests
`test_safety_gate.py` covers: missing envelope, wildcard account, disallowed region,
namespace mismatch, cost over ceiling, duration over ceiling. `test_cli_surface.py` asserts
no bypass flag exists — this is the test that keeps a future contributor from adding one for
convenience.

## Negative controls
Add a `--skip-safety` option to a command in a scratch branch; confirm `test_cli_surface.py`
fails. Set `allowed_account_ids = ["*"]`; confirm `validate` refuses with a message
explaining why wildcards are forbidden.

## Acceptance criteria
1. `chainbreak validate` passes on a correct config and fails informatively on each of the
   six safety failures.
2. No bypass flag exists, asserted by test.
3. A botocore DEBUG log containing a session-token-shaped string is scrubbed.
4. Coverage 100% on `core/safety.py`.
5. Unimplemented commands exit 2 with a clear message.

## Verification commands
```bash
chainbreak --help && chainbreak validate --json
CHAINBREAK_ALLOWED_ACCOUNT_IDS='*' chainbreak validate ; echo "exit=$?"   # expect non-zero
pytest -m unit tests/unit/test_safety_gate.py tests/unit/test_cli_surface.py \
  tests/unit/test_logging_filter.py -q
pytest --cov=chainbreak.core.safety --cov-fail-under=100 -m unit -q
```

## Definition of done
Acceptance criteria met; `chainbreak.example.toml` documents every setting with its default
and its safety implication; `PROJECT_STATUS.md` updated.

## Out of scope
Executing scenarios. Provider sessions. Terraform invocation (M9). Report rendering.

## Risks
Config layering that silently drops a safety setting when a later layer is partial — use
explicit merge semantics with a test per layer combination.
