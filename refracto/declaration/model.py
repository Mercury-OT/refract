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


@dataclass(frozen=True)
class RunUnique:
    """Symbolic unique source, frozen per parameter and execution scope."""


@dataclass(frozen=True)
class RunTime:
    """A bounded UTC offset from the one wall-clock base frozen for this run."""
    unit: str | None = None
    amount: int = 0


@dataclass(frozen=True)
class StringConcat:
    """A bounded sequence of string literals and already parsed references."""
    parts: tuple = field(repr=False, metadata={"sensitive": True})

@dataclass
class Assertion:
    check: str
    params: dict = field(default_factory=dict, repr=False, metadata={"sensitive": True})

@dataclass
class RequestTemplate:
    method: str
    path: str
    body: dict | None = None
    path_segments: list | None = field(default=None, kw_only=True)
    declared_path: str | None = field(default=None, kw_only=True)
    query: dict | None = field(default=None, kw_only=True, repr=False, metadata={"sensitive": True})
    headers: dict | None = field(default=None, kw_only=True, repr=False, metadata={"sensitive": True})

@dataclass(frozen=True)
class Binding:
    placeholder: str
    from_step: str
    field: str
    key: str | None = field(default=None, kw_only=True)
    matching: dict | None = field(default=None, kw_only=True, repr=False, metadata={"sensitive": True})
    member_field: str | None = field(default=None, kw_only=True)

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
    on_failure: str = field(default="continue", kw_only=True)
    user: str | None = field(default=None, kw_only=True)
    session: str | None = field(default=None, kw_only=True)

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
    users: list[str] | None = field(default=None, kw_only=True)
    include_user_mappings: dict = field(default_factory=dict, kw_only=True, compare=False, repr=False)
    reference_bindings: dict = field(default_factory=dict, kw_only=True, compare=False, repr=False)
    run_values_bound: bool = field(default=False, kw_only=True, compare=False, repr=False)
    run_unique_values: dict[str, str] = field(default_factory=dict, kw_only=True, compare=False,
                                             repr=False, metadata={"sensitive": True})
    run_time: str | None = field(default=None, kw_only=True, compare=False,
                                 repr=False, metadata={"sensitive": True})
    run_time_source: str | None = field(default=None, kw_only=True, compare=False,
                                        repr=False, metadata={"sensitive": True})
    run_time_values: dict[str, str] = field(default_factory=dict, kw_only=True, compare=False,
                                           repr=False, metadata={"sensitive": True})

    def __post_init__(self):
        # Bounded Python-constructor migration only. The YAML loader never
        # accepts actor and always supplies the explicit users declaration.
        if self.users is None:
            self.users = [self.actor] if self.actor else []

    def selected_user(self, step):
        """The declaration's participant, before anonymous runtime translation."""
        if step.user is not None:
            return step.user
        return self.users[0] if type(self.users) is list and len(self.users) == 1 else None

    def effective_user(self, step):
        selected = self.selected_user(step)
        return None if type(selected) is str and selected == "anonymous" else selected

    @property
    def parameters(self):
        return {item.kind: item.value for item in self.inputs}

    @property
    def description(self):
        return self.intent
