"""Offline controls for the reviewed page declaration; none sends a target request."""

import copy

import pytest
import yaml

from examples.mattermost_api.channel_message import (
    CANONICAL, UNKNOWN, bind_declaration, classify, load_scenario, page_observations,
)
from refracto.declaration.run_values import bind_run_values
from refracto.projection.frontend import _eval_frontend


BINDINGS = {"channel_path": "/team/channels/private", "channel_id": "channel", "member_id": "member"}


def test_binding_changes_only_the_three_environment_slots(tmp_path):
    bound = bind_declaration(CANONICAL, BINDINGS, tmp_path)
    expected = yaml.safe_load(CANONICAL.read_bytes())
    expected["parameters"].update(BINDINGS)
    assert yaml.safe_load(bound.read_bytes()) == expected
    assert (tmp_path / "reviewed.yaml").read_bytes() == CANONICAL.read_bytes()


def test_changed_status_cannot_be_bound_as_the_approved_scenario(tmp_path):
    altered = tmp_path / "changed.yaml"
    altered.write_text(CANONICAL.read_text().replace("value: 201", "value: 200"))
    with pytest.raises(ValueError, match="approved four steps"):
        bind_declaration(altered, BINDINGS, tmp_path)
    assert not (tmp_path / "bound.yaml").exists()


@pytest.mark.parametrize(("case", "native", "business"), [
    ("baseline", "PASSED", "PASS"),
    ("same-text-different-id", "FAILED", "FAIL"),
    ("duplicate-id", "FAILED", "FAIL"),
    ("wrong-text", "FAILED", "FAIL"),
    ("anonymous", "FAILED", UNKNOWN),
    ("incomplete", "PASSED", UNKNOWN),
    ("old-document", "PASSED", UNKNOWN),
    ("reused-loader-id", "PASSED", UNKNOWN),
    ("different-context", "PASSED", UNKNOWN),
])
def test_reread_requires_identified_complete_fresh_page(tmp_path, case, native, business):
    bound, _ = bind_run_values(load_scenario(bind_declaration(CANONICAL, BINDINGS, tmp_path)))
    reread = bound.steps[-1]
    expected_text = next(item.value for item in bound.inputs if item.kind == "message")
    returned_id = "new-post"
    observed_id = "older-post" if case == "same-text-different-id" else returned_id
    text = "different" if case == "wrong-text" else expected_text
    item = {"id": observed_id, "fields": {"post_id": observed_id, "message": text}}
    posts = {"identified": [item], "anonymous": []}
    if case == "duplicate-id":
        posts["identified"].append(copy.deepcopy(item))
    if case == "anonymous":
        posts["anonymous"].append({"fields": {"message": "unrelated private text"}})
    rendered = {"channel.view": {"anonymous": [{"fields": {"path": BINDINGS["channel_path"]}}]},
                "channel.posts": posts}
    source, = reread.bind
    assert (source.from_step, source.field) == ("send", "id")
    bindings = {source.placeholder: returned_id}
    checks = [_eval_frontend(check, rendered, bindings, bound.inputs) for check in reread.expect.frontend]
    status = "PASSED" if all(check.ok for check in checks) else "FAILED"
    assert status == native
    observations = page_observations({"enter_channel": {
        "context_id": "ctx", "frame_id": "frame", "document_after": "initial",
    }, "reopen_channel": {
        "rendered": rendered, "new_document": case != "old-document", "timeline_complete": case != "incomplete",
        "context_id": "other" if case == "different-context" else "ctx", "frame_id": "frame",
        "document_before": "initial", "document_after": "initial" if case == "reused-loader-id" else "fresh",
    }})
    assert "unrelated private text" not in repr(observations)
    steps = {"send": {"status": "PASSED"}, "reopen_channel": {"status": status}}
    records = [{"step": "send", "method": "POST", "actual_path": "/api/v4/posts",
                "response": {"id": returned_id, "message": expected_text}}]
    assert classify(steps, observations, records)["reopen_channel"] == business


def test_unattributed_post_is_not_a_send_pass():
    steps = {"send": {"status": "ERROR"}}
    observations = {"send": {"associated_count": 0}}
    assert classify(steps, observations, [])["send"] == UNKNOWN
