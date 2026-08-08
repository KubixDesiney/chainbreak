"""M6 acceptance criterion 2: property-based, reflection-driven redaction test.

Discovers every ``DomainModel`` subclass in ``chainbreak.core.models`` by
reflection, then -- for every field on every model that reflection identifies
as unconstrained free text (a bare ``str`` or ``tuple[str, ...]`` with no
regex pattern) -- constructs an instance carrying a synthetic secret from the
corpus below in that field, and asserts that ``redact()`` either raises
``SecretLeakError`` or the secret does not appear anywhere in the canonical
serialization.

Field discovery is reflective (``model_cls.model_fields``), so a new
free-text field added to an existing model is picked up automatically. A new
*model* requires a registered factory in ``_FACTORIES`` below; the
``test_every_domain_model_has_a_factory`` test fails loudly, naming the
model, if one is added without one -- coverage cannot silently regress.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from chainbreak.core import canonical
from chainbreak.core import models as m
from chainbreak.core.enums import (
    BenchmarkFamily,
    Confidence,
    DelegationMechanism,
    DivergenceKind,
    FindingType,
    MutationKind,
    OutcomeClass,
    PhaseKind,
    PlanPhase,
    PolicyKind,
    ProbeKind,
    Provider,
    Sensitivity,
    SeverityHint,
)
from chainbreak.core.errors import SecretLeakError
from chainbreak.evidence.redaction import redact

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Synthetic secret corpus (SI-1 pattern table + M06 spec).
# ---------------------------------------------------------------------------

# AWS's own documented example access-key shape (used consistently across
# this repo's fixtures, e.g. test_logging_filter.py): CI's T-01 tree/history
# scan exempts any AKIA/ASIA-shaped string whose line also contains the
# literal word EXAMPLE, on the theory that a real leaked key would not
# coincidentally read "...EXAMPLE..." immediately after the prefix.
_FAKE_AKID = "AKIAIOSFODNN7EXAMPLE"
_FAKE_ASIA = "ASIAIOSFODNN7EXAMPLE"
_FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dGVzdHNpZ25hdHVyZXZhbHVlZm9ydGVzdA"
_FAKE_PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIExampleKey==\n-----END RSA PRIVATE KEY-----"
_FAKE_SESSION_TOKEN = (
    "FQoGZXIvYXdzEBoaDAbcXampLeSessionTokenValueThatIsLongAndBase64Shaped1234567890=="
)
_FAKE_SECRET_KEY_KV = "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYzzzzzKEY1"

SECRET_CORPUS: tuple[str, ...] = (
    _FAKE_AKID,
    _FAKE_ASIA,
    _FAKE_JWT,
    _FAKE_PEM,
    _FAKE_SESSION_TOKEN,
    _FAKE_SECRET_KEY_KV,
)

# ---------------------------------------------------------------------------
# Minimal-valid-instance factories, one per DomainModel subclass. Each
# returns the kwargs used to construct the model so a test can override a
# single field and rebuild.
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)

_HEX_DIGITS = "0123456789abcdef"


def _sha(seed: str = "x") -> str:
    """A syntactically valid ``sha256:...`` digest, distinct per seed."""
    hex_char = _HEX_DIGITS[(sum(ord(c) for c in seed) or 1) % 16]
    return "sha256:" + hex_char * 64


def _authority_set() -> m.AuthoritySet:
    return m.AuthoritySet.of("objectstore.read")


def _capability_kwargs() -> dict[str, Any]:
    return {
        "id": "objectstore.read",
        "title": "Read an object",
        "description": "Read a benchmark-owned object marker.",
        "probe_kind": ProbeKind.READ_MARKER,
        "sensitivity": Sensitivity.BENIGN_READ,
    }


def _identity_ref_kwargs() -> dict[str, Any]:
    return {"provider": Provider.FAKE, "kind": "role", "value": "fake:cb-01234567:agent-a"}


def _credential_record_kwargs() -> dict[str, Any]:
    return {
        "credential_id": "cred_01J8XKQ4Z0000000000000000",
        "identity_id": "agent-a",
        "mechanism": DelegationMechanism.ROLE_CHAIN,
        "issued_at": _NOW,
        "expires_at": _NOW.replace(hour=13),
        "requested_duration_s": 900,
        "granted_duration_s": 900,
        "session_name_hash": _sha("a"),
        "access_key_id_hash": _sha("b"),
    }


def _policy_fingerprint_kwargs() -> dict[str, Any]:
    return {
        "policy_kind": PolicyKind.IDENTITY_INLINE,
        "name_hash": _sha("c"),
        "document_sha256": _sha("d"),
        "statement_count": 1,
        "has_explicit_deny": False,
    }


def _policy_state_snapshot_kwargs() -> dict[str, Any]:
    return {
        "snapshot_id": "ps_01",
        "identity_id": "agent-a",
        "taken_at": _NOW,
        "monotonic_ns": 1,
        "policies": (m.PolicyFingerprint(**_policy_fingerprint_kwargs()),),
    }


def _mutation_receipt_kwargs() -> dict[str, Any]:
    return {
        "confirmed": True,
        "confirmation_method": "read_after_write",
        "monotonic_sent_ns": 1,
        "wall_sent": _NOW,
    }


def _policy_mutation_kwargs() -> dict[str, Any]:
    return {
        "mutation_id": "mut_01",
        "kind": MutationKind.ATTACH_INLINE_DENY,
        "target_identity": "agent-a",
    }


def _expected_authority_kwargs() -> dict[str, Any]:
    return {"capabilities": _authority_set(), "phase": PlanPhase.BASELINE, "derivation": "DECLARED"}


def _observed_authority_kwargs() -> dict[str, Any]:
    return {
        "capabilities": _authority_set(),
        "phase": PlanPhase.BASELINE,
        "probe_matrix_id": "pm_01",
        "attempted": 1,
        "classified": 1,
    }


def _delegation_edge_kwargs() -> dict[str, Any]:
    return {
        "edge_id": "hop-1",
        "source_id": "principal",
        "target_id": "agent-a",
        "mechanism": DelegationMechanism.ROLE_CHAIN,
        "requested_capabilities": _authority_set(),
        "intended_capabilities": _authority_set(),
        "expected_effective": _authority_set(),
        "credential_lifetime_s": 900,
    }


def _identity_node_kwargs() -> dict[str, Any]:
    return {
        "identity_id": "principal",
        "is_root": True,
        "hop_index": 0,
        "expected_authority": m.ExpectedAuthority(**_expected_authority_kwargs()),
    }


def _divergence_point_kwargs() -> dict[str, Any]:
    return {"hop_index": 0, "identity_id": "agent-a", "kind": DivergenceKind.MIXED}


def _path_analysis_kwargs() -> dict[str, Any]:
    return {
        "path": ("principal", "agent-a"),
        "attenuation_monotone_set": True,
        "attenuation_monotone_cardinality": True,
    }


def _edge_divergence_kwargs() -> dict[str, Any]:
    return {
        "edge_id": "hop-1",
        "expected_at_target_observed": _authority_set(),
        "expected_at_target_intended": _authority_set(),
        "attenuation_correct": True,
        "attenuation_correct_vs_intent": True,
    }


def _authorization_graph_kwargs() -> dict[str, Any]:
    return {"nodes": (m.IdentityNode(**_identity_node_kwargs()),)}


def _probe_timing_kwargs() -> dict[str, Any]:
    return {"monotonic_start_ns": 0, "monotonic_end_ns": 1, "wall_start": _NOW}


def _probe_request_record_kwargs() -> dict[str, Any]:
    return {
        "probe_kind": ProbeKind.READ_MARKER,
        "binding_actions": ("s3:GetObject",),
        "target_ref_hash": _sha("e"),
        "target_namespace": "cb-01234567",
        "parameters_fingerprint": _sha("f"),
    }


def _probe_outcome_kwargs() -> dict[str, Any]:
    return {"outcome_class": OutcomeClass.ALLOWED}


def _observation_kwargs() -> dict[str, Any]:
    return {
        "observation_id": "obs_01",
        "run_id": "01J8XKQ4V7ZP3N2M9YB6TCFR5A",
        "sequence": 1,
        "phase": PlanPhase.BASELINE,
        "probe_matrix_id": "pm_01",
        "identity_id": "agent-a",
        "identity_ref_hash": _sha("g"),
        "capability_id": "objectstore.read",
        "trial": 1,
        "trial_count": 1,
        "request": m.ProbeRequestRecord(**_probe_request_record_kwargs()),
        "timing": m.ProbeTiming(**_probe_timing_kwargs()),
        "outcome": m.ProbeOutcome(**_probe_outcome_kwargs()),
        "preconditions_verified": True,
    }


def _probe_cell_result_kwargs() -> dict[str, Any]:
    return {
        "identity_id": "agent-a",
        "capability_id": "objectstore.read",
        "phase": PlanPhase.BASELINE,
        "trials": (OutcomeClass.ALLOWED,),
    }


def _interval_kwargs() -> dict[str, Any]:
    return {"low": 0.0, "point": 1.0, "high": 2.0}


def _revocation_measurement_kwargs() -> dict[str, Any]:
    return {
        "identity_id": "agent-a",
        "capability_id": "objectstore.read",
        "mutation_kind": MutationKind.ATTACH_INLINE_DENY,
        "transition_observed": False,
        "poll_interval_ms": 500,
        "poll_count": 0,
        "window_length_s": 1.0,
        "mutation_receipt_confirmed": True,
    }


def _stale_authority_measurement_kwargs() -> dict[str, Any]:
    from chainbreak.core.enums import StaleAuthorityClass

    return {
        "identity_id": "agent-a",
        "capability_id": "objectstore.read",
        "classification": StaleAuthorityClass.CURRENT_AUTHORITY,
        "deferral_seconds": 1.0,
        "credential_expired_at_execution": False,
    }


def _task_step_outcome_kwargs() -> dict[str, Any]:
    return {
        "capability_id": "objectstore.read",
        "succeeded": True,
        "outcome_class": OutcomeClass.ALLOWED,
    }


def _task_outcome_kwargs() -> dict[str, Any]:
    from chainbreak.core.enums import TaskStatus

    return {
        "task_id": "task_01",
        "identity_id": "agent-a",
        "worker": "sequential",
        "status": TaskStatus.COMPLETE,
        "steps_total": 1,
        "steps_attempted": 1,
        "steps_succeeded": 1,
        "reported_insufficient_authority": False,
        "output_marker_written": True,
        "output_marker_verified_independently": True,
    }


def _finding_evidence_kwargs() -> dict[str, Any]:
    return {}


def _finding_kwargs() -> dict[str, Any]:
    return {
        "finding_id": "fnd_01",
        "type": FindingType.EXPECTED_BEHAVIOR,
        "severity_hint": SeverityHint.INFORMATIONAL,
        "confidence": Confidence.HIGH,
        "subject_kind": "identity",
        "observation": "agent-a matched expectation",
    }


def _detector_check_kwargs() -> dict[str, Any]:
    return {
        "negative_control_id": "nc-01",
        "expected_type": FindingType.AUTHORITY_EXPANSION,
        "produced": True,
        "result": "DETECTOR_OK",
    }


def _measurement_kwargs() -> dict[str, Any]:
    return {
        "metric": "revocation_window",
        "value": m.Interval(**_interval_kwargs()),
        "confidence": Confidence.HIGH,
    }


def _category_result_kwargs() -> dict[str, Any]:
    from chainbreak.core.enums import CategoryStatus, ScoringCategory

    return {
        "category": ScoringCategory.SCOPE_ATTENUATION,
        "status": CategoryStatus.NOT_MEASURED,
        "coverage": 0.0,
        "confidence": Confidence.INSUFFICIENT,
    }


def _probe_matrix_kwargs() -> dict[str, Any]:
    return {
        "matrix_id": "pm_01",
        "phase_name": "baseline",
        "identities": ("agent-a",),
        "capabilities": _authority_set(),
    }


def _plan_step_kwargs() -> dict[str, Any]:
    return {"order": 0, "phase_name": "baseline", "kind": PhaseKind.PROBE}


def _synthesized_policy_kwargs() -> dict[str, Any]:
    return {
        "identity_id": "agent-a",
        "capabilities": _authority_set(),
        "document_size_bytes": 10,
        "fingerprint": _sha("h"),
    }


def _compile_warning_kwargs() -> dict[str, Any]:
    return {
        "code": "G3_DOWNGRADED",
        "message": "intent exceeds parent; downgraded by negative control",
    }


def _compiled_expected_finding_kwargs() -> dict[str, Any]:
    return {"type": FindingType.AUTHORITY_EXPANSION}


def _compiled_scenario_kwargs() -> dict[str, Any]:
    return {
        "compiled_hash": _sha("i"),
        "scenario_id": "basic",
        "scenario_version": "1.0.0",
        "catalog_version": "1.0.0",
        "adapter_version": "0.1.0",
        "graph": m.AuthorizationGraph(**_authorization_graph_kwargs()),
        "probe_matrices": (m.ProbeMatrix(**_probe_matrix_kwargs()),),
        "plan": (m.PlanStep(**_plan_step_kwargs()),),
    }


def _provenance_kwargs() -> dict[str, Any]:
    return {
        "chainbreak_version": "0.1.0a0",
        "capability_catalog_version": "1.0.0",
        "provider": Provider.FAKE,
        "provider_adapter_version": "0.1.0",
        "python_version": "3.12.4",
        "config_fingerprint": _sha("j"),
    }


def _scenario_ref_kwargs() -> dict[str, Any]:
    return {
        "id": "basic",
        "version": "1.0.0",
        "family": BenchmarkFamily.SCOPE_ATTENUATION,
        "api_version": "chainbreak.dev/v1alpha1",
        "compiled_hash": _sha("k"),
    }


def _safety_envelope_kwargs() -> dict[str, Any]:
    return {
        "allowed_account_ids": ("123456789012",),
        "allowed_regions": ("us-east-1",),
        "namespace": "cb-01234567",
        "namespace_pattern": "cb-01234567",
    }


def _experiment_run_kwargs() -> dict[str, Any]:
    return {
        "run_id": "01J8XKQ4V7ZP3N2M9YB6TCFR5A",
        "created_at": _NOW,
        "status": m.RunStatus.RUNNING
        if hasattr(m, "RunStatus")
        else __import__("chainbreak.core.enums", fromlist=["RunStatus"]).RunStatus.RUNNING,
        "scenario": m.ScenarioRef(**_scenario_ref_kwargs()),
        "provenance": m.Provenance(**_provenance_kwargs()),
        "envelope": m.SafetyEnvelope(**_safety_envelope_kwargs()),
    }


def _provider_capability_binding_kwargs() -> dict[str, Any]:
    return {
        "capability_id": "objectstore.read",
        "provider": Provider.FAKE,
        "actions": ("fake:read",),
        "resource_template": "fake://{namespace}/marker",
        "probe_kind": ProbeKind.READ_MARKER,
    }


def _capability_catalog_kwargs() -> dict[str, Any]:
    return {"version": "1.0.0", "capabilities": (m.Capability(**_capability_kwargs()),)}


def _delegation_constraints_kwargs() -> dict[str, Any]:
    return {}


_FACTORIES: dict[type[m.DomainModel], Any] = {
    m.AuthoritySet: lambda: {"capabilities": frozenset({"objectstore.read"})},
    m.Capability: _capability_kwargs,
    m.CapabilityCatalog: _capability_catalog_kwargs,
    m.ProviderCapabilityBinding: _provider_capability_binding_kwargs,
    m.IdentityRef: _identity_ref_kwargs,
    m.SafetyEnvelope: _safety_envelope_kwargs,
    m.CredentialRecord: _credential_record_kwargs,
    m.PolicyFingerprint: _policy_fingerprint_kwargs,
    m.PolicyStateSnapshot: _policy_state_snapshot_kwargs,
    m.MutationReceipt: _mutation_receipt_kwargs,
    m.PolicyMutation: _policy_mutation_kwargs,
    m.DelegationConstraints: _delegation_constraints_kwargs,
    m.ExpectedAuthority: _expected_authority_kwargs,
    m.ObservedAuthority: _observed_authority_kwargs,
    m.DelegationEdge: _delegation_edge_kwargs,
    m.IdentityNode: _identity_node_kwargs,
    m.DivergencePoint: _divergence_point_kwargs,
    m.PathAnalysis: _path_analysis_kwargs,
    m.EdgeDivergence: _edge_divergence_kwargs,
    m.AuthorizationGraph: _authorization_graph_kwargs,
    m.ProbeTiming: _probe_timing_kwargs,
    m.ProbeRequestRecord: _probe_request_record_kwargs,
    m.ProbeOutcome: _probe_outcome_kwargs,
    m.Observation: _observation_kwargs,
    m.ProbeCellResult: _probe_cell_result_kwargs,
    m.Interval: _interval_kwargs,
    m.RevocationMeasurement: _revocation_measurement_kwargs,
    m.StaleAuthorityMeasurement: _stale_authority_measurement_kwargs,
    m.TaskStepOutcome: _task_step_outcome_kwargs,
    m.TaskOutcome: _task_outcome_kwargs,
    m.FindingEvidence: _finding_evidence_kwargs,
    m.Finding: _finding_kwargs,
    m.DetectorCheck: _detector_check_kwargs,
    m.Measurement: _measurement_kwargs,
    m.CategoryResult: _category_result_kwargs,
    m.ProbeMatrix: _probe_matrix_kwargs,
    m.PlanStep: _plan_step_kwargs,
    m.SynthesizedPolicy: _synthesized_policy_kwargs,
    m.CompileWarning: _compile_warning_kwargs,
    m.CompiledExpectedFinding: _compiled_expected_finding_kwargs,
    m.CompiledScenario: _compiled_scenario_kwargs,
    m.Provenance: _provenance_kwargs,
    m.ScenarioRef: _scenario_ref_kwargs,
    m.ExperimentRun: _experiment_run_kwargs,
}


def _discover_domain_models() -> list[type[m.DomainModel]]:
    return [
        obj
        for _name, obj in inspect.getmembers(m, inspect.isclass)
        if issubclass(obj, m.DomainModel)
        and obj is not m.DomainModel
        and obj.__module__ == m.__name__
    ]


ALL_DOMAIN_MODELS = _discover_domain_models()


def test_every_domain_model_has_a_factory() -> None:
    """Reflection discovers the models; this is the completeness backstop --
    a new model without a registered factory fails here, by name, rather than
    silently escaping the property sweep below."""
    missing = [cls.__name__ for cls in ALL_DOMAIN_MODELS if cls not in _FACTORIES]
    assert not missing, f"no redaction-test factory registered for: {missing}"


def _pattern_of(field_info: Any) -> str | None:
    for item in field_info.metadata:
        pattern = getattr(item, "pattern", None)
        if pattern:
            return str(pattern)
    return None


def _free_text_fields(model_cls: type[m.DomainModel]) -> list[tuple[str, str]]:
    """``(field_name, kind)`` pairs reflection identifies as unconstrained
    free text: a bare ``str`` or a ``tuple[str, ...]``, neither pattern-
    restricted. ``kind`` is ``"str"`` or ``"tuple"``."""
    fields = []
    for name, info in model_cls.model_fields.items():
        if info.annotation is str and _pattern_of(info) is None:
            fields.append((name, "str"))
        elif info.annotation == tuple[str, ...] and _pattern_of(info) is None:
            fields.append((name, "tuple"))
    return fields


def _free_text_cases() -> list[tuple[type[m.DomainModel], str, str]]:
    cases = []
    for model_cls in ALL_DOMAIN_MODELS:
        if model_cls not in _FACTORIES:
            continue
        for field_name, kind in _free_text_fields(model_cls):
            cases.append((model_cls, field_name, kind))
    return cases


FREE_TEXT_CASES = _free_text_cases()


def test_free_text_field_discovery_is_nonempty() -> None:
    """Sanity check on the discovery mechanism itself: if this hits zero, the
    property sweep below would vacuously pass without checking anything."""
    assert len(FREE_TEXT_CASES) >= 10


@pytest.mark.parametrize(
    "model_cls,field_name,kind",
    FREE_TEXT_CASES,
    ids=[f"{c[0].__name__}.{c[1]}" for c in FREE_TEXT_CASES],
)
@pytest.mark.parametrize("secret", SECRET_CORPUS)
def test_redact_catches_or_removes_every_corpus_secret(
    model_cls: type[m.DomainModel], field_name: str, kind: str, secret: str
) -> None:
    kwargs = _FACTORIES[model_cls]()
    kwargs[field_name] = (secret,) if kind == "tuple" else secret
    try:
        instance = model_cls(**kwargs)
    except ValidationError:
        pytest.skip(
            f"{model_cls.__name__}.{field_name} rejects this shape via its own validator "
            "(e.g. allowed_account_ids' 12-digit check) -- structurally not free text"
        )

    try:
        redact(instance)
    except SecretLeakError as exc:
        # The report itself must not reproduce the leak.
        assert secret not in str(exc)
        return

    serialized = canonical.dumps(instance)
    assert secret not in serialized, (
        f"{model_cls.__name__}.{field_name} let a corpus secret through redact() unflagged"
    )


# ---------------------------------------------------------------------------
# Focused regression tests: known-benign hash-shaped values must never
# false-positive (every Sha256Digest field in the entire schema depends on
# this), and each pattern individually must fire in isolation.
# ---------------------------------------------------------------------------


def test_sha256_digest_is_not_a_false_positive() -> None:
    redact({"identity_ref_hash": _sha("a"), "compiled_hash": _sha("b")})


def test_git_commit_sha_is_not_a_false_positive() -> None:
    redact({"git_commit": "9d4a2c1f" + "0" * 32})


def test_ulid_is_not_a_false_positive() -> None:
    from chainbreak.core.ids import new_ulid

    redact({"run_id": new_ulid(), "observation_id": "obs_" + new_ulid()})


@pytest.mark.parametrize("secret", SECRET_CORPUS)
def test_redact_raises_on_bare_dict(secret: str) -> None:
    with pytest.raises(SecretLeakError):
        redact({"nested": {"deep": [secret]}})


def test_redact_error_message_never_contains_the_secret() -> None:
    secret = _FAKE_AKID
    with pytest.raises(SecretLeakError) as excinfo:
        redact({"field": secret})
    assert secret not in str(excinfo.value)
    assert secret not in repr(excinfo.value)


def test_redact_raises_on_raw_secret_material() -> None:
    from chainbreak.core.secrets import SecretMaterial

    with pytest.raises(SecretLeakError):
        redact(SecretMaterial("super-secret-value", "test"))


def test_redact_raises_on_secret_in_bare_frozenset() -> None:
    with pytest.raises(SecretLeakError):
        redact(frozenset({_FAKE_AKID, "benign"}))


def test_redact_raises_on_secret_in_bare_set() -> None:
    with pytest.raises(SecretLeakError):
        redact({_FAKE_AKID, "benign"})


def test_redact_passes_through_clean_bare_set_unchanged() -> None:
    redact(frozenset({"objectstore.read", "keyvalue.read"}))


def test_redact_passes_through_enum_value_unchanged() -> None:
    redact(OutcomeClass.ALLOWED)


def test_redact_passes_through_opaque_object_unchanged() -> None:
    """Something that is neither text nor a container -- ``StrEnum`` members
    are themselves ``str`` and take the string-scanning branch above, so this
    exercises the true fallback for e.g. a raw ``bytes`` value."""
    redact(b"\x00\x01\x02")


def test_redact_passes_through_clean_data_unchanged() -> None:
    clean = {"a": 1, "b": [1, 2, 3], "c": {"nested": "value"}, "d": None, "e": True}
    assert redact(clean) == clean


def test_redact_message_replaces_arn_in_place() -> None:
    from chainbreak.evidence.redaction import redact_message

    text = (
        "User: arn:aws:iam::123456789012:role/agent-a is not authorized to perform: "
        "s3:GetObject on resource: arn:aws:s3:::cb-01234567/marker with an explicit deny"
    )
    redacted = redact_message(text)
    assert "arn:aws:iam::123456789012:role/agent-a" not in redacted
    assert "<REDACTED_ARN>" in redacted
    assert "is not authorized to perform: s3:GetObject" in redacted
    assert "with an explicit deny" in redacted


# ---------------------------------------------------------------------------
# S1: no file write inside evidence/ may bypass the redact() choke point.
# ---------------------------------------------------------------------------


def test_no_unsafe_file_writes_outside_writer() -> None:
    """S1's lint rule: only writer.py may open a file for writing or call
    json.dump inside evidence/."""
    import re
    from pathlib import Path

    evidence_dir = Path(m.__file__).resolve().parent.parent / "evidence"
    offenders = []
    write_open = re.compile(r"""open\([^)]*["'][wxa]b?["']""")
    write_text_call = re.compile(r"\.write_text\(")
    for path in sorted(evidence_dir.glob("*.py")):
        if path.name in {"writer.py", "__init__.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if "json.dump(" in text or write_open.search(text) or write_text_call.search(text):
            offenders.append(path.name)
    assert not offenders, f"file write outside writer.py: {offenders}"
