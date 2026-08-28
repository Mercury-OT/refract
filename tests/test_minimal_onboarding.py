import inspect
import re
from pathlib import Path

import pytest

from refracto import ports, runner
from refracto.report import DEGRADED, PASSED

from examples.minimal import adapters as minimal_adapters
from examples.minimal.app import MinimalRestApp
from examples.minimal.run_example import SCENARIO_PATH, run


ROOT = Path(__file__).resolve().parents[1]
MINIMAL_ROOT = ROOT / "examples" / "minimal"
STATE_SCENARIO_PATH = MINIMAL_ROOT / "scenarios" / "state_degraded.yaml"
ONBOARDING_PATH = ROOT / "docs" / "onboarding.md"
FENCED_BLOCK_RE = re.compile(
    r"^(?P<fence>`{3,}|~{3,})[^\n]*\n(?P<body>.*?)^(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


def _fenced_blocks(markdown: str) -> list[str]:
    return [match.group("body") for match in FENCED_BLOCK_RE.finditer(markdown)]


def test_minimal_backend_and_contract_run_passes_strict_gate():
    rep = run()

    assert rep.status == PASSED
    assert rep.degradations() == []
    assert {domain.projection for domain in rep.domains} == {"backend", "contract"}


def test_missing_state_probe_is_an_explicit_step_degradation():
    app = MinimalRestApp()
    adapters = minimal_adapters.build_adapters(app)

    rep = runner.run_scenario(
        STATE_SCENARIO_PATH,
        adapters,
        projections=("backend",),
    )

    assert rep.status == DEGRADED
    assert rep.degradations()
    assert any(
        projection == "backend"
        and step_id == "create_with_state_expectation"
        and "no StateProbe" in reason
        for projection, step_id, reason in rep.degradations()
    )


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_missing_ui_driver_is_rejected_before_request_side_effects(projection):
    app = MinimalRestApp()
    adapters = minimal_adapters.build_adapters(app)

    with pytest.raises(ValueError, match="UiDriver"):
        runner.run_scenario(
            SCENARIO_PATH,
            adapters,
            projections=(projection,),
        )

    assert adapters.api.sent == []
    assert app.request_count == 0


def test_empty_204_response_normalizes_and_the_scenario_stays_passed():
    app = MinimalRestApp()
    adapters = minimal_adapters.build_adapters(app)

    rep = runner.run_scenario(
        SCENARIO_PATH,
        adapters,
        projections=("backend", "contract"),
    )

    backend = next(domain for domain in rep.domains if domain.projection == "backend")
    empty_response = next(
        response for response in backend.provider_recordings if response.status == 204
    )
    normalized = adapters.normalizer.normalize(empty_response)

    assert normalized.succeeded is True
    assert normalized.fields == {}
    assert rep.status == PASSED


def test_contract_only_is_rejected_before_request_side_effects():
    app = MinimalRestApp()
    adapters = minimal_adapters.build_adapters(app)

    with pytest.raises(ValueError, match="backend"):
        runner.run_scenario(
            SCENARIO_PATH,
            adapters,
            projections=("contract",),
        )

    assert adapters.api.sent == []
    assert app.request_count == 0


def test_minimal_module_implements_only_the_three_intended_ports():
    adapter_classes = [
        value
        for value in vars(minimal_adapters).values()
        if inspect.isclass(value) and value.__module__ == minimal_adapters.__name__
    ]
    port_types = {
        port_type
        for adapter_class in adapter_classes
        for port_type in (
            ports.Authenticator,
            ports.ApiDriver,
            ports.ResponseNormalizer,
            ports.StateProbe,
            ports.UiDriver,
        )
        if issubclass(adapter_class, port_type)
    }

    assert port_types == {
        ports.Authenticator,
        ports.ApiDriver,
        ports.ResponseNormalizer,
    }


def test_onboarding_code_blocks_are_copied_from_tested_minimal_sources():
    guide = ONBOARDING_PATH.read_text(encoding="utf-8")
    code_blocks = _fenced_blocks(guide)
    sources = [
        path.read_text(encoding="utf-8")
        for path in MINIMAL_ROOT.rglob("*")
        if path.suffix in {".py", ".yaml"}
    ]

    assert code_blocks
    for block in code_blocks:
        assert any(block in source for source in sources), (
            "onboarding code block has no verbatim source under examples/minimal:\n"
            f"{block}"
        )


def test_fence_extractor_covers_any_language_and_unlabelled_blocks():
    markdown = """```python
python block
```
```bash
bash block
```
```json
json block
```
```text
text block
```
```
unlabelled block
```
~~~custom
tilde block
~~~"""

    assert _fenced_blocks(markdown) == [
        "python block\n",
        "bash block\n",
        "json block\n",
        "text block\n",
        "unlabelled block\n",
        "tilde block\n",
    ]


def test_onboarding_states_strict_gate_and_request_response_boundary():
    guide = ONBOARDING_PATH.read_text(encoding="utf-8")

    assert "Do not use `assert rep.passed` as a strict gate" in guide
    assert 'assert rep.status == "PASSED"' in guide
    assert "assert rep.degradations() == []" in guide
    assert "request/response-only integration" in guide
    assert "does **not** provide internal-state verification" in guide
