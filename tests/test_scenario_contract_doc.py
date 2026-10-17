"""Guard the scenario contract documentation.

`SCENARIO.md` must exist, cover every bounded vocabulary term, keep its worked
examples product-neutral by using only `demo.*` scenario identifiers, and — most
importantly — its worked examples must actually be **loadable** declarations.
This prevents the public contract document from drifting when the vocabulary
changes.
"""
import re
import tempfile
from pathlib import Path

import pytest
import yaml

from refracto.declaration import vocabulary as vocab
from refracto.declaration.loader import load_scenario

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "SCENARIO.md"

_FENCED_YAML_RE = re.compile(r"```yaml\n(.*?)```", re.DOTALL)


def _worked_example_blocks() -> list:
    """Return the fenced YAML blocks in SCENARIO.md that are whole scenarios.

    Blocks that merely illustrate a fragment (a `bind:` mapping, a `poll:` policy)
    carry no top-level `scenario:` key and are not loadable on their own.
    """
    return [
        block for block in _FENCED_YAML_RE.findall(DOC.read_text(encoding="utf-8"))
        if re.search(r"(?m)^scenario:\s*\S+", block)
    ]


def test_scenario_doc_exists():
    assert DOC.is_file()


def test_doc_covers_every_bounded_term():
    text = DOC.read_text(encoding="utf-8")
    for point, terms in vocab._TERMS.items():
        assert point in text, f"SCENARIO.md does not mention observation point {point}"
        for term in terms:
            assert term in text, f"SCENARIO.md does not mention vocabulary term {point}.{term}"


def test_doc_example_scenarios_are_neutral_demo_only():
    text = DOC.read_text(encoding="utf-8")
    ids = re.findall(r"(?m)^\s*scenario:\s*(\S+)", text)
    assert ids, "SCENARIO.md should contain at least one worked example scenario block"
    for sid in ids:
        assert sid.startswith("demo."), f"Non-neutral example scenario id: {sid!r}. Worked examples must use demo.*"


def test_doc_has_at_least_one_worked_example():
    assert _worked_example_blocks(), (
        "SCENARIO.md should contain at least one fenced YAML block declaring a whole scenario")


@pytest.mark.parametrize("index", range(len(_worked_example_blocks())))
def test_doc_worked_examples_load(index):
    """A documented example that the loader rejects is worse than no example: readers
    copy it and hit a `DeclarationError` on their first attempt. The contract document
    must only publish declarations the contract itself accepts."""
    block = _worked_example_blocks()[index]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "doc_example.yaml"
        path.write_text(block, encoding="utf-8")
        load_scenario(str(path))


def test_documented_explicit_stop_fragment_loads_in_its_stated_context(tmp_path):
    blocks = _FENCED_YAML_RE.findall(DOC.read_text(encoding="utf-8"))
    fragments = [block for block in blocks if "on_failure: stop" in block]
    assert len(fragments) == 1
    fragment = yaml.safe_load(fragments[0])
    data = {
        "schema_version": 1,
        "scenario": "demo.documented_stop",
        "actor": "editor",
        "steps": [{
            "id": "create",
            "do": {"request": {"method": "POST", "path": ["records"]}},
        }, *fragment],
    }
    path = tmp_path / "documented_stop.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    scenario = load_scenario(str(path))
    assert scenario.steps[0].on_failure == "continue"
    assert scenario.steps[1].on_failure == "stop"
