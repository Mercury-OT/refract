"""Public port and data-model definitions for the framework core.

The core depends on these abstract seams rather than product-specific code.
Adapters implement the execution interfaces and transport runtime data through
these neutral structures.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TypeAlias, TypedDict


JsonScalar: TypeAlias = str | int | float | bool | None


class IdentifiedUiObject(TypedDict):
    id: str
    fields: dict[str, JsonScalar]


class AnonymousUiObject(TypedDict):
    fields: dict[str, JsonScalar]


class RenderedAnchor(TypedDict):
    identified: list[IdentifiedUiObject]
    anonymous: list[AnonymousUiObject]


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestAction:
    """Prepared operation data; nested containers are owned by the recipient.

    Core constructs a fresh copy at the resolver boundary and retains its own
    request for comparison. This view carries neither a declaration nor checks.
    """

    method: str
    path: str = field(repr=False, metadata={"sensitive": True})
    body: dict | None = field(default=None, repr=False, metadata={"sensitive": True})
    query: dict | None = field(default=None, repr=False, metadata={"sensitive": True})
    headers: dict | None = field(default=None, repr=False, metadata={"sensitive": True})


@dataclass
class RequestSpec:
    method: str
    path: str
    body: dict | None = None
    traceparent: str | None = None
    query: dict[str, str] = field(default_factory=dict, kw_only=True, repr=False, metadata={"sensitive": True})
    headers: dict[str, str] = field(default_factory=dict, kw_only=True, repr=False, metadata={"sensitive": True})


@dataclass(frozen=True, slots=True, kw_only=True)
class BrowserNetworkIdentity:
    """Actual browser origin/network identity, not a transmitted server trace."""

    origin: str = field(repr=False, metadata={"sensitive": True})
    request_id: str = field(repr=False, metadata={"sensitive": True})


@dataclass
class RecordedResponse:
    status: int
    headers: dict = field(repr=False, metadata={"sensitive": True})
    json: dict | None
    text: str
    trace_id: str | None
    request: RequestSpec
    # Recording identity for step-based execution.
    step_id: str | None = None
    attempt_index: int = 0
    is_final: bool = True
    template_path: str | None = None       # declared step.request.path
    bound_logical_path: str | None = None  # path after binding substitution
    actual_path: str | None = None         # adapter-resolved path used in execution
    request_id: str | None = field(default=None, kw_only=True)
    mock_fixture_id: str | None = field(default=None, kw_only=True)
    user: str | None = field(default=None, kw_only=True)
    session_generation: int | None = field(default=None, kw_only=True)
    request_header_items: list[tuple[str, str]] | None = field(default=None, kw_only=True, repr=False, metadata={"sensitive": True})
    header_items: list[tuple[str, str]] | None = field(default=None, kw_only=True, repr=False, metadata={"sensitive": True})
    browser_identity: BrowserNetworkIdentity | None = field(default=None, kw_only=True, repr=False, metadata={"sensitive": True})


@dataclass
class Span:
    name: str
    attributes: dict = field(default_factory=dict)


@dataclass
class StateFacts:
    trace_id: str
    spans: list = field(default_factory=list)


@dataclass(frozen=True, slots=True, kw_only=True)
class ObjectStateQuery:
    """One read-only observation request, without assertions or expected values."""

    observation_id: str = field(repr=False)
    projection: str
    step_id: str
    trace_id: str = field(repr=False)
    user: str | None = field(repr=False)
    session_generation: int
    object: str
    id: str | int = field(repr=False, metadata={"sensitive": True})
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ObservedObject:
    id: str | int = field(repr=False, metadata={"sensitive": True})
    fields: dict = field(repr=False, metadata={"sensitive": True})


@dataclass(frozen=True, slots=True)
class ObjectStateFacts:
    query: ObjectStateQuery = field(repr=False, metadata={"sensitive": True})
    source: str = field(repr=False, metadata={"sensitive": True})
    complete: bool
    objects: list[ObservedObject] = field(repr=False, metadata={"sensitive": True})


@dataclass
class NormalizedResponse:
    succeeded: bool
    fields: dict
    status: int
    raw: "RecordedResponse"


@dataclass(frozen=True, kw_only=True)
class UiActionPermit:
    """One-use authorization for one primitive, independent of network traffic."""

    execution_id: str
    action_id: str
    step_id: str
    mode: str
    action: str
    target: str | None
    value: object = field(repr=False, metadata={"sensitive": True})
    token: str = field(
        repr=False,
        metadata={"sensitive": True},
    )
    user: str | None = None
    session_generation: int = 0
    context_id: str = ""
    object_id: object = field(default=None, repr=False, metadata={"sensitive": True})


@dataclass(frozen=True, kw_only=True)
class MockResponse:
    """One inspectable ordered fixture; never generated from expectations."""

    fixture_id: str
    source: str
    method: str
    path: str = field(repr=False)
    response: dict = field(repr=False, metadata={"sensitive": True})
    status: int = 200
    query: dict[str, str] | None = field(default=None, kw_only=True, repr=False, metadata={"sensitive": True})
    request_headers: dict[str, str] | None = field(default=None, kw_only=True, repr=False, metadata={"sensitive": True})
    response_headers: dict[str, str] | None = field(default=None, kw_only=True, repr=False, metadata={"sensitive": True})


@dataclass
class MockResponseQueue:
    """A run-local transport cursor shared by all mock browser contexts."""
    plan: list[MockResponse] = field(repr=False, metadata={"sensitive": True})
    index: int = 0


@dataclass(frozen=True, kw_only=True)
class UiTraffic:
    """An origin-associated request/response pair, not a time-window guess."""

    execution_id: str
    action_id: str
    step_id: str
    mode: str
    request_id: str
    permit_token: str = field(repr=False, metadata={"sensitive": True})
    request: RequestSpec = field(repr=False, metadata={"sensitive": True})
    response: RecordedResponse = field(repr=False, metadata={"sensitive": True})
    mock_fixture_id: str | None = None
    user: str | None = None
    session_generation: int = 0
    context_id: str = ""
    browser_identity: BrowserNetworkIdentity | None = field(default=None, kw_only=True, repr=False, metadata={"sensitive": True})


@dataclass(frozen=True, kw_only=True)
class UiObjectSelection:
    """Observed scoped-control selection; consistency evidence, not attestation."""

    object_id: object = field(repr=False, metadata={"sensitive": True})
    object_matches: int
    control_matches: int


@dataclass(frozen=True, kw_only=True)
class UiActionEvidence:
    """Adapter evidence returned for one permitted semantic UI action."""

    execution_id: str
    action_id: str
    step_id: str
    mode: str
    permit_token: str = field(
        repr=False,
        metadata={"sensitive": True},
    )
    traffic: list[UiTraffic] = field(repr=False, metadata={"sensitive": True})
    rendered: dict[str, RenderedAnchor] = field(
        repr=False,
        metadata={"sensitive": True},
    )
    diagnostic_outgoing: list[RequestSpec] = field(
        default_factory=list,
        repr=False,
        metadata={"sensitive": True},
    )
    diagnostic_recorded: list[RecordedResponse] = field(
        default_factory=list,
        repr=False,
        metadata={"sensitive": True},
    )
    mock_recordings: list[RecordedResponse] = field(
        default_factory=list, repr=False, metadata={"sensitive": True},
    )
    user: str | None = None
    session_generation: int = 0
    context_id: str = ""
    diagnostic_notes: list[str] = field(default_factory=list, kw_only=True, repr=False)
    object_selection: UiObjectSelection | None = field(default=None, repr=False, metadata={"sensitive": True})


@dataclass(frozen=True, kw_only=True)
class UiActionResult:
    """Exactly one of completed evidence or an explicit adapter skip."""

    evidence: UiActionEvidence | None = None
    skip_reason: str | None = None

    def __post_init__(self):
        if self.evidence is not None and self.skip_reason is not None:
            raise ValueError(
                "UiActionResult requires exactly one of evidence or a non-empty skip_reason")
        if self.evidence is None and not (
            isinstance(self.skip_reason, str) and self.skip_reason.strip()
        ):
            raise ValueError(
                "UiActionResult requires exactly one of evidence or a non-empty skip_reason")


@dataclass(frozen=True, kw_only=True)
class UserSession:
    """Sensitive adapter authentication material, never report serialization."""
    principal_id: str = field(repr=False, metadata={"sensitive": True})
    authentication_id: str = field(repr=False, metadata={"sensitive": True})
    credentials: object = field(repr=False, metadata={"sensitive": True})


class Authenticator(ABC):
    @abstractmethod
    def identify(self, user: str) -> str: ...

    @abstractmethod
    def session(self, user: str) -> UserSession: ...


class ApiDriver(ABC):
    @abstractmethod
    def send(self, spec: RequestSpec, session: object) -> RecordedResponse: ...


class ResponseNormalizer(ABC):
    @abstractmethod
    def normalize(self, resp: RecordedResponse) -> NormalizedResponse: ...

class StateProbe(ABC):
    @abstractmethod
    def observe(self, trace_id: str) -> StateFacts: ...


class ObjectStateProbe(ABC):
    """Return actual object facts through an independently configured reader."""

    @abstractmethod
    def observe_object(self, query: ObjectStateQuery) -> ObjectStateFacts: ...


class UiDriver(ABC):
    """Marker for UI adapters; execution requires primitive stepwise capability."""


class StepwiseUiDriver(ABC):
    """Core-authorized primitives in one context per current user/session."""

    @abstractmethod
    def supports_stepwise_mode(self, mode: str) -> bool:
        """Explicitly opt into mock or live primitive execution."""
        ...

    def supports_object_targeting(self, mode: str) -> bool:
        """Opt in only when scoped clicks provide a validated selection receipt."""
        return False

    @abstractmethod
    def open_stepwise(
        self,
        session: object | None,
        *,
        mode: str,
        mock_plan: list[MockResponse] | None = None,
        mock_queue: MockResponseQueue | None = None,
        user: str | None = None,
        session_generation: int = 0,
        context_id: str = "",
    ) -> object: ...

    @abstractmethod
    def perform_step(
        self,
        context: object,
        permit: UiActionPermit,
        *,
        business_header_names: tuple[str, ...] = (),
    ) -> UiActionResult: ...

    @abstractmethod
    def close_stepwise(self, context: object) -> None: ...

    def snapshot(self, context: object) -> dict[str, RenderedAnchor]:
        """Read current rendering after a core wait without performing an action."""
        raise NotImplementedError("UI snapshot capability not supported")


class Recorder(ABC):
    @abstractmethod
    def record(self, resp: RecordedResponse) -> None: ...

    @abstractmethod
    def responses(self) -> list: ...
