"""Scenario identity Terraform outputs remain executable data."""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.capabilities.loader import load_catalog
from chainbreak.scenarios.compiler import compile_scenario
from chainbreak.scenarios.loader import load_and_compile
from chainbreak.scenarios.safety import load_scenario_yaml
from chainbreak.scenarios.schema import ScenarioDocument

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_negative_control_role_bindings_survive_compilation(synthetic_aws_registry) -> None:
    path = REPO_ROOT / "scenarios" / "_negative-controls" / "nc-scope-expansion.yaml"
    compiled = load_and_compile(path, registry=synthetic_aws_registry)

    bindings = {node.identity_id: node.provider_binding for node in compiled.graph.nodes}

    assert bindings["principal"] == "principal_role_arn"
    assert bindings["agent-a"] == "agent_a_role_arn"
    assert bindings["agent-b"] == "agent_b_expansion_role_arn"


def test_compiler_carries_binding_on_regular_graph_nodes(synthetic_aws_registry) -> None:
    path = REPO_ROOT / "scenarios" / "scope-attenuation" / "basic.yaml"
    document = ScenarioDocument.model_validate(load_scenario_yaml(path))
    compiled = compile_scenario(
        document,
        catalog=load_catalog(),
        registry=synthetic_aws_registry,
    )

    assert all(node.provider_binding for node in compiled.graph.nodes)
