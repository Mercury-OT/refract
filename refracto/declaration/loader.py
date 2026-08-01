import numbers
import re
import yaml
from refracto.declaration import vocabulary as vocab
from refracto.declaration.model import (
    Scenario, Grid, Ref, Input, Assertion, Expect, RequestTemplate, Binding, PollPolicy, Step,
)


class DeclarationError(Exception):
    pass


# --- placeholder grammar ----------------------------------------------------
# Placeholder names must look like identifiers.
_PLACEHOLDER_RE = re.compile(r"\{([^}]+)\}")
_PLACEHOLDER_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _malformed_placeholder(where: str, s: str) -> None:
    raise DeclarationError(f"{where}: malformed placeholder in {s!r}")


def _extract_placeholder_names(s: str, where: str) -> list:
    """Extract `{name}` placeholders from a string.

    Reject malformed placeholders, including invalid names and unmatched braces.
    """
    names = []
    spans = []
    for m in _PLACEHOLDER_RE.finditer(s):
        name = m.group(1)
        if not _PLACEHOLDER_NAME_RE.match(name):
            _malformed_placeholder(where, s)
        names.append(name)
        spans.append((m.start(), m.end()))
    leftover = list(s)
    for start, end in spans:
        for i in range(start, end):
            leftover[i] = ""
    if "{" in leftover or "}" in leftover:
        _malformed_placeholder(where, s)
    return names


def _scan_path_placeholders(path: str, where: str) -> list:
    """A path placeholder must occupy a whole `/`-separated segment."""
    names = []
    for seg in path.split("/"):
        if "{" not in seg and "}" not in seg:
            continue
        m = re.fullmatch(r"\{([^}]+)\}", seg)
        if not m or not _PLACEHOLDER_NAME_RE.match(m.group(1)):
            raise DeclarationError(
                f"{where}: path placeholder must occupy a whole segment, "
                f"got segment {seg!r} in path {path!r}")
        names.append(m.group(1))
    return names


def _scan_body_placeholders(value, where: str) -> list:
    """Recurse through body values and collect placeholders.

    Body placeholders must occupy an entire scalar string. Placeholders are not
    allowed in map keys.
    """
    names = []
    if isinstance(value, str):
        found = _extract_placeholder_names(value, where)
        if found and (len(found) != 1 or value != "{" + found[0] + "}"):
            raise DeclarationError(
                f"{where}: in-string body placeholder interpolation forbidden, got {value!r}")
        names.extend(found)
    elif isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str) and ("{" in k or "}" in k):
                raise DeclarationError(f"{where}: placeholder not allowed in a body map key, got {k!r}")
            names.extend(_scan_body_placeholders(v, where))
    elif isinstance(value, list):
        for item in value:
            names.extend(_scan_body_placeholders(item, where))
    return names


def _normalize_method(raw_method, where: str) -> str:
    if not isinstance(raw_method, str) or not raw_method.strip():
        raise DeclarationError(f"{where} must be a non-empty string, got {raw_method!r}")
    return raw_method.strip().upper()


_TOP_LEVEL_KEYS = {
    "scenario", "grid", "actor", "precondition", "inputs", "intent", "expect",
    "version", "steps",
}

# Unknown nested keys are rejected fail-loud rather than ignored.
_STEP_KEYS = {"id", "request", "bind", "poll", "expect"}
_REQUEST_KEYS = {"method", "path", "body"}
_BINDING_KEYS = {"from", "field"}
_POLL_KEYS = {"on_timeout"}
_GRID_KEYS = {"level", "module"}
_PRECONDITION_KEYS = {"ref"}

_SUPPORTED_VERSIONS = (2,)

# A step's own `expect` does not contain a `request` block. Request ownership
# lives on the step itself.
_STEP_EXPECT_POINTS = ("frontend", "response", "backend_state")


def _require_nonempty_str(container, key, where):
    v = container.get(key)
    if not isinstance(v, str) or not v.strip():
        raise DeclarationError(f"{where} must be a non-empty string, got {v!r}")
    return v


def _is_number(v) -> bool:
    # bool is a subclass of int — a YAML `true` must not count as a number.
    return isinstance(v, numbers.Real) and not isinstance(v, bool)


def _validate_param_values(point: str, check: str, params: dict) -> None:
    if check == "count_gt" and not _is_number(params.get("n")):
        raise DeclarationError(f"{point}.count_gt: 'n' must be a number, got {params.get('n')!r}")
    if check == "span_attr":
        op = params.get("op")
        if op not in vocab.COMPARISON_OPS:
            raise DeclarationError(
                f"{point}.span_attr: 'op' must be one of {list(vocab.COMPARISON_OPS)}, got {op!r}")
        if op in vocab.ORDERING_OPS and not _is_number(params.get("value")):
            raise DeclarationError(
                f"{point}.span_attr: 'value' must be a number for op {op!r}, got {params.get('value')!r}")


def _parse_assertions(point: str, raw_list) -> list:
    if raw_list is None:
        return []
    if not isinstance(raw_list, list):
        raise DeclarationError(f"expect.{point} must be a list, got {type(raw_list).__name__}")
    out = []
    for item in raw_list:
        if not isinstance(item, dict) or "check" not in item:
            raise DeclarationError(f"{point}: each assertion must be a mapping with a 'check' key, got {item!r}")
        check = item["check"]
        if not vocab.is_valid(point, check):
            raise DeclarationError(f"{point}: unknown/invalid check {check!r}")
        params = {k: v for k, v in item.items() if k != "check"}
        required = vocab.required_params(point, check)
        for req in required:
            if req not in params:
                raise DeclarationError(f"{point}.{check}: missing required param {req!r}")
        allowed = set(required) | set(vocab.optional_params(point, check))
        extra = set(params) - allowed
        if extra:
            raise DeclarationError(
                f"{point}.{check}: unknown param(s) {sorted(extra)}; allowed: {sorted(allowed)}")
        _validate_param_values(point, check, params)
        out.append(Assertion(check=check, params=params))
    return out


def _parse_request(raw, where: str) -> RequestTemplate:
    if not isinstance(raw, dict):
        raise DeclarationError(f"{where} must be a mapping, got {type(raw).__name__}")
    unknown = set(raw) - _REQUEST_KEYS
    if unknown:
        raise DeclarationError(
            f"{where}: unknown key(s) {sorted(unknown)}; allowed: {sorted(_REQUEST_KEYS)}")
    method = _normalize_method(raw.get("method"), f"{where}.method")
    path = raw.get("path")
    if not isinstance(path, str) or not path:
        raise DeclarationError(f"{where}.path must be a non-empty string, got {path!r}")
    return RequestTemplate(method=method, path=path, body=raw.get("body"))


def _parse_bindings(raw_bind, seen_has_fields: dict, where: str) -> list:
    """Parse bindings against already-processed prior steps only."""
    if raw_bind is None:
        return []
    if not isinstance(raw_bind, dict):
        raise DeclarationError(f"{where}.bind must be a mapping, got {type(raw_bind).__name__}")
    out = []
    for placeholder, spec in raw_bind.items():
        if not isinstance(spec, dict):
            raise DeclarationError(
                f"{where}.bind.{placeholder} must be a mapping, got {type(spec).__name__}")
        unknown = set(spec) - _BINDING_KEYS
        if unknown:
            raise DeclarationError(
                f"{where}.bind.{placeholder}: unknown key(s) {sorted(unknown)}; "
                f"allowed: {sorted(_BINDING_KEYS)}")
        from_step = spec.get("from")
        field = spec.get("field")
        if from_step not in seen_has_fields:
            raise DeclarationError(
                f"{where}.bind.{placeholder}: 'from' {from_step!r} must reference a prior step id")
        if field not in seen_has_fields[from_step]:
            raise DeclarationError(
                f"{where}.bind.{placeholder}: bound field {field!r} not guaranteed by source step "
                f"{from_step!r} (source step must declare {{check: has, field: {field!r}}} "
                f"in its expect.response; 'success' does not satisfy this)")
        out.append(Binding(placeholder=placeholder, from_step=from_step, field=field))
    return out


def _parse_poll(raw_poll, method: str, where: str):
    if raw_poll is None:
        return None
    if not isinstance(raw_poll, dict):
        raise DeclarationError(f"{where}.poll must be a mapping, got {type(raw_poll).__name__}")
    unknown = set(raw_poll) - _POLL_KEYS
    if unknown:
        raise DeclarationError(
            f"{where}.poll: unknown key(s) {sorted(unknown)}; allowed: {sorted(_POLL_KEYS)}")
    on_timeout = raw_poll.get("on_timeout", "FAIL")
    if on_timeout not in vocab.POLL_ON_TIMEOUT:
        raise DeclarationError(
            f"{where}.poll.on_timeout must be one of {list(vocab.POLL_ON_TIMEOUT)}, got {on_timeout!r}")
    if method not in vocab.POLL_SAFE_METHODS:
        raise DeclarationError(
            f"{where}.poll: poll target method must be one of {list(vocab.POLL_SAFE_METHODS)}, "
            f"got {method!r} (GET-only)")
    return PollPolicy(on_timeout=on_timeout)


def _build_expect(raw_expect, allowed_points, where: str) -> Expect:
    """Validate an `expect` block and build the corresponding Expect object."""
    if raw_expect is None:
        raw_expect = {}
    if not isinstance(raw_expect, dict):
        raise DeclarationError(f"{where} must be a mapping, got {type(raw_expect).__name__}")
    unknown_points = set(raw_expect) - set(allowed_points)
    if unknown_points:
        raise DeclarationError(
            f"unknown {where} block(s) {sorted(unknown_points)}; allowed: {list(allowed_points)}")
    return Expect(
        frontend=_parse_assertions("frontend", raw_expect.get("frontend")),
        response=_parse_assertions("response", raw_expect.get("response")),
        backend_state=_parse_assertions("backend_state", raw_expect.get("backend_state")),
    )


def _parse_v2_steps(steps_raw: list) -> list:
    """Parse v2 steps in file order and validate prior-step bindings."""
    seen_has_fields = {}   # step_id -> set of fields declared via {check: has, field: ...}
    steps = []
    for idx, raw in enumerate(steps_raw):
        if not isinstance(raw, dict):
            raise DeclarationError(f"step[{idx}] must be a mapping, got {type(raw).__name__}")
        unknown = set(raw) - _STEP_KEYS
        if unknown:
            raise DeclarationError(
                f"step[{idx}]: unknown key(s) {sorted(unknown)}; allowed: {sorted(_STEP_KEYS)}")

        step_id = raw.get("id")
        if not isinstance(step_id, str) or not step_id.strip():
            raise DeclarationError(f"step[{idx}]: 'id' must be a non-empty string, got {step_id!r}")
        if step_id in seen_has_fields:
            raise DeclarationError(f"step id {step_id!r} is duplicated")
        where = f"step {step_id!r}"

        if "request" not in raw:
            raise DeclarationError(f"{where}: missing 'request'")
        request = _parse_request(raw["request"], f"{where}.request")

        expect = _build_expect(raw.get("expect"), _STEP_EXPECT_POINTS, f"{where}.expect")
        has_fields = {a.params["field"] for a in expect.response if a.check == "has"}

        bind = _parse_bindings(raw.get("bind"), seen_has_fields, where)
        poll = _parse_poll(raw.get("poll"), request.method, where)

        if poll is not None and not expect.response:
            raise DeclarationError(
                f"{where}: a poll step requires at least one expect.response assertion "
                f"(the stop condition)")

        used_placeholders = set(_scan_path_placeholders(request.path, f"{where}.request.path"))
        if request.body is not None:
            used_placeholders |= set(_scan_body_placeholders(request.body, f"{where}.request.body"))
        bound_placeholders = {b.placeholder for b in bind}

        unbound = used_placeholders - bound_placeholders
        if unbound:
            raise DeclarationError(f"{where}: unbound placeholder(s) {sorted(unbound)}")
        unused = bound_placeholders - used_placeholders
        if unused:
            raise DeclarationError(f"{where}: declared bind never used: {sorted(unused)}")

        steps.append(Step(id=step_id, request=request, expect=expect, bind=bind, poll=poll))
        seen_has_fields[step_id] = has_fields
    return steps


def _load_v1_step(d: dict) -> Step:
    """Normalize a legacy flat scenario into one implicit step."""
    exp = d.get("expect", {})
    if not isinstance(exp, dict):
        raise DeclarationError(f"'expect' must be a mapping, got {type(exp).__name__}")

    # In v1, `expect.request` carries at most one request assertion.
    request_assertions = _parse_assertions("request", exp.get("request"))
    if len(request_assertions) > 1:
        raise DeclarationError(
            "v1 scenario has more than one 'expect.request' assertion; migrate to v2 steps")

    expect = _build_expect(exp, vocab.OBSERVATION_POINTS, "expect")
    request = None
    if request_assertions:
        params = request_assertions[0].params
        request = RequestTemplate(method=params["method"], path=params["path"])
        # In v1, the optional `async` hint names a response field that must also
        # appear in the normalized response contract.
        async_field = params.get("async")
        if async_field and not any(
                a.check == "has" and a.params.get("field") == async_field for a in expect.response):
            expect.response.append(Assertion(check="has", params={"field": async_field}))
    return Step(id="main", request=request, expect=expect)


def load_scenario(path: str) -> Scenario:
    with open(path, encoding="utf-8") as f:
        d = yaml.safe_load(f)
    if not isinstance(d, dict):
        raise DeclarationError(f"scenario must be a top-level mapping, got {type(d).__name__}")
    unknown = set(d) - _TOP_LEVEL_KEYS
    if unknown:
        raise DeclarationError(
            f"unknown top-level field(s) {sorted(unknown)}; allowed: {sorted(_TOP_LEVEL_KEYS)}")

    version = d.get("version")
    has_expect = "expect" in d
    has_steps = "steps" in d

    if version == 1:
        raise DeclarationError("'version: 1' is not valid; legacy flat scenarios carry no version field")
    if version is not None and version != 2:
        raise DeclarationError(
            f"unsupported 'version' {version!r}; supported versions: {list(_SUPPORTED_VERSIONS)}")
    if has_expect and has_steps:
        raise DeclarationError(
            "scenario cannot have both a top-level 'expect' and 'steps'; use v2 'steps' only")
    if version is None and has_steps:
        raise DeclarationError("scenario has 'steps' but no 'version'; add `version: 2`")
    if version == 2 and not has_steps:
        raise DeclarationError("scenario declares `version: 2` but has no 'steps'; v2 requires 'steps'")
    is_v2 = version == 2

    try:
        _require_nonempty_str(d, "scenario", "'scenario'")
        _require_nonempty_str(d, "actor", "'actor'")

        grid_raw = d["grid"]
        if not isinstance(grid_raw, dict):
            raise DeclarationError(f"'grid' must be a mapping, got {type(grid_raw).__name__}")
        unknown_grid = set(grid_raw) - _GRID_KEYS
        if unknown_grid:
            raise DeclarationError(
                f"unknown 'grid' key(s) {sorted(unknown_grid)}; allowed: {sorted(_GRID_KEYS)}")
        _require_nonempty_str(grid_raw, "level", "'grid.level'")
        _require_nonempty_str(grid_raw, "module", "'grid.module'")
        grid = Grid(level=grid_raw["level"], module=grid_raw["module"])

        inputs_raw = d.get("inputs", [])
        if not isinstance(inputs_raw, list):
            raise DeclarationError(f"'inputs' must be a list, got {type(inputs_raw).__name__}")
        inputs = []
        for item in inputs_raw:
            if not isinstance(item, dict) or len(item) != 1:
                raise DeclarationError(f"inputs: each entry must be a mapping with exactly one key, got {item!r}")
            (kind, value), = item.items()
            inputs.append(Input(kind=kind, value=value))

        precondition_raw = d.get("precondition", [])
        if not isinstance(precondition_raw, list):
            raise DeclarationError(f"'precondition' must be a list, got {type(precondition_raw).__name__}")
        precondition = []
        for p_idx, r in enumerate(precondition_raw):
            if not isinstance(r, dict) or "ref" not in r:
                raise DeclarationError(f"precondition: each entry must be a mapping with a 'ref' key, got {r!r}")
            unknown_pre = set(r) - _PRECONDITION_KEYS
            if unknown_pre:
                raise DeclarationError(
                    f"precondition[{p_idx}]: unknown key(s) {sorted(unknown_pre)}; "
                    f"allowed: {sorted(_PRECONDITION_KEYS)}")
            precondition.append(Ref(ref=r["ref"]))

        if is_v2:
            steps_raw = d["steps"]
            if not isinstance(steps_raw, list):
                raise DeclarationError(f"'steps' must be a list, got {type(steps_raw).__name__}")
            steps = _parse_v2_steps(steps_raw)
        else:
            steps = [_load_v1_step(d)]

        return Scenario(
            id=d["scenario"], grid=grid, actor=d["actor"],
            precondition=precondition, inputs=inputs,
            intent=d.get("intent", ""), steps=steps,
        )
    except KeyError as e:
        raise DeclarationError(f"missing required field: {e}") from e
