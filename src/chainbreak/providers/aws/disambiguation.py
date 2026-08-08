"""Response-shape disambiguation (AWS_PROVIDER_SPEC section 6.1, 6.2).

The highest-risk module in the AWS adapter (AWS_PROVIDER_SPEC's own "Risks"
section): get this wrong and every denial-shaped measurement is meaningless.
Every classifier here is a pure function of already-fetched response data --
no network calls, no state -- so it is testable against literal, hand-copied
AWS message strings with no AWS account at all, and the canary test
(``test_disambiguation.py``) that pins today's exact message wording is what
would catch AWS silently changing it.

Message-shape classification never guesses: the absence of a recognized
phrase yields ``DENIED_UNATTRIBUTED``, not a best-effort attribution
(AWS_PROVIDER_SPEC section 6.1 point 3).
"""

from __future__ import annotations

import re

from chainbreak.core.enums import DenialAttribution, OutcomeClass

#: AWS's own explicit-deny message shape, e.g. "...is not authorized to
#: perform: s3:GetObject on resource: ... with an explicit deny in an
#: identity-based policy". The trailing noun phrase varies (identity-based
#: policy, resource-based policy, session policy, service control policy --
#: and "permissions boundary", which is the one kind that does *not* end in
#: the word "policy") -- matched on the "with an explicit deny in a(n)"
#: prefix alone, which is itself AWS's distinctive, documented phrase, so a
#: new kind of policy AWS adds later is still recognized as "explicit deny"
#: without needing its exact noun enumerated here.
_EXPLICIT_DENY_RE = re.compile(
    r"with an explicit deny in (?:a|an) [a-z][a-z \-]{2,40}", re.IGNORECASE
)

#: AWS's default implicit-denial message shape: "...is not authorized to
#: perform: <action> on resource: <resource> because no <policy-kind> policy
#: allows the <action> action". Only classified implicit when the explicit
#: phrase above is absent -- checked in that order by the caller.
_IMPLICIT_NO_ALLOW_RE = re.compile(r"is not authorized to perform", re.IGNORECASE)


def classify_denial_message(message: str) -> tuple[OutcomeClass, DenialAttribution | None]:
    """Classify an AWS denial message's explicit-vs-implicit shape.

    Returns ``(DENIED_UNATTRIBUTED, None)`` -- never a guess -- when neither
    recognized phrase is present, per AWS_PROVIDER_SPEC section 6.1's third
    mitigation.
    """
    if _EXPLICIT_DENY_RE.search(message):
        return OutcomeClass.DENIED_EXPLICIT, DenialAttribution.EXPLICIT_DENY
    if _IMPLICIT_NO_ALLOW_RE.search(message):
        return OutcomeClass.DENIED_IMPLICIT, DenialAttribution.IMPLICIT_NO_ALLOW
    return OutcomeClass.DENIED_UNATTRIBUTED, None


def is_lambda_function_fault(function_error: str | None) -> bool:
    """``True`` iff the Lambda ``Invoke`` response carries a ``FunctionError``
    field -- a fault *inside* the invoked function (it raised, or the
    handler crashed), which is orthogonal to whether the caller was
    authorized to invoke it at all (AWS_PROVIDER_SPEC section 6.2's
    disambiguation hazard: ``StatusCode: 200`` with a populated
    ``FunctionError`` is a function fault, never a denial -- IAM already let
    the call through, or there would be no response body to inspect)."""
    return bool(function_error)


def is_s3_object_missing(error_code: str, *, http_status: int | None) -> bool:
    """``True`` for S3's "object does not exist" signal in either of its two
    disguises (``NoSuchKey`` when the caller holds ``s3:ListBucket``, a bare
    ``404`` otherwise) -- distinct from an authorization denial, which this
    function does not classify (see module docstring: by the time an agent
    probes ``objectstore.read``, the precondition check has already confirmed
    the object exists, so this path should not fire and its firing is itself
    the interesting signal -- AWS_PROVIDER_SPEC section 6.1)."""
    if error_code == "NoSuchKey":
        return True
    return error_code == "404" or http_status == 404


def is_access_denied_code(error_code: str) -> bool:
    return error_code in {"AccessDenied", "AccessDeniedException", "UnauthorizedException"}
