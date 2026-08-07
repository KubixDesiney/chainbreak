"""Runtime enforcement of SI-3: a provider adapter may not silently broaden a
scenario's declared capabilities.

The interface is shaped for the AWS adapter's botocore ``before-call`` hook
(M8): ``record()`` is what that hook calls once per outbound API operation;
the ``with`` block's boundary is one probe attempt. The check fires on
``__exit__`` regardless of whether the block itself raised, and regardless of
whether the probe's own outcome "looked like it worked" -- a broadened
operation is a violation independent of what it returned.
"""

from __future__ import annotations

from types import TracebackType

from chainbreak.core.errors import CapabilityBroadeningError
from chainbreak.core.models import ProviderCapabilityBinding


class OperationAllowlist:
    """Records operations invoked during a probe; raises on exit if any
    operation fell outside the binding's declared ``actions``."""

    def __init__(self, binding: ProviderCapabilityBinding) -> None:
        self._binding = binding
        self._invoked: list[str] = []

    def record(self, operation: str) -> None:
        self._invoked.append(operation)

    @property
    def invoked_operations(self) -> tuple[str, ...]:
        return tuple(self._invoked)

    def __enter__(self) -> OperationAllowlist:
        self._invoked = []
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        allowed = set(self._binding.actions)
        broadened = sorted({op for op in self._invoked if op not in allowed})
        if broadened:
            raise CapabilityBroadeningError(
                f"{self._binding.capability_id}: operations outside binding: {broadened}",
                capability_id=self._binding.capability_id,
                binding_actions=sorted(allowed),
                broadened=broadened,
            )
