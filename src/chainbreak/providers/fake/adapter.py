"""``FakeProviderAdapter``: wires the policy engine, session store and
consistency model behind the ``ProviderAdapter`` Protocol.

The one piece of state that lives here rather than in ``engine.py`` is
*pending mutation transitions*: while a consistency-model window is still
open for an identity, a ``probe()`` against it must evaluate against the
*pre-mutation* snapshot, not the (already-updated) authoritative engine
state -- ``snapshot_policy_state`` always reads the authoritative state
directly, modelling that a confirmed read-after-write (the bootstrap
identity's own control-plane read) is fast, while an *agent's* own probe can
still observe stale behavior for up to ``propagation_delay_ms`` longer
(AWS_PROVIDER_SPEC section 7). At most one transition is tracked per
identity at a time: a second mutation applied before the first has settled
folds the first into authoritative state immediately, which is how these
scenarios are actually run in practice (one mutation, then observe).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from chainbreak.capabilities.guard import OperationAllowlist
from chainbreak.capabilities.loader import load_catalog
from chainbreak.core.canonical import dumps
from chainbreak.core.enums import (
    DelegationMechanism,
    DenialAttribution,
    MutationKind,
    OutcomeClass,
    PolicyKind,
    Provider,
)
from chainbreak.core.errors import CapabilityResolutionError, MutationTargetForbiddenError
from chainbreak.core.ids import (
    CapabilityId,
    IdentityId,
    Namespace,
    digest_ref,
    fingerprint_json,
)
from chainbreak.core.models import (
    EMPTY_AUTHORITY,
    AuthoritySet,
    Capability,
    CapabilityCatalog,
    IdentityRef,
    MutationReceipt,
    PolicyFingerprint,
    PolicyMutation,
    PolicyStateSnapshot,
    ProbeOutcome,
    ProbeTiming,
    ProviderCapabilityBinding,
    SafetyEnvelope,
)
from chainbreak.providers.base.namespace import assert_namespace
from chainbreak.providers.base.types import (
    DelegationRequest,
    DelegationResult,
    EnvironmentDescriptor,
    PreflightCheck,
    PreflightReport,
    ProbeRequest,
    ProbeResult,
)
from chainbreak.providers.fake.bindings import build_fake_bindings
from chainbreak.providers.fake.clock import VirtualClock
from chainbreak.providers.fake.consistency import ConsistencyModel, MutationVisibility
from chainbreak.providers.fake.engine import PolicyEngine
from chainbreak.providers.fake.probes import (
    MarkerStore,
    build_fake_preconditions,
    build_probe_outcome,
)
from chainbreak.providers.fake.session import SessionStore, virtual_ms_to_datetime

ADAPTER_VERSION = "0.1.0"

#: Identities that must never be a mutation target (SI-12): the fake's own
#: analogue of AWS_PROVIDER_SPEC section 3's bootstrap/principal.
_DEFAULT_PROTECTED_IDENTITIES = frozenset({"bootstrap", "principal"})


@dataclass
class _PendingTransition:
    pre_allow: AuthoritySet
    pre_deny: AuthoritySet
    visibility: MutationVisibility


@dataclass
class FakeProviderAdapter:
    """A deterministic, in-memory authorization laboratory (ARCHITECTURE.md
    section 3.9). Construct one per run; nothing here is shared across runs."""

    seed: int = 0
    account_ref: str = "555555555555"
    region: str = "fake-region-1"
    namespace: Namespace = "cb-00000000"
    propagation_delay_ms: int = 0
    jitter_ms: int = 0
    oscillate: bool = False
    transient_error_rate: float = 0.0
    clock_skew_ms: float = 0.0
    throttle_after_n_calls: int | None = None
    protected_identities: frozenset[str] = field(
        default_factory=lambda: _DEFAULT_PROTECTED_IDENTITIES
    )

    name: str = field(default="fake", init=False)
    adapter_version: str = field(default=ADAPTER_VERSION, init=False)

    catalog: CapabilityCatalog = field(init=False, repr=False)
    bindings: dict[str, ProviderCapabilityBinding] = field(init=False, repr=False)
    engine: PolicyEngine = field(init=False, repr=False)
    sessions: SessionStore = field(init=False, repr=False)
    consistency: ConsistencyModel = field(init=False, repr=False)
    markers: MarkerStore = field(init=False, repr=False)
    clock: VirtualClock = field(init=False, repr=False)

    _ref_to_identity_id: dict[str, IdentityId] = field(init=False, default_factory=dict, repr=False)
    _session_scope: dict[IdentityId, AuthoritySet | None] = field(
        init=False, default_factory=dict, repr=False
    )
    _credentials_by_identity: dict[IdentityId, list[str]] = field(
        init=False, default_factory=dict, repr=False
    )
    _pending: dict[IdentityId, _PendingTransition] = field(
        init=False, default_factory=dict, repr=False
    )
    _snapshot_counter: int = field(init=False, default=0, repr=False)
    _call_count: int = field(init=False, default=0, repr=False)
    _fault_rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.catalog = load_catalog()
        self.bindings = {b.capability_id: b for b in build_fake_bindings(self.catalog)}
        self.engine = PolicyEngine()
        self.sessions = SessionStore(seed=self.seed)
        self.consistency = ConsistencyModel(
            propagation_delay_ms=self.propagation_delay_ms,
            jitter_ms=self.jitter_ms,
            oscillate=self.oscillate,
            seed=self.seed,
        )
        self.markers = MarkerStore()
        self.preconditions = build_fake_preconditions(self.markers)
        self.clock = VirtualClock()
        # A distinct RNG stream from session/consistency so fault injection
        # draws never perturb their seeded sequences (F6).
        self._fault_rng = random.Random(self.seed ^ 0x5A5A5A5A)  # noqa: S311  # nosec B311

    # -- setup, not part of the Protocol ---------------------------------

    def advance_clock(self, milliseconds: int) -> None:
        self.clock.advance(milliseconds)

    def register_identity(
        self, identity_id: IdentityId, *, allow: AuthoritySet = EMPTY_AUTHORITY
    ) -> IdentityRef:
        """Registers a root/ungoverned identity directly (no delegation) --
        e.g. the scenario's ``principal``."""
        self.engine.register_identity(identity_id, allow=allow)
        ref = self._make_ref(identity_id)
        self._ref_to_identity_id[ref.value] = identity_id
        return ref

    def _make_ref(self, identity_id: IdentityId) -> IdentityRef:
        return IdentityRef(
            provider=Provider.FAKE,
            kind="role",
            value=f"fake:{self.account_ref}:role/{self.namespace}-{identity_id}",
            region=self.region,
            account_ref=self.account_ref,
        )

    # -- ProviderAdapter Protocol -----------------------------------------

    def preflight(self, envelope: SafetyEnvelope) -> PreflightReport:
        checks = (
            PreflightCheck(
                name="account",
                passed=self.account_ref in envelope.allowed_account_ids,
                detail=self.account_ref,
            ),
            PreflightCheck(
                name="region", passed=self.region in envelope.allowed_regions, detail=self.region
            ),
            PreflightCheck(
                name="namespace",
                passed=self.namespace == envelope.namespace,
                detail=self.namespace,
            ),
        )
        return PreflightReport(
            passed=all(c.passed for c in checks),
            account_ref=self.account_ref,
            region=self.region,
            checks=checks,
        )

    def resolve_capability(self, cap_id: CapabilityId) -> ProviderCapabilityBinding:
        try:
            return self.bindings[cap_id]
        except KeyError:
            raise CapabilityResolutionError(
                f"no fake binding registered for {cap_id}",
                provider="fake",
                capability_id=cap_id,
            ) from None

    def describe_environment(self) -> EnvironmentDescriptor:
        return EnvironmentDescriptor(
            provider=Provider.FAKE,
            adapter_version=self.adapter_version,
            account_ref=self.account_ref,
            region=self.region,
            namespace=self.namespace,
        )

    def delegate(self, request: DelegationRequest) -> DelegationResult:
        # Checks the *caller's* ref -- the source identity requesting this
        # delegation -- against the run's namespace (SI-2). The newly minted
        # target ref is always in-namespace by construction (_make_ref always
        # embeds self.namespace), so asserting on it would be tautological.
        assert_namespace(request.source_identity.value, self.namespace)

        if not self.engine.is_registered(request.target_identity_id):
            self.engine.register_identity(
                request.target_identity_id, allow=request.intended_capabilities
            )

        result = self.sessions.issue(
            identity_ref=self._make_ref(request.target_identity_id),
            target_identity_id=request.target_identity_id,
            mechanism=request.mechanism,
            requested_duration_s=request.requested_duration_s,
            intended_capabilities=request.intended_capabilities,
            issued_at_ms=self.clock.now_ms,
        )

        self._ref_to_identity_id[result.identity_ref.value] = request.target_identity_id
        self._credentials_by_identity.setdefault(request.target_identity_id, []).append(
            result.record.credential_id
        )
        scopes_session = request.mechanism in (
            DelegationMechanism.SESSION_POLICY_SCOPED,
            DelegationMechanism.ROLE_CHAIN_WITH_SESSION_POLICY,
        )
        self._session_scope[request.target_identity_id] = (
            request.intended_capabilities if scopes_session else None
        )
        return result

    def probe(self, request: ProbeRequest) -> ProbeResult:
        # Resolved against the *request's own* declared namespace, not the
        # adapter's -- checking against self.namespace on both sides would
        # be tautological (always true) and would never catch a caller that
        # passed the wrong namespace into the request (SI-2's actual point).
        assert_namespace(request.identity_ref.value, self.namespace)
        target_ref = request.binding.resource_template.format(namespace=request.namespace)
        assert_namespace(target_ref, self.namespace)

        self._call_count += 1
        start_ms = self.clock.now_ms
        capability = self.catalog.get(request.capability_id)
        identity_id = self._ref_to_identity_id[request.identity_ref.value]

        # SI-3: the allowlist fires on every probe, exactly as it will for
        # the AWS adapter's botocore before-call hook (M8) -- the fake
        # "invokes" precisely its binding's one declared action, which is
        # what makes this the first real (non-test) caller of
        # capabilities/guard.py's OperationAllowlist since M2 built it.
        with OperationAllowlist(request.binding) as allowlist:
            for action in request.binding.actions:
                allowlist.record(action)
            outcome = self._decide_outcome(identity_id, capability, at_ms=start_ms)
        timing = self._build_timing(start_ms)
        return ProbeResult(outcome=outcome, timing=timing)

    def _decide_outcome(
        self, identity_id: IdentityId, capability: Capability, at_ms: int
    ) -> ProbeOutcome:
        if (
            self.throttle_after_n_calls is not None
            and self._call_count > self.throttle_after_n_calls
        ):
            return ProbeOutcome(
                outcome_class=OutcomeClass.ERROR_TRANSIENT,
                message_redacted="throttled (fake fault injection)",
                disambiguation_path="fault_injection_throttle",
            )
        if self.transient_error_rate and self._fault_rng.random() < self.transient_error_rate:
            return ProbeOutcome(
                outcome_class=OutcomeClass.ERROR_TRANSIENT,
                message_redacted="injected transient fault (fake fault injection)",
                disambiguation_path="fault_injection_transient",
            )

        credential_ids = self._credentials_by_identity.get(identity_id, [])
        if credential_ids and not self.sessions.is_live(credential_ids[-1], at_ms=at_ms):
            return ProbeOutcome(
                outcome_class=OutcomeClass.DENIED_IMPLICIT,
                denial_attribution=DenialAttribution.UNDISCLOSED,
                disambiguation_path="session_revoked",
            )

        session_allow = self._session_scope.get(identity_id)
        pending = self._pending.get(identity_id)
        # Only drop pending tracking once fully settled -- deleting it the
        # first time is_visible() happens to return True would end an
        # oscillating transition after its first flip instead of letting it
        # flip back, since every later probe would then fall straight
        # through to authoritative state with nothing left to consult.
        if pending is not None and at_ms >= pending.visibility.settle_at_ms:
            del self._pending[identity_id]
            pending = None

        if pending is not None and not pending.visibility.is_visible(at_ms):
            outcome_class = PolicyEngine.evaluate_against(
                pending.pre_allow,
                pending.pre_deny,
                capability.id,
                session_allow=session_allow,
            )
            identity_allow = pending.pre_allow
        else:
            outcome_class = self.engine.evaluate(
                identity_id, capability.id, session_allow=session_allow
            )
            identity_allow = self.engine.identity_allow(identity_id)

        return build_probe_outcome(
            preconditions=self.preconditions,
            provisioning_identity=self._make_ref(identity_id),
            capability=capability,
            outcome_class=outcome_class,
            identity_allow=identity_allow,
            session_allow=session_allow,
        )

    def _build_timing(self, start_ms: int) -> ProbeTiming:
        return ProbeTiming(
            monotonic_start_ns=start_ms * 1_000_000,
            monotonic_end_ns=start_ms * 1_000_000,
            wall_start=virtual_ms_to_datetime(start_ms),
            clock_offset_ms=self.clock_skew_ms,
            attempt_number=1,
            retries=0,
        )

    def apply_policy_mutation(self, mutation: PolicyMutation) -> MutationReceipt:
        target = mutation.target_identity
        if target in self.protected_identities:
            raise MutationTargetForbiddenError(
                f"refuses to mutate protected identity {target!r} (SI-12)",
                target_identity=target,
            )
        if not self.engine.is_registered(target):
            self.engine.register_identity(target)

        pre_allow = self.engine.identity_allow(target)
        pre_deny = self.engine.identity_deny(target)

        monotonic_sent_ns = self.clock.now_ms * 1_000_000
        wall_sent = virtual_ms_to_datetime(self.clock.now_ms)

        match mutation.kind:
            case MutationKind.ATTACH_INLINE_DENY:
                self.engine.apply_deny(target, mutation.denies_capabilities)
            case MutationKind.REMOVE_INLINE_POLICY:
                self.engine.remove_allow(target, mutation.denies_capabilities)
            case MutationKind.REPLACE_INLINE_POLICY:
                self.engine.replace(
                    target, allow=mutation.grants_capabilities, deny=mutation.denies_capabilities
                )
            case MutationKind.REVOKE_OLDER_SESSIONS:
                for credential_id in self._credentials_by_identity.get(target, []):
                    self.sessions.revoke(credential_id)
            case MutationKind.UPDATE_TRUST_POLICY | MutationKind.DELETE_SESSION_POLICY_SCOPE:
                # Both are built-in negative controls (AWS_PROVIDER_SPEC
                # section 4): neither affects a live session's authority --
                # a trust policy change governs future AssumeRole only, and
                # "deleting" a session policy scope only affects the *next*
                # delegation, not the credential already issued.
                pass

        self._pending[target] = _PendingTransition(
            pre_allow=pre_allow,
            pre_deny=pre_deny,
            visibility=self.consistency.schedule(applied_at_ms=self.clock.now_ms),
        )

        return MutationReceipt(
            confirmed=True,
            confirmation_method="read_after_write",
            confirmation_latency_ms=0.0,
            monotonic_sent_ns=monotonic_sent_ns,
            wall_sent=wall_sent,
        )

    def snapshot_policy_state(self, identity_ref: IdentityRef) -> PolicyStateSnapshot:
        identity_id = self._ref_to_identity_id[identity_ref.value]
        allow = self.engine.identity_allow(identity_id)
        deny = self.engine.identity_deny(identity_id)
        salt = f"fake-snapshot:{self.seed}:"

        document = dumps({"allow": allow.sorted, "deny": deny.sorted})
        fingerprint = PolicyFingerprint(
            policy_kind=PolicyKind.IDENTITY_INLINE,
            name_hash=digest_ref(identity_id, salt),
            document_sha256=fingerprint_json(document),
            statement_count=max(1, (0 if allow.is_empty() else 1) + (0 if deny.is_empty() else 1)),
            has_explicit_deny=not deny.is_empty(),
        )
        self._snapshot_counter += 1
        return PolicyStateSnapshot(
            snapshot_id=f"snap_fake_{self.seed}_{self._snapshot_counter:012d}",
            identity_id=identity_id,
            taken_at=virtual_ms_to_datetime(self.clock.now_ms),
            monotonic_ns=self.clock.now_ms * 1_000_000,
            policies=(fingerprint,),
        )
