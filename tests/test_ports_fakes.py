from refracto import ports
from tests.fakes import FakeApi, FakeAuth, FakeRecorder, FakeStateProbe, FakeUi


def test_fakes_satisfy_ports():
    assert isinstance(FakeAuth(), ports.Authenticator)
    assert isinstance(FakeApi(), ports.ApiDriver)
    assert isinstance(FakeStateProbe(), ports.StateProbe)
    assert isinstance(FakeUi(), ports.UiDriver)
    assert isinstance(FakeRecorder(), ports.Recorder)


def test_fake_api_echoes_configured_response():
    api = FakeApi(responses={
        ("POST", "items"): {
            "status": 200,
            "json": {"success": True, "data": {"itemId": "T1"}},
        }
    })
    spec = ports.RequestSpec(
        method="POST",
        path="items",
        body={},
        traceparent="00-abc-def-01",
    )
    r = api.send(spec, session=object())
    assert r.status == 200
    assert r.json["success"] is True
    assert r.trace_id == "abc"  # FakeApi derives trace_id from the traceparent


def test_fake_stateprobe_returns_configured_spans():
    probe = FakeStateProbe(spans_by_trace={"abc": [ports.Span("item.create", {"row_count": 3})]})
    facts = probe.observe("abc")
    assert facts.spans[0].name == "item.create"
    assert facts.spans[0].attributes["row_count"] == 3


def test_fake_stateprobe_observe_returns_independent_list():
    """`FakeStateProbe.observe()` returns a defensive copy rather than a shared list."""
    original_span = ports.Span("item.create", {"row_count": 3})
    probe = FakeStateProbe(spans_by_trace={"abc": [original_span]})

    facts1 = probe.observe("abc")
    assert len(facts1.spans) == 1

    facts1.spans.append(ports.Span("extra.span", {}))
    assert len(facts1.spans) == 2

    facts2 = probe.observe("abc")
    assert len(facts2.spans) == 1, "Fixture was mutated by the caller"
    assert facts2.spans[0].name == "item.create"
