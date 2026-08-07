"""Provider-neutral session-policy synthesis (SCENARIO_SPECIFICATION.md section 10, F7).

The real, provider-specific policy document (statements, actions, resource
ARNs) does not exist until a provider adapter does -- AWS_PROVIDER_SPEC.md
section 4 describes what the AWS binding eventually generates from binding
metadata, and that generation is explicitly out of scope here (M8). What
*is* in scope at compile time is the one thing that can go wrong before any
provider is involved: the policy a capability set would require might not
fit. AWS's own inline session-policy ceiling is 2048 characters
(AWS_PROVIDER_SPEC.md section 4); other providers will have their own, hence
the limit is a parameter, not a constant baked into the check.

The "document" synthesized here is a canonical-JSON placeholder (the sorted
capability list), not a real policy -- it exists to be sized and
fingerprinted, standing in for whatever the eventual provider binding
generates from the same capability set.
"""

from __future__ import annotations

from chainbreak.core.canonical import dumps
from chainbreak.core.errors import ScenarioSemanticError
from chainbreak.core.ids import IdentityId, fingerprint_json
from chainbreak.core.models import AuthoritySet, SynthesizedPolicy

AWS_INLINE_SESSION_POLICY_LIMIT_BYTES = 2048


def synthesize_policy(
    identity_id: IdentityId,
    capabilities: AuthoritySet,
    *,
    edge_id: str | None = None,
    size_limit_bytes: int = AWS_INLINE_SESSION_POLICY_LIMIT_BYTES,
) -> SynthesizedPolicy:
    """Build the size-checked, fingerprinted placeholder policy artifact for one edge.

    Raises :class:`ScenarioSemanticError` naming the limit -- a compile-time
    failure, not something discovered as a runtime `PackedPolicyTooLarge`.
    """
    document = dumps(capabilities.model_dump_canonical())
    size = len(document.encode("utf-8"))

    if size > size_limit_bytes:
        raise ScenarioSemanticError(
            f"{identity_id}: synthesized session policy is {size} bytes, "
            f"exceeding the {size_limit_bytes}-byte limit",
            identity_id=identity_id,
            edge_id=edge_id,
            size_bytes=size,
            size_limit_bytes=size_limit_bytes,
        )

    return SynthesizedPolicy(
        identity_id=identity_id,
        edge_id=edge_id,
        capabilities=capabilities,
        document_size_bytes=size,
        fingerprint=fingerprint_json(document),
    )
