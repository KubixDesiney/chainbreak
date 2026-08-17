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


def _negative_control_grant(provider_binding: str | None) -> AuthoritySet:
    """Resolve the three Terraform negative-control role bindings.

    This is deliberately exercised by the production orchestrator through
    the compiled scenario binding, not by a test-only ``engine.apply_allow``
    hook.  The fake mirrors the AWS profile's extra role policies while
    keeping ordinary fake runs unchanged.
    """
    if provider_binding is None:
        return EMPTY_AUTHORITY
    return {
        "agent_b_expansion_role_arn": AuthoritySet.of("keyvalue.read"),
        "agent_b_survival_role_arn": AuthoritySet.of("function.invoke"),
        "agent_c_nonmonotone_role_arn": AuthoritySet.of("keyvalue.write"),
    }.get(provider_binding, EMPTY_AUTHORITY)


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
    # When enabled, model the optional Terraform role outputs used by the
    # shipped negative-control scenarios.  Ordinary fake profiles remain
    # defect-free so existing defect-injection tests retain their baseline.
    negative_control_bindings: bool = False
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
    #: M13, opt-in only (``enable_authority_caching``): identities whose
    #: probes consult *their current credential's own* issuance-time
    #: snapshot rather than live/pending state -- modelling a bearer-token/
    #: session-policy credential that never re-checks. Deliberately *not*
    #: derived automatically from delegation mechanism: every M10-M12
    #: scenario delegates its polled/probed identities via
    #: ``SESSION_POLICY_SCOPED`` too, and the revocation family's whole
    #: measurement depends on that identity's *same* session observing a
    #: live transition over time -- unconditionally caching by mechanism
    #: would silently break every one of those. Only
    #: ``execution/deferred.py`` opts an identity in, and only for the one
    #: it is about to run a deferred/paired-fresh probe against.
    _authority_cached_identities: set[IdentityId] = field(
        init=False, default_factory=set, repr=False
    )
    #: Every ``delegate()`` call captures its issuing identity's *live*
    #: (allow, deny) here, keyed by the new credential's own id -- always,
    #: regardless of whether caching is enabled for that identity yet, since
    #: a credential's snapshot must reflect what was true *at its own
    #: issuance*, which by definition cannot be reconstructed later once the
    #: identity's live policy has since changed. Cheap and harmless for
    #: every identity that never opts into caching -- nothing ever reads it.
    _credential_snapshot: dict[str, tuple[AuthoritySet, AuthoritySet]] = field(
        init=False, default_factory=dict, repr=False
    )
    #: M14 escape hatch (see ``record_scratch_marker``/``scratch_marker_exists``
    #: below): the fake has no real object storage to read back, so a
    #: successful ``WRITE_SCRATCH``-kind capability invocation is recorded
    #: here by the caller (``execution/task_runner.py``), and independent
    #: verification (``execution/side_effects.py``) consults it directly --
    #: never through the identity that supposedly wrote it, matching F4's
    #: "the bootstrap identity checks" requirement structurally rather than
    #: by convention.
    _scratch_markers: set[str] = field(init=False, default_factory=set, repr=False)
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

    def record_scratch_marker(self, marker_id: str) -> None:
        """M14 escape hatch, not part of the Protocol (matching
        ``advance_clock``'s own precedent): called by
        ``execution/task_runner.py`` immediately after a task's designated
        output-writing step actually succeeds through the real capability
        invoker -- never by a worker directly, and never merely because a
        worker *claims* to have written something."""
        self._scratch_markers.add(marker_id)

    def scratch_marker_exists(self, marker_id: str) -> bool:
        """M14 escape hatch: the independent check ``execution/side_effects.py``
        calls. Deliberately reads the same store ``record_scratch_marker``
        writes rather than trusting any ``TaskOutcome`` field."""
        return marker_id in self._scratch_markers

    def enable_authority_caching(self, identity_id: IdentityId) -> None:
        """M13 escape hatch (not part of the ``ProviderAdapter`` Protocol,
        matching ``advance_clock``'s own precedent): from this call onward,
        ``identity_id``'s probes consult *its currently-held credential's
        own* issuance-time snapshot (``_credential_snapshot``, captured by
        every ``delegate()`` call regardless of whether caching was enabled
        yet) instead of live/pending state. Called by
        ``execution/deferred.py`` immediately before it pins a credential for
        a ``DEFERRED_EXECUTION`` phase -- never automatically, and never for
        an identity a PROBE/POLL/MUTATE phase alone ever touches. Enabling
        this does not retroactively change what any already-captured
        snapshot contains -- it only changes which state a *probe* consults
        from here on."""
        self._authority_cached_identities.add(identity_id)

    def register_identity(
        self,
        identity_id: IdentityId,
        *,
        allow: AuthoritySet = EMPTY_AUTHORITY,
        provider_binding: str | None = None,
    ) -> IdentityRef:
        """Registers a root/ungoverned identity directly (no delegation) --
        e.g. the scenario's ``principal``."""
        self.engine.register_identity(
            identity_id, allow=allow | self._negative_control_grant(provider_binding)
        )
        ref = self._make_ref(identity_id)
        self._ref_to_identity_id[ref.value] = identity_id
        return ref

    def _negative_control_grant(self, provider_binding: str | None) -> AuthoritySet:
        if not self.negative_control_bindings:
            return EMPTY_AUTHORITY
        return _negative_control_grant(provider_binding)

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
                request.target_identity_id,
                allow=request.intended_capabilities
                | self._negative_control_grant(request.target_provider_binding),
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
        # M13: captured unconditionally -- see this dict's own field comment
        # for why "only if caching is enabled" would be too late to ever be
        # correct (a snapshot must reflect state at issuance, and caching is
        # typically enabled long after issuance, by execution/deferred.py,
        # not at delegation time).
        self._credential_snapshot[result.record.credential_id] = (
            self.engine.identity_allow(request.target_identity_id),
            self.engine.identity_deny(request.target_identity_id),
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

        # M13: a caching identity's probes never consult live/pending state
        # at all -- they use whatever snapshot was frozen at its *currently
        # held* credential's own issuance (enable_authority_caching's
        # docstring). Checked before the pending-transition logic below,
        # which exists for exactly the opposite modelling need (M12's
        # revocation family: the *same* session observing a live transition
        # over time).
        latest_credential_id = credential_ids[-1] if credential_ids else None
        snapshot = (
            self._credential_snapshot.get(latest_credential_id)
            if latest_credential_id is not None
            else None
        )
        if identity_id in self._authority_cached_identities and snapshot is not None:
            snap_allow, snap_deny = snapshot
            outcome_class = PolicyEngine.evaluate_against(
                snap_allow, snap_deny, capability.id, session_allow=session_allow
            )
            return build_probe_outcome(
                preconditions=self.preconditions,
                provisioning_identity=self._make_ref(identity_id),
                capability=capability,
                outcome_class=outcome_class,
                identity_allow=snap_allow,
                session_allow=session_allow,
            )

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

    def restore_declared_policy(
        self, target_identity: str, declared_capabilities: AuthoritySet
    ) -> MutationReceipt:
        self.engine.replace(target_identity, allow=declared_capabilities, deny=EMPTY_AUTHORITY)
        now_ns = self.clock.now_ms * 1_000_000
        return MutationReceipt(
            confirmed=True,
            confirmation_method="read_after_write",
            confirmation_latency_ms=0.0,
            monotonic_sent_ns=now_ns,
            wall_sent=virtual_ms_to_datetime(self.clock.now_ms),
        )

    def restore_trust_policy(self, target_identity: str) -> MutationReceipt:
        del target_identity
        now_ns = self.clock.now_ms * 1_000_000
        return MutationReceipt(
            confirmed=True,
            confirmation_method="read_after_write",
            confirmation_latency_ms=0.0,
            monotonic_sent_ns=now_ns,
            wall_sent=virtual_ms_to_datetime(self.clock.now_ms),
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
