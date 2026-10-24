"""Documented fragments use the executable parser, not a second mini-language."""
from pathlib import Path
import re

import pytest
import yaml

from refracto.declaration.loader import _load_document, load_scenario
from refracto.declaration.binding import prepare_step
from refracto.ports import NormalizedResponse
from tests.test_stabilization_documentation import write_context


ROOT = Path(__file__).resolve().parents[1]


def request(step_id):
    return {"id": step_id, "do": {"request": {"method": "GET", "path": ["records"]}},
            "expect": {"response": [{"check": "status_equals", "value": 200}]}}


@pytest.mark.parametrize("document", ["SCENARIO.md", "docs/tasks/run-values-concat.md"])
def test_parameter_and_response_fragments_parse_and_resolve(tmp_path, document):
    from refracto.declaration.run_values import bind_run_values
    blocks = re.findall(r"```yaml\n(.*?)```", (ROOT / document).read_text(), re.S)
    parameter_block = next(block for block in blocks
                           if "from_run: unique" in block and block.startswith("parameters:"))
    expression_block = next(block for block in blocks
                            if block.startswith("concat:") and "from_step: account" in block)
    # Validate untouched bytes first: safe_load alone would erase duplicate keys.
    for name, block in (("run_parameters", parameter_block), ("response_concat", expression_block)):
        assert load_scenario(write_context(tmp_path / name, name, block)).steps
    parameters = yaml.safe_load(parameter_block)["parameters"]
    expression = yaml.safe_load(expression_block)
    assert parameters["run_token"] == {"from_run": "unique"}
    assert set(parameters["document_title"]) == {"concat"}
    account, batch, consume = [request(name) for name in ("account", "batch", "consume")]
    consume["do"]["request"]["body"] = {
        "name": expression, "title": {"from_parameter": "document_title"}}
    case = _load_document({"schema_version": 1, "scenario": "demo.documented_composition",
                           "users": [], "parameters": parameters, "steps": [account, batch, consume]})
    frozen, token = bind_run_values(case)
    step, bound = prepare_step(frozen.steps[2], frozen, {
        "account": NormalizedResponse(True, {"account_code": "AC12"}, 200, None),
        "batch": NormalizedResponse(True, {"batch_code": "B07"}, 200, None),
    })
    assert step.request.body == {"name": "AC12-document-B07", "title": token + "-document-" + token}
    assert set(bound.values()) == {"AC12", "B07"}
