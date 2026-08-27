"""Public port and data-model definitions for the framework core.

The core depends on these abstract seams rather than product-specific code.
Adapters implement the execution interfaces and transport runtime data through
these neutral structures.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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
    rendered: dict = field(default_factory=dict)    # anchor -> {visible, count, text}
    outgoing: list = field(default_factory=list)    # list[RequestSpec] sent by the UI
    recorded: list = field(default_factory=list)    # list[RecordedResponse] captured from UI traffic


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


class Recorder(ABC):
    @abstractmethod
    def record(self, resp: RecordedResponse) -> None: ...

    @abstractmethod
    def responses(self) -> list: ...
