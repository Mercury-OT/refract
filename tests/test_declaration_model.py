import dataclasses

from refracto.declaration.model import Binding, Expect, Grid, PollPolicy, RequestTemplate, Scenario, Step


def test_request_template_minimal():
    req = RequestTemplate(method="GET", path="/items")
    assert req.method == "GET"
    assert req.path == "/items"
    assert req.body is None


def test_request_template_with_body():
    req = RequestTemplate(method="POST", path="/items", body={"name": "test"})
    assert req.method == "POST"
    assert req.path == "/items"
    assert req.body == {"name": "test"}


def test_binding_frozen():
    binding = Binding(placeholder="itemId", from_step="create", field="id")
    assert binding.placeholder == "itemId"
    assert binding.from_step == "create"
    assert binding.field == "id"
    try:
        binding.placeholder = "changed"
        assert False, "Binding should be frozen"
    except (AttributeError, dataclasses.FrozenInstanceError):
        pass


def test_poll_policy_frozen():
    poll = PollPolicy(on_timeout="FAIL")
    assert poll.on_timeout == "FAIL"
    try:
        poll.on_timeout = "SKIP"
        assert False, "PollPolicy should be frozen"
    except (AttributeError, dataclasses.FrozenInstanceError):
        pass


def test_expect_has_no_request_field():
    expect = Expect()
    assert expect.frontend == []
    assert expect.response == []
    assert expect.backend_state == []
    assert not hasattr(expect, "request")


def test_expect_with_assertions():
    expect = Expect(frontend=["check1"], response=["check2"], backend_state=["check3"])
    assert expect.frontend == ["check1"]
    assert expect.response == ["check2"]
    assert expect.backend_state == ["check3"]


def test_step_minimal():
    req = RequestTemplate(method="GET", path="/items")
    expect = Expect()
    step = Step(id="main", request=req, expect=expect)
    assert step.id == "main"
    assert step.request.method == "GET"
    assert step.expect.response == []
    assert step.bind == []
    assert step.poll is None


def test_step_with_bind_and_poll():
    req = RequestTemplate(method="GET", path="/items")
    expect = Expect(response=["check1"])
    binding = Binding(placeholder="itemId", from_step="create", field="id")
    poll = PollPolicy(on_timeout="FAIL")
    step = Step(id="check", request=req, expect=expect, bind=[binding], poll=poll)
    assert step.id == "check"
    assert len(step.bind) == 1
    assert step.bind[0].placeholder == "itemId"
    assert step.poll.on_timeout == "FAIL"


def test_scenario_with_steps():
    grid = Grid(level="unit", module="test")
    step1 = Step(id="main", request=RequestTemplate(method="GET", path="/items"), expect=Expect())
    scenario = Scenario(
        id="test_scenario",
        grid=grid,
        actor="client",
        precondition=[],
        inputs=[],
        intent="test intent",
        steps=[step1],
    )
    assert scenario.id == "test_scenario"
    assert scenario.grid.level == "unit"
    assert scenario.actor == "client"
    assert len(scenario.steps) == 1
    assert scenario.steps[0].id == "main"


def test_scenario_steps_required():
    grid = Grid(level="unit", module="test")
    try:
        Scenario(id="test", grid=grid, actor="client", precondition=[], inputs=[], intent="test")
        assert False, "Scenario should require steps parameter"
    except TypeError as e:
        assert "steps" in str(e)
