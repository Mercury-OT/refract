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
    value: str

@dataclass(frozen=True)
class ValueRef:
    """A data-only reference to a value resolved elsewhere in the scenario.

    `source` names where the value comes from (currently only ``"bind"``; a
    future ``"input"`` source lands here without changing the shape). `key`
    names the specific entry within that source. This carries no expression,
    arithmetic, or concatenation — it is purely a pointer to one value.
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

@dataclass(frozen=True)
class Binding:
    placeholder: str
    from_step: str
    field: str

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
    request: RequestTemplate
    expect: Expect
    bind: list = field(default_factory=list)
    poll: object = None

@dataclass
class Scenario:
    id: str
    grid: Grid
    actor: str
    precondition: list
    inputs: list
    intent: str
    steps: list
