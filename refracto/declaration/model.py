from dataclasses import dataclass, field

@dataclass(frozen=True)
class Grid:
    level: str
    module: str

@dataclass(frozen=True)
class Ref:
    ref: str

@dataclass(frozen=True)
class Input:
    kind: str
    value: object = field(repr=False, metadata={"sensitive": True})

@dataclass(frozen=True)
class ValueRef:
    """A data-only reference to a value resolved elsewhere in the scenario.

    `source` names where the value comes from (``"bind"`` or ``"input"``).
    `key` names the specific entry within that source. This carries no
    expression, arithmetic, or concatenation — it is purely a pointer to one
    value.
    """
    source: str
    key: str

@dataclass
class Assertion:
    check: str
    params: dict = field(default_factory=dict)

@dataclass
class RequestTemplate:
    method: str
    path: str
    body: dict | None = None
    path_segments: list | None = field(default=None, kw_only=True)
    declared_path: str | None = field(default=None, kw_only=True)

@dataclass(frozen=True)
class Binding:
    placeholder: str
    from_step: str
    field: str

@dataclass(frozen=True)
class ResultSource:
    """Declaration-only response alias; never contains a resolved value."""
    from_step: str
    response_field: str

@dataclass(frozen=True)
class PollPolicy:
    on_timeout: str

@dataclass
class Expect:
    frontend: list = field(default_factory=list)
    response: list = field(default_factory=list)
    backend_state: list = field(default_factory=list)

@dataclass
class Step:
    id: str
    request: RequestTemplate | None
    expect: Expect
    bind: list = field(default_factory=list)
    poll: object = None
    action: str = "request"
    target: str | None = None
    value: object = None
    duration: int | None = None
    request_asserted: bool = False

@dataclass
class Scenario:
    id: str
    grid: Grid | None
    actor: str
    precondition: list
    inputs: list
    intent: str
    steps: list
    source_lookup: dict = field(default_factory=dict, kw_only=True, compare=False, repr=False)
    include_dependencies: dict = field(default_factory=dict, kw_only=True, compare=False, repr=False)
    results: dict = field(default_factory=dict, kw_only=True, compare=False, repr=False)
    included_results: dict = field(default_factory=dict, kw_only=True, compare=False, repr=False)

    @property
    def parameters(self):
        return {item.kind: item.value for item in self.inputs}

    @property
    def description(self):
        return self.intent
