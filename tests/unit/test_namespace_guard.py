"""providers/base/namespace.py -- SI-2's actual enforcement point."""

from __future__ import annotations

import pytest

from chainbreak.core.errors import NamespaceViolationError
from chainbreak.providers.base.namespace import assert_namespace

pytestmark = pytest.mark.unit


class TestInNamespace:
    def test_exact_match_passes(self):
        assert_namespace("cb-abcd1234", "cb-abcd1234")

    def test_namespace_embedded_in_a_larger_reference_passes(self):
        assert_namespace("arn:aws:iam::123456789012:role/cb-abcd1234-agent-a", "cb-abcd1234")

    def test_namespace_embedded_in_a_url_style_ref_passes(self):
        assert_namespace("fake://cb-abcd1234/objectstore.read", "cb-abcd1234")


class TestOutOfNamespace:
    def test_missing_namespace_raises(self):
        with pytest.raises(NamespaceViolationError):
            assert_namespace("arn:aws:iam::123456789012:role/other-role", "cb-abcd1234")

    def test_lookalike_namespace_does_not_pass(self):
        # A different (but similarly-shaped) namespace string must not be
        # treated as a match -- this is the actual point of the check.
        with pytest.raises(NamespaceViolationError):
            assert_namespace("fake://cb-11111111/objectstore.read", "cb-abcd1234")

    def test_empty_reference_raises(self):
        with pytest.raises(NamespaceViolationError):
            assert_namespace("", "cb-abcd1234")

    def test_error_carries_ref_and_namespace_context(self):
        with pytest.raises(NamespaceViolationError) as excinfo:
            assert_namespace("wrong-ref", "cb-abcd1234")
        assert excinfo.value.context["namespace"] == "cb-abcd1234"
        assert excinfo.value.context["ref"] == "wrong-ref"
