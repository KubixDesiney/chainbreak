"""SI-2's actual enforcement point: every probe, mutation and delegation target
must be checked against the run's namespace before any provider call is made.

Deliberately simple and provider-agnostic: a provider reference (ARN, table
name, whatever an adapter's ``IdentityRef.value`` or resource identifier
looks like) is in-namespace iff the namespace string appears in it as a
literal substring. AWS_PROVIDER_SPEC section 2 (P6) additionally requires the
*shape* of a real ARN to match a stricter regex; that stricter check belongs
to ``providers/aws/`` (M8), which knows what an ARN looks like -- this
module's job is the one check every provider shares.
"""

from __future__ import annotations

from chainbreak.core.errors import NamespaceViolationError
from chainbreak.core.ids import Namespace


def assert_namespace(ref: str, namespace: Namespace) -> None:
    """Raise :class:`NamespaceViolationError` if ``ref`` does not belong to
    ``namespace``. Call before every probe, mutation and delegation -- never
    after, and never only in a test."""
    if namespace not in ref:
        raise NamespaceViolationError(
            f"reference does not belong to namespace {namespace!r}: {ref!r}",
            namespace=namespace,
            ref=ref,
        )
