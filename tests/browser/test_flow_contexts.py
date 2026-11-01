"""Two scheduled Scenarios share actual Chromium pages and mapped users."""
import pytest

from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_flow
from tests.browser.test_anonymous_users import Accounts, ObservedUi, interaction, send
from tests.browser.test_support import fixture
from tests.fakes import FakeNormalizer
from tests.test_flow_ui import flow_path, scenario


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_flow_keeps_real_dom_sessions_and_ordered_mock_queue_across_scenarios(http_peer, tmp_path, projection):
    path = flow_path(tmp_path, [
        scenario("browser.prepare_pages", interaction("creator", "owner value") +
                 interaction("reader", "reader value"), users=["creator", "reader"],
                 write_flow={"owner_reply": {"from_step": "creator_send", "response_field": "reply"}}),
        scenario("browser.use_pages", [send("owner_return", "operator", {"from_flow": "owner_reply"}),
                                       send("reader_return", "guest", "reader value")],
                 users=["operator", "guest"]),
    ], users=["owner", "anonymous"], mappings=[
        {"creator": "owner", "reader": "anonymous"},
        {"operator": "owner", "guest": "anonymous"},
    ], parameters={"owner_reply": {}})
    source_bytes = {source: source.read_bytes() for source in tmp_path.iterdir()}
    ui, auth = ObservedUi(http_peer.base_url), Accounts(http_peer.base_url)
    adapters = Adapters(auth, None, None, ui, InMemoryRecorder, None, FakeNormalizer())
    plan = [fixture("owner-first", reply="owner value"), fixture("reader-first", reply="reader value"),
            fixture("owner-return", reply="owner value"), fixture("reader-return", reply="reader value")]
    report = run_flow(path, adapters, projections=(projection,),
                      mock_plan=plan if projection == "frontend" else None)
    assert report.status == "PASSED", report.localize()
    assert all(source.read_bytes() == content for source, content in source_bytes.items())
    assert auth.identified == auth.acquired == ["owner"]
    assert ui.actions == ["open", "fill", "click", "open", "fill", "click", "click", "click"]
    assert len(ui.opened) == len(ui.closed) == 2
    assert ui.observed[0]["context"] is ui.observed[6]["context"]
    assert ui.observed[3]["context"] is ui.observed[7]["context"]
    assert ui.opened[0] is not ui.opened[1]
    assert ui.observed[0]["storage"] == ui.observed[6]["storage"]
    assert ui.observed[3]["storage"] is ui.observed[7]["storage"] is None
    assert all(context.closed and context.page.is_closed() for context in ui.closed)
    assert len({permit.execution_id for permit in ui.permits}) == 1
    assert len({permit.action_id for permit in ui.permits}) == 8
    assert [(step.user, step.session_generation) for step in report.domains[0].steps] == [
        ("owner", 1), ("owner", 1), ("owner", 1), (None, 0), (None, 0), (None, 0),
        ("owner", 1), (None, 0)]
    if projection == "frontend":
        assert http_peer.api_requests == []
        assert len({id(context.mock_queue) for context in ui.opened}) == 1
        assert [item["fixture_id"] for item in report.domains[0].mock_consumption] == [
            "owner-first", "reader-first", "owner-return", "reader-return"]
    else:
        assert [request["body"] for request in http_peer.api_requests] == [
            {"value": "owner value"}, {"value": "reader value"},
            {"value": "owner value"}, {"value": "reader value"}]
        recordings = report.domains[0].provider_recordings
        assert [(item.user, item.session_generation) for item in recordings] == [
            ("owner", 1), (None, 0), ("owner", 1), (None, 0)]
        assert len({item.request_id for item in recordings}) == len({item.trace_id for item in recordings}) == 4
