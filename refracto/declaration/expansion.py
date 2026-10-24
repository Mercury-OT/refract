"""Explicit source-confidentiality review rendering, never runtime serialization."""
import copy

from refracto.declaration.model import ValueRef, RunUnique, RunTime, StringConcat


def expansion_view(scenario):
    if scenario.run_values_bound:
        raise ValueError("expanded review requires a symbolic declaration, not a bound run")
    parameters = scenario.parameters
    bindings = dict(scenario.reference_bindings)
    bindings.update({binding.placeholder: binding for step in scenario.steps for binding in step.bind})

    def aliases(items):
        return {name: {"from_step": source.from_step, "response_field": source.response_field}
                for name, source in items.items()}

    def value(node):
        if isinstance(node, RunUnique):
            return {"kind": "run-value", "from_run": "unique"}
        if isinstance(node, RunTime):
            result = {"kind": "run-value", "from_run": "time"}
            if node.unit is not None:
                result["offset"] = {node.unit: node.amount}
            return result
        if isinstance(node, StringConcat):
            return {"kind": "concat", "parts": [value(part) for part in node.parts]}
        if isinstance(node, ValueRef):
            if node.source == "input":
                return {"kind": "reference", "from_parameter": node.key}
            binding = bindings.get(node.key)
            if binding is not None:
                result = {"kind": "reference", "from_step": binding.from_step, "response_field": binding.field}
                if binding.key is not None:
                    result["key"] = binding.key
                if binding.matching is not None:
                    result["matching"] = {key: value(item) for key, item in binding.matching.items()}
                    result["member_field"] = binding.member_field
                return result
            # An unused with parameter still belongs in the explicit view, but
            # has no consuming leaf's Binding. Keys use loader's length prefix.
            length, _, rest = node.key.partition(":")
            count = int(length)
            return {"kind": "reference", "from_step": rest[:count], "response_field": rest[count + 1:]}
        if isinstance(node, list):
            return {"kind": "list", "items": [value(item) for item in node]}
        if isinstance(node, dict):
            return {"kind": "object", "entries": {key: value(item) for key, item in node.items()}}
        return {"kind": "literal", "value": node}

    def request(template):
        result = {"method": template.method, "path": [value(item) for item in template.path_segments]}
        if template.body is not None:
            result["body"] = value(template.body)
        if template.query is not None:
            result["query"] = value(template.query)
        if template.headers is not None:
            result["headers"] = value(template.headers)
        return result

    steps = []
    for step in scenario.steps:
        item = {"id": step.id, "source": copy.deepcopy(scenario.source_lookup.get(step.id)),
                "user": scenario.selected_user(step) or "anonymous", "session": step.session or "reuse",
                "on_failure": step.on_failure,
                "do": {"request": request(step.request)} if step.action == "request" else step.action}
        if step.target is not None:
            item["target"] = step.target
        if step.action == "fill":
            item["value"] = value(step.value)
        if step.duration is not None:
            item["duration"] = step.duration
        expect = {}
        if step.request_asserted:
            expect["request"] = request(step.request)
        for point, label in (("frontend", "ui"), ("response", "response"), ("backend_state", "backend_state")):
            assertions = getattr(step.expect, point)
            if assertions:
                expect[label] = [{"check": assertion.check,
                                  **{key: value(item) for key, item in assertion.params.items()}}
                                 for assertion in assertions]
        if expect:
            item["expect"] = expect
        if step.poll is not None:
            item["poll"] = {"on_timeout": step.poll.on_timeout}
        steps.append(item)
    return {"view": "expanded-review/1", "scenario": scenario.id,
            "users": list(scenario.users), "description": scenario.description,
            "grid": None if scenario.grid is None else {"level": scenario.grid.level, "module": scenario.grid.module},
            "dependencies": copy.deepcopy(scenario.include_dependencies),
            "include_user_mappings": copy.deepcopy(scenario.include_user_mappings),
            "results": aliases(scenario.results),
            "included_results": {sid: aliases(items) for sid, items in scenario.included_results.items()},
            "parameters": {key: value(item) for key, item in parameters.items()}, "steps": steps}
