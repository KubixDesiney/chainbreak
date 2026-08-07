"""The five-stage scenario validation pipeline (SCENARIO_SPECIFICATION.md section 9).

    1. Syntactic   -- YAML parse, JSON Schema validation against v1alpha1.
    2. Structural  -- Pydantic model construction; type and enum checks.
    3. Semantic    -- graph invariants G-1..G-5, capability closure, references resolve.
    4. Provider binding -- every named capability has a binding in the declared provider.
    5. Safety      -- no literal ARNs/account IDs/regions; no DANGEROUS capability
                       without opt-in. Runs even in ``--offline`` mode and cannot be
                       skipped (SI-11).

Exit codes: 0 valid, 2 schema/structural, 3 semantic, 4 binding, 5 safety.

Stage 1's bounds/literal-infrastructure half and all of stage 5's ARN/account/region
check are already enforced unconditionally by ``scenarios/safety.py``, before this
module ever sees a document -- that is what makes an untrusted scenario file a
*parsing* problem rather than a security problem, and it is why this loader cannot
accidentally skip it. JSON Schema validation is generated in-memory from
``ScenarioDocument.model_json_schema()`` rather than read from a file, so this module
does not depend on ``schemas/`` being present at runtime (it may not be, outside a
repository checkout).
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import jsonschema
import pydantic

from chainbreak.capabilities.loader import assert_no_dangerous, load_catalog
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.errors import (
    BindingValidationError,
    CapabilityResolutionError,
    ChainbreakError,
    DangerousCapabilityError,
    ScenarioSafetyError,
    ScenarioSemanticError,
    ScenarioSyntaxError,
)
from chainbreak.core.models import CapabilityCatalog, CompiledScenario
from chainbreak.scenarios.compiler import compile_scenario
from chainbreak.scenarios.safety import load_scenario_yaml
from chainbreak.scenarios.schema import ScenarioDocument

EXIT_VALID = 0
EXIT_SYNTAX_STRUCTURAL = 2
EXIT_SEMANTIC = 3
EXIT_BINDING = 4
EXIT_SAFETY = 5

_SCHEMA = ScenarioDocument.model_json_schema()


class ScenarioValidationResult(NamedTuple):
    """Every failure within the stage that fired is in ``errors``; a later
    stage never runs once an earlier one has failed (F1's "within a stage" is
    upheld by Pydantic's own multi-error ``ValidationError`` at stage 2, the
    stage this pipeline is most likely to see more than one failure in)."""

    exit_code: int
    errors: tuple[str, ...]
    compiled: CompiledScenario | None


def validate_scenario(
    path: Path,
    *,
    catalog: CapabilityCatalog | None = None,
    registry: BindingRegistry | None = None,
    adapter_version: str = "0.1.0",
    max_delegation_depth: int = 6,
    allow_dangerous: bool = False,
) -> ScenarioValidationResult:
    """Run all five stages, stopping at the first that fails."""
    catalog = catalog or load_catalog()
    registry = registry or BindingRegistry()

    # Stage 1 (partial) + stage 5 (partial): safe YAML load, document bounds,
    # and the literal-ARN/account/region check. Unconditional; see module docstring.
    try:
        raw = load_scenario_yaml(path)
    except ScenarioSafetyError as exc:
        return ScenarioValidationResult(EXIT_SAFETY, (str(exc),), None)
    except ScenarioSyntaxError as exc:
        return ScenarioValidationResult(EXIT_SYNTAX_STRUCTURAL, (str(exc),), None)

    # Stage 1: JSON Schema validation against v1alpha1.
    schema_errors = tuple(
        f"{'.'.join(str(part) for part in error.path) or '<document>'}: {error.message}"
        for error in jsonschema.Draft202012Validator(_SCHEMA).iter_errors(raw)
    )
    if schema_errors:
        return ScenarioValidationResult(EXIT_SYNTAX_STRUCTURAL, schema_errors, None)

    # Stage 2: structural (Pydantic construction).
    try:
        document = ScenarioDocument(**raw)
    except pydantic.ValidationError as exc:
        errors = tuple(
            f"{'.'.join(str(part) for part in error['loc']) or '<document>'}: {error['msg']}"
            for error in exc.errors()
        )
        return ScenarioValidationResult(EXIT_SYNTAX_STRUCTURAL, errors, None)

    # Stage 5 (remainder): no DANGEROUS capability without the double opt-in (SI-9).
    try:
        assert_no_dangerous(catalog, config_allows=allow_dangerous, cli_allows=allow_dangerous)
    except DangerousCapabilityError as exc:
        return ScenarioValidationResult(EXIT_SAFETY, (str(exc),), None)

    # Stages 3 and 4: graph construction (semantic) and binding resolution
    # (provider), both surfaced by the compiler.
    try:
        compiled = compile_scenario(
            document,
            catalog=catalog,
            registry=registry,
            adapter_version=adapter_version,
            max_delegation_depth=max_delegation_depth,
        )
    except ScenarioSemanticError as exc:
        return ScenarioValidationResult(EXIT_SEMANTIC, (str(exc),), None)
    except (CapabilityResolutionError, BindingValidationError) as exc:
        return ScenarioValidationResult(EXIT_BINDING, (str(exc),), None)

    return ScenarioValidationResult(EXIT_VALID, (), compiled)


def load_and_compile(
    path: Path | str,
    *,
    catalog: CapabilityCatalog | None = None,
    registry: BindingRegistry | None = None,
    adapter_version: str = "0.1.0",
    max_delegation_depth: int = 6,
    allow_dangerous: bool = False,
) -> CompiledScenario:
    """Convenience wrapper for callers that want an exception, not a result object.

    Note: with no ``registry`` supplied, provider-binding resolution (stage 4)
    runs against an empty registry -- correct today, since no provider package
    (M5 fake, M8 AWS) has registered anything into it yet. A caller compiling a
    real ``provider: aws`` scenario must supply a populated ``BindingRegistry``.
    """
    result = validate_scenario(
        Path(path),
        catalog=catalog,
        registry=registry,
        adapter_version=adapter_version,
        max_delegation_depth=max_delegation_depth,
        allow_dangerous=allow_dangerous,
    )
    if result.compiled is None:
        raise ChainbreakError(
            f"{path}: validation failed (exit {result.exit_code}): {'; '.join(result.errors)}",
            path=str(path),
            exit_code=result.exit_code,
            errors=list(result.errors),
        )
    return result.compiled
