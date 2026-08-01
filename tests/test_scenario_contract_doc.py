"""Guard the scenario contract documentation.

`SCENARIO.md` must exist, cover every bounded vocabulary term, and keep its
worked examples product-neutral by using only `demo.*` scenario identifiers.
This prevents the public contract document from drifting when the vocabulary
changes.
"""
import re
from pathlib import Path

from refracto.declaration import vocabulary as vocab

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "SCENARIO.md"


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
