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


@dataclass
class RequestSpec:
    method: str
    path: str
    body: dict | None = None
    traceparent: str | None = None


@dataclass
class RecordedResponse:
    status: int
    headers: dict
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


@dataclass
class Span:
    name: str
    attributes: dict = field(default_factory=dict)


@dataclass
class StateFacts:
    trace_id: str
    spans: list = field(default_factory=list)


@dataclass
class NormalizedResponse:
    succeeded: bool
    fields: dict
    status: int
    raw: "RecordedResponse"


@dataclass
class UiResult:
    # anchor -> a partial mapping of identified and anonymous rendered objects
    rendered: dict[str, RenderedAnchor] = field(default_factory=dict)
    outgoing: list = field(default_factory=list)    # list[RequestSpec] sent by the UI
    recorded: list = field(default_factory=list)    # list[RecordedResponse] captured from UI traffic


@dataclass(frozen=True, kw_only=True)
class UiActionPermit:
    """One-use core authorization for one semantic UI action."""

    execution_id: str
    action_id: str
    request_id: str
    step_id: str
    attempt_index: int
    mode: str
    method: str
    template_path: str
    bound_logical_path: str = field(
        repr=False,
        metadata={"sensitive": True},
    )
    traceparent: str
    trace_id: str
    token: str = field(
        repr=False,
        metadata={"sensitive": True},
    )
    resolved_bindings: dict[str, object] = field(
        repr=False,
        compare=False,
        metadata={"sensitive": True},
    )
    mock_response: dict = field(
        repr=False,
        compare=False,
        metadata={"sensitive": True},
    )


@dataclass(frozen=True, kw_only=True)
class UiActionEvidence:
    """Adapter evidence returned for one permitted semantic UI action."""

    execution_id: str
    action_id: str
    request_id: str
    step_id: str
    attempt_index: int
    mode: str
    method: str
    template_path: str
    bound_logical_path: str = field(
        repr=False,
        metadata={"sensitive": True},
    )
    permit_token: str = field(
        repr=False,
        metadata={"sensitive": True},
    )
    actual_path: str = field(
        repr=False,
        metadata={"sensitive": True},
    )
    is_final: bool
    primary_request: RequestSpec = field(
        repr=False,
        metadata={"sensitive": True},
    )
    primary_response: RecordedResponse = field(
        repr=False,
        metadata={"sensitive": True},
    )
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


class Authenticator(ABC):
    @abstractmethod
    def session(self, role: str) -> object: ...


class ApiDriver(ABC):
    @abstractmethod
    def send(self, spec: RequestSpec, session: object) -> RecordedResponse: ...


class ResponseNormalizer(ABC):
    @abstractmethod
    def normalize(self, resp: RecordedResponse) -> NormalizedResponse: ...

    @abstractmethod
    def synthesize(self, fields, values=None) -> dict:
        """Build a product-shaped success response for declared fields.

        ``values`` supplies concrete values for equality-constrained fields;
        other fields may use adapter-defined placeholders.
        """
        ...


class StateProbe(ABC):
    @abstractmethod
    def observe(self, trace_id: str) -> StateFacts: ...


class UiDriver(ABC):
    @abstractmethod
    def run_intent(self, scenario, session: object | None, mock: dict | None) -> UiResult: ...


class StepwiseUiDriver(ABC):
    """Optional capability for core-authorized, stateful multi-step UI execution."""

    @abstractmethod
    def open_stepwise(
        self,
        scenario,
        session: object | None,
        *,
        mode: str,
    ) -> object: ...

    @abstractmethod
    def perform_step(
        self,
        scenario,
        step,
        context: object,
        permit: UiActionPermit,
    ) -> UiActionResult: ...

    @abstractmethod
    def close_stepwise(self, context: object) -> None: ...


class Recorder(ABC):
    @abstractmethod
    def record(self, resp: RecordedResponse) -> None: ...

    @abstractmethod
    def responses(self) -> list: ...
