"""Symbolic parameter analysis and explicit, isolated run-value freezing."""
import copy
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from refracto.declaration.model import Input, RunUnique, RunTime, StringConcat, ValueRef


UNKNOWN = object()
STRING = object()
_TIME_UNITS = {"days": 86400, "hours": 3600, "minutes": 60, "seconds": 1}
_MAX_OFFSET_SECONDS = (datetime.max - datetime.min).days * 86400 + 86399


def time_offset_seconds(node):
    """Validate typed nodes as well as parsed input without coercion."""
    if node.unit is None and type(node.amount) is int and node.amount == 0:
        return 0
    if (type(node.unit) is not str or node.unit not in _TIME_UNITS
            or type(node.amount) is not int):
        raise ValueError("time offset requires one supported unit and a strict integer")
    seconds = node.amount * _TIME_UNITS[node.unit]
    if abs(seconds) > _MAX_OFFSET_SECONDS:
        raise ValueError("time offset exceeds the representable datetime range")
    return seconds


def _parse_run_time(value):
    if value is None:
        return None
    match = re.fullmatch(
        r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})\.([0-9]{3})Z",
        value) if type(value) is str else None
    try:
        if match is not None:
            year, month, day, hour, minute, second, millisecond = map(int, match.groups())
            return datetime(year, month, day, hour, minute, second, millisecond * 1000,
                            tzinfo=timezone.utc)
    except ValueError:
        pass
    raise ValueError("run_time must be a valid UTC timestamp in YYYY-MM-DDTHH:MM:SS.sssZ format")


def _utc_now():
    return datetime.now(timezone.utc)


def _format_time(value):
    # strftime %Y is not zero-padded consistently for years below 1000.
    return (f"{value.year:04d}-{value.month:02d}-{value.day:02d}T"
            f"{value.hour:02d}:{value.minute:02d}:{value.second:02d}."
            f"{value.microsecond // 1000:03d}Z")


def known_value(node, parameters, active=None, _memo=None):
    """Inspect typed declarations without randomness or interpreting dictionaries.

    STRING means a string whose content depends on this run or a response;
    UNKNOWN means a response value whose type is not yet known.
    """
    active = set() if active is None else active
    memo = {} if _memo is None else _memo
    if isinstance(node, ValueRef):
        if node.source != "input":
            return UNKNOWN
        if node.key not in parameters:
            raise ValueError("unknown parameter dependency")
        if node.key in memo:
            return memo[node.key]
        if node.key in active:
            raise ValueError("cyclic parameter dependency")
        active.add(node.key)
        try:
            memo[node.key] = known_value(parameters[node.key], parameters, active, memo)
            return memo[node.key]
        finally:
            active.remove(node.key)
    if isinstance(node, RunTime):
        time_offset_seconds(node)
        return STRING
    if isinstance(node, RunUnique):
        return STRING
    if isinstance(node, StringConcat):
        parts = [known_value(part, parameters, active, memo) for part in node.parts]
        if any(type(part) is not str and part is not STRING and part is not UNKNOWN for part in parts):
            raise ValueError("concat operands must resolve to strings")
        return STRING if any(part is STRING or part is UNKNOWN for part in parts) else "".join(parts)
    return node


def validate_parameters(parameters):
    memo = {}
    for name in parameters:
        known_value(ValueRef("input", name), parameters, _memo=memo)


def _has_run_value(node, kind):
    if isinstance(node, kind):
        return True
    if isinstance(node, StringConcat):
        return any(_has_run_value(part, kind) for part in node.parts)
    if isinstance(node, dict):
        return any(_has_run_value(value, kind) for value in node.values())
    if isinstance(node, list):
        return any(_has_run_value(value, kind) for value in node)
    # Walking a container never interprets its keys as declaration markers.
    return False


def ensure_bound_run_values(scenario):
    """Low-level projections must not generate a token or pass an unbound run."""
    if any(_has_run_value(item.value, (RunUnique, RunTime)) for item in scenario.inputs):
        raise ValueError("run values must be explicitly bound before projection execution")


def _run_clock(scenario, run_time):
    """Validate symbolic inputs and establish the logical run's one UTC base."""
    fixed = _parse_run_time(run_time)
    if scenario.run_values_bound:
        raise ValueError("run values are already bound; use the original symbolic declaration")
    parameters = scenario.parameters
    try:
        validate_parameters(parameters)
    except RecursionError:
        raise ValueError("parameter dependency graph exceeds available recursion capacity") from None
    if not any(_has_run_value(value, RunTime) for value in parameters.values()):
        return None, None
    try:
        base = fixed if fixed is not None else _utc_now()
        if type(base) is not datetime or base.tzinfo is None or base.utcoffset() is None:
            raise ValueError("invalid UTC wall clock")
        base = base.astimezone(timezone.utc)
        base = base.replace(microsecond=(base.microsecond // 1000) * 1000)
    except Exception:
        raise ValueError("unable to establish the run UTC time") from None
    return base, "fixed" if fixed is not None else "actual"


def _bind_values(scenario, base, time_source):
    """Freeze one execution scope without re-reading a clock or shared state."""
    bound = copy.deepcopy(scenario)
    parameters = bound.parameters
    bound.run_unique_values = {}
    bound.run_time = _format_time(base) if base is not None else None
    bound.run_time_source = time_source
    bound.run_time_values = {}
    resolved, active = {}, set()

    def parameter(name):
        if name in resolved:
            return resolved[name]
        if name in active:
            raise ValueError("cyclic parameter dependency")
        active.add(name)
        try:
            resolved[name] = freeze(parameters[name], name)
            if isinstance(parameters[name], RunTime):
                bound.run_time_values[name] = resolved[name]
            return resolved[name]
        finally:
            active.remove(name)

    def freeze(node, owner):
        if isinstance(node, RunUnique):
            if owner not in bound.run_unique_values:
                bound.run_unique_values[owner] = uuid4().hex
            return bound.run_unique_values[owner]
        if isinstance(node, RunTime):
            try:
                return _format_time(base + timedelta(seconds=time_offset_seconds(node)))
            except (OverflowError, ValueError):
                raise ValueError("time offset overflows the run UTC time") from None
        if isinstance(node, ValueRef) and node.source == "input":
            value = parameter(node.key)
            # Keep a pointer when the dependency remains response-derived.
            return node if isinstance(value, (ValueRef, StringConcat)) else copy.deepcopy(value)
        if isinstance(node, StringConcat):
            parts = tuple(freeze(part, owner) for part in node.parts)
            if all(type(part) is str for part in parts):
                return "".join(parts)
            return replace(node, parts=parts)
        if isinstance(node, dict):
            return {key: freeze(value, owner) for key, value in node.items()}
        if isinstance(node, list):
            return [freeze(value, owner) for value in node]
        return copy.deepcopy(node)

    try:
        bound.inputs = [Input(name, parameter(name)) for name in parameters]
    except RecursionError:
        raise ValueError("parameter dependency graph exceeds available recursion capacity") from None
    bound.run_values_bound = True
    return bound


def bind_run_values(scenario, *, run_time=None):
    """Return an independent execution copy and its generated source-value map.

    Each compiled parameter is a separate source; references reuse their source.
    Response-dependent include arguments remain typed until their consuming step.
    This standalone call owns a fresh clock base and generation scope.
    """
    base, source = _run_clock(scenario, run_time)
    bound = _bind_values(scenario, base, source)
    return bound, copy.deepcopy(bound.run_unique_values)


def bind_projection_values(scenario, projections, *, run_time=None):
    """Prepare all execution copies before ports, sharing one logical UTC base.

    Only executable projections generate values. Contract gets an independent
    copy of backend's frozen declaration and never invokes the generator.
    """
    base, source = _run_clock(scenario, run_time)
    bound = {name: _bind_values(scenario, base, source)
             for name in ("backend", "frontend", "e2e") if name in projections}
    if "contract" in projections:
        bound["contract"] = copy.deepcopy(bound["backend"])
    return bound
