"""Session policy JSON synthesis (AWS_PROVIDER_SPEC section 4).

Generated from binding metadata only -- never hand-written per scenario.
One statement per intended capability (each binding names its own actions
and resource; merging distinct resources into one statement's ``Action``
list would grant more than any single capability's binding declares, which
is exactly the broadening SI-3 exists to prevent), plus a fixed, always-
present ``sts:GetCallerIdentity`` statement for the control capability so a
scoped session can still be diagnosed if every intended capability turns out
to be denied.

The 2048-character ``Policy=`` parameter limit is asserted here with a clear
:class:`ConfigurationError` rather than discovered as STS's own
``PackedPolicyTooLarge`` at call time -- M3's compiler already asserts this
at compile time against a fingerprint-only stand-in
(``scenarios/policy_synthesis.py``); this is the same limit enforced again
against the real document this module builds.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from chainbreak.core.errors import ConfigurationError
from chainbreak.core.ids import CapabilityId
from chainbreak.core.models import AuthoritySet, ProviderCapabilityBinding

#: STS's own hard limit on an inline ``Policy=`` session-policy parameter.
MAX_SESSION_POLICY_CHARS = 2048

_WHOAMI_STATEMENT = {
    "Sid": "CbAlwaysWhoami",
    "Effect": "Allow",
    "Action": ["sts:GetCallerIdentity"],
    "Resource": "*",
}


def _statement_sid(capability_id: str) -> str:
    """A valid IAM ``Sid`` (alphanumeric only) derived from a capability id,
    e.g. ``objectstore.read`` -> ``CbAllowObjectstoreRead``."""
    words = re.split(r"[._-]", capability_id)
    return "CbAllow" + "".join(w.capitalize() for w in words)


def synthesize_session_policy(
    intended_capabilities: AuthoritySet,
    bindings: Mapping[CapabilityId, ProviderCapabilityBinding],
    *,
    namespace: str,
) -> str:
    """Build the session-policy JSON document for a ``SESSION_POLICY_SCOPED``
    (or ``ROLE_CHAIN_WITH_SESSION_POLICY``) delegation.

    Session policies intersect with the role's identity policy and can never
    grant (AWS_PROVIDER_SPEC section 4) -- this document only ever narrows,
    regardless of what it lists.
    """
    statements = [
        {
            "Sid": _statement_sid(capability_id),
            "Effect": "Allow",
            "Action": list(bindings[capability_id].actions),
            "Resource": [bindings[capability_id].resource_template.format(namespace=namespace)],
        }
        for capability_id in intended_capabilities.sorted
        if capability_id != "identity.whoami"
    ]
    statements.append(_WHOAMI_STATEMENT)

    document = json.dumps({"Version": "2012-10-17", "Statement": statements}, separators=(",", ":"))
    if len(document) > MAX_SESSION_POLICY_CHARS:
        raise ConfigurationError(
            f"synthesized session policy is {len(document)} chars, "
            f"exceeds the {MAX_SESSION_POLICY_CHARS}-char STS limit",
            document_length=len(document),
            capability_count=len(intended_capabilities),
        )
    return document
