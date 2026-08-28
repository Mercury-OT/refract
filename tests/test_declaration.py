import pytest
from refracto.declaration.loader import load_scenario, DeclarationError
from refracto.declaration import model

def test_load_synthetic_scenario(tmp_path):
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    assert s.id == "refracto.synthetic_probe"
    assert s.grid == model.Grid(level="smoke", module="generic")
    assert s.actor == "actor1"
    assert s.precondition == [model.Ref(ref="resource.owned_by_actor")]
    assert s.inputs == [model.Input(kind="payload", value="testdata/synthetic_input.txt")]
    # v1 (legacy flat) normalizes to a single step
    assert len(s.steps) == 1
    step = s.steps[0]
    assert step.id == "main"
    assert step.request.method == "POST"
    assert step.request.path == "resource/action"
    # response block parsed into Assertion objects
    checks = [a.check for a in step.expect.response]
    assert "success" in checks and "has" in checks
    has = next(a for a in step.expect.response if a.check == "has")
    assert has.params["field"] == "taskId"
    # backend_state
    bs = [(a.check, a.params["span"]) for a in step.expect.backend_state]
    assert bs == [("span_exists", "POST /resource/action"),
                  ("span_exists", "INSERT resource.job_queue")]

def test_invalid_term_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "precondition: []\ninputs: []\nintent: t\n"
        "expect:\n  response:\n    - {check: span_attr, span: s, attr: a, op: '>', value: 0}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError):
        load_scenario(str(bad))

def test_inputs_with_multiple_keys_rejected(tmp_path):
    """Regression: inputs entry with 2+ keys raises DeclarationError, not ValueError."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "precondition: []\ninputs: [{csv: a, extra: b}]\nintent: t\n"
        "expect:\n  frontend: []\n  request: []\n  response: []\n  backend_state: []\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as exc_info:
        load_scenario(str(bad))
    assert "exactly one key" in str(exc_info.value)

def test_assertion_missing_required_param(tmp_path):
    """Regression: assertion missing required param raises DeclarationError."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "precondition: []\ninputs: []\nintent: t\n"
        "expect:\n  response:\n    - {check: has}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as exc_info:
        load_scenario(str(bad))
    assert "missing required param" in str(exc_info.value)

def test_assertion_not_mapping_or_missing_check(tmp_path):
    """Regression: assertion that is not a mapping or lacks 'check' key raises DeclarationError."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "precondition: []\ninputs: []\nintent: t\n"
        "expect:\n  response:\n    - just a string\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as exc_info:
        load_scenario(str(bad))
    assert "must be a mapping with a 'check' key" in str(exc_info.value)

# --- Load-time fail-loud hardening ------------------------------------

def test_top_level_not_mapping_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "top-level mapping" in str(e.value)

def test_unknown_top_level_key_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expct:\n  response: []\n",   # typo'd 'expect'
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "unknown top-level field" in str(e.value)

def test_empty_actor_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("scenario: x\ngrid: {level: smoke, module: m}\nactor: ''\n", encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "non-empty string" in str(e.value)

def test_unknown_expect_block_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  resposne:\n    - {check: success}\n",   # typo'd 'response'
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "unknown expect block" in str(e.value)

def test_observation_point_not_a_list_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  response: {check: success}\n",   # mapping, not a list
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "must be a list" in str(e.value)

def test_unknown_assertion_param_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  request:\n    - {check: request, method: GET, path: p, bogus: 1}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "unknown param" in str(e.value)

def test_request_async_optional_param_allowed(tmp_path):
    good = tmp_path / "good.yaml"
    good.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  request:\n    - {check: request, method: POST, path: p, async: taskId}\n",
        encoding="utf-8")
    s = load_scenario(str(good))
    # `async` is a v1 contract hint validated at the assertion level; it has no
    # RequestTemplate field, but it is still materialized into the response
    # contract as a `has` assertion (see test_v1_async_hint_materializes_as_has_assertion).
    assert s.steps[0].request.method == "POST"
    assert s.steps[0].request.path == "p"

def test_v1_async_hint_materializes_as_has_assertion(tmp_path):
    """A v1 `{check: request, ..., async: taskId}` hint must contribute `taskId` to
    the response contract (SCENARIO.md: "async — a contract hint naming a response
    field"), not be silently dropped."""
    good = tmp_path / "good.yaml"
    good.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  request:\n    - {check: request, method: POST, path: p, async: taskId}\n",
        encoding="utf-8")
    s = load_scenario(str(good))
    response_checks = [(a.check, a.params.get("field")) for a in s.steps[0].expect.response]
    assert ("has", "taskId") in response_checks

def test_v1_async_hint_does_not_duplicate_existing_has_assertion(tmp_path):
    """If the v1 scenario already declares `{check: has, field: taskId}` explicitly,
    materializing the `async` hint must not append a second, duplicate assertion."""
    good = tmp_path / "good.yaml"
    good.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n"
        "  request:\n    - {check: request, method: POST, path: p, async: taskId}\n"
        "  response:\n    - {check: has, field: taskId}\n",
        encoding="utf-8")
    s = load_scenario(str(good))
    response_checks = [(a.check, a.params.get("field")) for a in s.steps[0].expect.response]
    assert response_checks.count(("has", "taskId")) == 1

def test_span_attr_bad_op_rejected_at_load(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  backend_state:\n    - {check: span_attr, span: s, attr: a, op: '!=', value: 0}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "op" in str(e.value)

def test_count_gt_non_numeric_n_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  frontend:\n    - {check: count_gt, anchor: row, n: many}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "'n' must be a number" in str(e.value)

def test_span_attr_non_numeric_value_ordering_op_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  backend_state:\n    - {check: span_attr, span: s, attr: a, op: '>', value: lots}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "must be a number" in str(e.value)

def test_span_attr_eq_allows_string_value(tmp_path):
    good = tmp_path / "good.yaml"
    good.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  backend_state:\n    - {check: span_attr, span: s, attr: env, op: '==', value: prod}\n",
        encoding="utf-8")
    s = load_scenario(str(good))
    assert s.steps[0].expect.backend_state[0].params["value"] == "prod"

# --- Loader version dispatch -------------------------------------------------
# Decision table (8 rows):
#   1. no version, top-level expect, no steps        -> legacy v1 (one step)
#   2. version: 2, steps, no top-level expect         -> v2
#   3. no version but steps present                   -> reject "add version: 2"
#   4. version: 2 but only top-level expect            -> reject
#   5. both top-level expect and steps                 -> reject
#   6. version: 1                                      -> reject
#   7. unknown/other version                           -> reject, report supported
#   8. v1 flat with >1 request assertion                -> reject "migrate to v2 steps"

def test_v1_legacy_normalizes_to_one_step(tmp_path):
    """Row 1: no version, top-level expect, no steps -> legacy v1 (one step)."""
    good = tmp_path / "good.yaml"
    good.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n"
        "  response:\n    - {check: success}\n"
        "  request:\n    - {check: request, method: POST, path: p}\n",
        encoding="utf-8")
    s = load_scenario(str(good))
    assert len(s.steps) == 1
    assert s.steps[0].id == "main"
    assert s.steps[0].request == model.RequestTemplate(method="POST", path="p")
    assert s.steps[0].bind == []
    assert s.steps[0].poll is None

def test_v2_parses_into_steps(tmp_path):
    """Row 2: version: 2, steps, no top-level expect -> v2."""
    good = tmp_path / "good.yaml"
    good.write_text(
        "version: 2\n"
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: items}\n"
        "    expect:\n"
        "      response:\n        - {check: success}\n        - {check: has, field: itemId}\n"
        "      backend_state:\n        - {check: span_exists, span: item.create}\n"
        "  - id: fetch\n"
        "    request: {method: GET, path: 'items/{itemId}'}\n"
        "    bind:\n      itemId: {from: create, field: itemId}\n"
        "    poll:\n      on_timeout: SKIP\n"
        "    expect:\n"
        "      response:\n        - {check: has, field: result}\n",
        encoding="utf-8")
    s = load_scenario(str(good))
    assert len(s.steps) == 2
    create, fetch = s.steps
    assert create.id == "create"
    assert create.request == model.RequestTemplate(method="POST", path="items")
    assert [a.check for a in create.expect.response] == ["success", "has"]
    assert [a.params["span"] for a in create.expect.backend_state] == ["item.create"]
    assert create.bind == []
    assert create.poll is None
    assert fetch.id == "fetch"
    assert fetch.request == model.RequestTemplate(method="GET", path="items/{itemId}")
    assert fetch.bind == [model.Binding(placeholder="itemId", from_step="create", field="itemId")]
    assert fetch.poll == model.PollPolicy(on_timeout="SKIP")

def test_v2_step_expect_rejects_request_subblock(tmp_path):
    """A step's expect has no `request` sub-block — request is a step field, not an expect point."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\n"
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: GET, path: p}\n"
        "    expect:\n"
        "      request:\n        - {check: request, method: GET, path: p}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "unknown" in str(e.value) and "expect block" in str(e.value)

def test_no_version_with_steps_rejected(tmp_path):
    """Row 3: no version but steps present -> reject 'add version: 2'."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n  - id: s1\n    request: {method: GET, path: p}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "version: 2" in str(e.value)

def test_version_2_with_only_expect_rejected(tmp_path):
    """Row 4: version: 2 but only top-level expect (no steps) -> reject."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\n"
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  response:\n    - {check: success}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "steps" in str(e.value)

def test_both_expect_and_steps_rejected(tmp_path):
    """Row 5: both top-level expect and steps -> reject."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\n"
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  response:\n    - {check: success}\n"
        "steps:\n  - id: s1\n    request: {method: GET, path: p}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "expect" in str(e.value) and "steps" in str(e.value)

def test_version_1_rejected(tmp_path):
    """Row 6: version: 1 -> reject (v1 files carry no version field)."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 1\n"
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  response:\n    - {check: success}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "version: 1" in str(e.value)

def test_unknown_version_rejected(tmp_path):
    """Row 7: unknown/other version -> reject, report supported versions."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 3\n"
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "supported version" in str(e.value)

def test_v1_flat_with_multiple_request_assertions_rejected(tmp_path):
    """Row 8: v1 flat with >1 request assertion -> reject 'migrate to v2 steps'."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  request:\n"
        "    - {check: request, method: POST, path: p1}\n"
        "    - {check: request, method: GET, path: p2}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "migrate to v2 steps" in str(e.value)

# --- Fail-loud step validation ----------------------------------
# ids; prior+declared binds; placeholders (path whole-segment, body exact-match,
# no key placeholders, malformed); poll enum + GET-only.

def test_step_id_missing_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n  - request: {method: GET, path: p}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "id" in str(e.value)

def test_step_id_empty_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n  - id: ''\n    request: {method: GET, path: p}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "id" in str(e.value)

def test_step_id_duplicate_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n    request: {method: GET, path: p1}\n"
        "  - id: s1\n    request: {method: GET, path: p2}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "duplicat" in str(e.value)

def test_step_missing_request_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n  - id: s1\n    expect:\n      response:\n        - {check: success}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "request" in str(e.value)

def test_bind_from_later_step_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: GET, path: 'jobs/{jobId}'}\n"
        "    bind:\n      jobId: {from: s2, field: jobId}\n"
        "  - id: s2\n"
        "    request: {method: POST, path: jobs}\n"
        "    expect:\n      response:\n        - {check: has, field: jobId}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "prior step" in str(e.value)

def test_bind_from_same_step_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: GET, path: 'jobs/{jobId}'}\n"
        "    bind:\n      jobId: {from: s1, field: jobId}\n"
        "    expect:\n      response:\n        - {check: has, field: jobId}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "prior step" in str(e.value)

def test_bind_from_unknown_step_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: GET, path: 'jobs/{jobId}'}\n"
        "    bind:\n      jobId: {from: ghost, field: jobId}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "prior step" in str(e.value)

def test_bind_field_not_declared_has_rejected(tmp_path):
    """The source step declares `success` and `has: orderId`, but not `has: jobId` —
    binding `jobId` from it must fail; `success` alone does not guarantee a field."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: jobs}\n"
        "    expect:\n      response:\n        - {check: success}\n        - {check: has, field: orderId}\n"
        "  - id: s2\n"
        "    request: {method: GET, path: 'jobs/{jobId}'}\n"
        "    bind:\n      jobId: {from: create, field: jobId}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "not guaranteed by source step" in str(e.value)

def test_unbound_placeholder_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n  - id: s1\n    request: {method: GET, path: 'jobs/{jobId}'}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "unbound placeholder" in str(e.value)

def test_instring_body_placeholder_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: POST, path: jobs, body: {note: 'job-{jobId}'}}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "in-string" in str(e.value)

def test_placeholder_in_body_key_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: POST, path: jobs, body: {'{jobId}': 1}}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "body" in str(e.value) and "key" in str(e.value)

def test_malformed_placeholder_double_brace_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: POST, path: jobs, body: {note: '{{x}}'}}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "malformed placeholder" in str(e.value)

def test_malformed_placeholder_empty_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: POST, path: jobs, body: {note: '{}'}}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "malformed placeholder" in str(e.value)

def test_declared_bind_never_used_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: jobs}\n"
        "    expect:\n      response:\n        - {check: has, field: jobId}\n"
        "  - id: s2\n"
        "    request: {method: GET, path: jobs}\n"
        "    bind:\n      jobId: {from: create, field: jobId}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "never used" in str(e.value)

def test_poll_on_timeout_invalid_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: GET, path: jobs}\n"
        "    poll:\n      on_timeout: RETRY\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "on_timeout" in str(e.value)

def test_poll_target_method_not_get_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: POST, path: jobs}\n"
        "    poll:\n      on_timeout: FAIL\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "poll" in str(e.value) and "GET" in str(e.value)

def test_poll_with_no_expect_response_rejected(tmp_path):
    """A poll step with no expect.response has no stop condition — with an empty
    list, all([]) is vacuously True, so the poll would 'pass' after one request.
    This must be rejected at load time."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: GET, path: jobs}\n"
        "    poll:\n      on_timeout: FAIL\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "stop condition" in str(e.value) and "expect.response" in str(e.value)

def test_poll_with_empty_expect_response_rejected(tmp_path):
    """Same as above but with an explicit empty `expect.response: []` list —
    still no stop condition, still rejected."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: GET, path: jobs}\n"
        "    poll:\n      on_timeout: FAIL\n"
        "    expect:\n      response: []\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "stop condition" in str(e.value) and "expect.response" in str(e.value)

def test_path_placeholder_not_whole_segment_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: GET, path: 'jobs/job-{jobId}/status'}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError, match="whole segment"):
        load_scenario(str(bad))

def test_path_placeholder_trailing_suffix_not_whole_segment_rejected(tmp_path):
    """Spec example: `jobs/{jobId}.json` — a placeholder with a trailing literal
    suffix does not occupy a whole segment."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: GET, path: 'jobs/{jobId}.json'}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError, match="whole segment"):
        load_scenario(str(bad))

def test_path_placeholder_doubled_brace_not_whole_segment_rejected(tmp_path):
    """Spec example: `jobs/{{jobId}}/status` — a doubled brace in a path segment
    is not a legal whole-segment placeholder."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: GET, path: 'jobs/{{jobId}}/status'}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError, match="whole segment"):
        load_scenario(str(bad))

def test_request_method_missing_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {path: jobs}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError, match="non-empty string"):
        load_scenario(str(bad))

def test_request_method_null_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: null, path: jobs}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError, match="non-empty string"):
        load_scenario(str(bad))

def test_request_method_whitespace_only_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: '   ', path: jobs}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError, match="non-empty string"):
        load_scenario(str(bad))

def test_c1_canonical_multistep_scenario_loads(tmp_path):
    """Positive: create -> bind jobId into BOTH path and body, GET poll with
    on_timeout FAIL, source field declared via `has`; method normalized `get`->`GET`."""
    good = tmp_path / "good.yaml"
    good.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: jobs}\n"
        "    expect:\n"
        "      response:\n        - {check: success}\n        - {check: has, field: jobId}\n"
        "  - id: poll_status\n"
        "    request: {method: get, path: 'jobs/{jobId}/status', body: {jobId: '{jobId}'}}\n"
        "    bind:\n      jobId: {from: create, field: jobId}\n"
        "    poll:\n      on_timeout: FAIL\n"
        "    expect:\n"
        "      response:\n        - {check: has, field: status}\n",
        encoding="utf-8")
    s = load_scenario(str(good))
    assert len(s.steps) == 2
    create, poll_status = s.steps
    assert create.request.method == "POST"
    assert poll_status.request.method == "GET"   # normalized from 'get'
    assert poll_status.bind == [model.Binding(placeholder="jobId", from_step="create", field="jobId")]
    assert poll_status.poll == model.PollPolicy(on_timeout="FAIL")

def test_v1_with_zero_request_assertions_leaves_request_none(tmp_path):
    """A v1 flat scenario with no `expect.request` assertion at all is permitted:
    the normalized step's `request` stays None (the loader never invents one)."""
    good = tmp_path / "good.yaml"
    good.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  response:\n    - {check: success}\n",
        encoding="utf-8")
    s = load_scenario(str(good))
    assert len(s.steps) == 1
    assert s.steps[0].id == "main"
    assert s.steps[0].request is None
    assert [a.check for a in s.steps[0].expect.response] == ["success"]

# --- Reject unknown nested keys --------------------------------

def test_request_unknown_key_rejected(tmp_path):
    """A typo'd request key (`boddy` instead of `body`) must be rejected, not
    silently ignored."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: POST, path: jobs, boddy: {a: 1}}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "unknown" in str(e.value) and "boddy" in str(e.value)

def test_step_unknown_key_rejected(tmp_path):
    """A step with an extra top-level key (`timeout`) not in the step grammar
    must be rejected."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: GET, path: jobs}\n"
        "    timeout: 10\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "unknown" in str(e.value) and "timeout" in str(e.value)

def test_bind_unknown_key_rejected(tmp_path):
    """A bind spec with an extra key beyond `from`/`field` must be rejected."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: jobs}\n"
        "    expect:\n      response:\n        - {check: has, field: jobId}\n"
        "  - id: s2\n"
        "    request: {method: GET, path: 'jobs/{jobId}'}\n"
        "    bind:\n      jobId: {from: create, field: jobId, extra: 1}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "unknown" in str(e.value) and "extra" in str(e.value)

def test_poll_unknown_key_rejected(tmp_path):
    """A poll block with an extra key beyond `on_timeout` must be rejected."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: s1\n"
        "    request: {method: GET, path: jobs}\n"
        "    poll:\n      on_timeout: FAIL\n      extra: 1\n"
        "    expect:\n      response:\n        - {check: success}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "unknown" in str(e.value) and "extra" in str(e.value)

def test_grid_unknown_key_rejected(tmp_path):
    """A grid block with an extra key beyond `level`/`module` must be rejected —
    applies to both v1 and v2 forms since grid is parsed on a shared path."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m, extra: x}\nactor: a\n"
        "expect:\n  response:\n    - {check: success}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "unknown" in str(e.value) and "extra" in str(e.value)

def test_precondition_unknown_key_rejected(tmp_path):
    """A precondition entry with an extra key beyond `ref` must be rejected —
    applies to both v1 and v2 forms since precondition is parsed on a shared path."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "precondition: [{ref: resource.owned_by_actor, extra: x}]\n"
        "expect:\n  response:\n    - {check: success}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "unknown" in str(e.value) and "extra" in str(e.value)

# --- C-2 Step 1: span_attr.value as a data-only reference to a bound value ---

def test_span_attr_from_bind_reference_parses(tmp_path):
    """A `span_attr.value: {from_bind: X}` where X is declared in this step's
    `bind` parses into a `model.ValueRef(source='bind', key='X')`."""
    good = tmp_path / "good.yaml"
    good.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: items}\n"
        "    expect:\n      response:\n        - {check: has, field: itemId}\n"
        "  - id: update\n"
        "    request: {method: PUT, path: 'items/{itemId}'}\n"
        "    bind:\n      itemId: {from: create, field: itemId}\n"
        "    expect:\n"
        "      response:\n        - {check: success}\n"
        "      backend_state:\n"
        "        - {check: span_attr, span: item.update, attr: entity_id, op: '==', "
        "value: {from_bind: itemId}}\n",
        encoding="utf-8")
    s = load_scenario(str(good))
    update = s.steps[1]
    span_attr = next(a for a in update.expect.backend_state if a.check == "span_attr")
    assert span_attr.params["value"] == model.ValueRef(source="bind", key="itemId")


def test_span_attr_from_bind_only_use_is_not_flagged_unused(tmp_path):
    """A bound placeholder used only inside `span_attr.value` (never in the
    request path/body) is a legal, non-'unused' pattern."""
    good = tmp_path / "good.yaml"
    good.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: items}\n"
        "    expect:\n      response:\n        - {check: has, field: itemId}\n"
        "  - id: update\n"
        "    request: {method: PUT, path: items}\n"
        "    bind:\n      itemId: {from: create, field: itemId}\n"
        "    expect:\n"
        "      backend_state:\n"
        "        - {check: span_attr, span: item.update, attr: entity_id, op: '==', "
        "value: {from_bind: itemId}}\n",
        encoding="utf-8")
    s = load_scenario(str(good))
    assert s.steps[1].bind == [model.Binding(placeholder="itemId", from_step="create", field="itemId")]


def test_span_attr_from_bind_ordering_op_rejected(tmp_path):
    """A value reference may only be compared with `==`; ordering operators
    against a reference are rejected at load time (Step 1 boundary)."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: items}\n"
        "    expect:\n      response:\n        - {check: has, field: itemId}\n"
        "  - id: update\n"
        "    request: {method: PUT, path: 'items/{itemId}'}\n"
        "    bind:\n      itemId: {from: create, field: itemId}\n"
        "    expect:\n"
        "      backend_state:\n"
        "        - {check: span_attr, span: item.update, attr: entity_id, op: '>', "
        "value: {from_bind: itemId}}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "value reference requires op" in str(e.value)


def test_span_attr_from_bind_unknown_placeholder_rejected(tmp_path):
    """`from_bind` must reference a placeholder declared in this step's own
    `bind` — not merely any name that happens to exist elsewhere."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: items}\n"
        "    expect:\n      response:\n        - {check: has, field: itemId}\n"
        "  - id: update\n"
        "    request: {method: PUT, path: items}\n"
        "    expect:\n"
        "      backend_state:\n"
        "        - {check: span_attr, span: item.update, attr: entity_id, op: '==', "
        "value: {from_bind: itemId}}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "must reference a placeholder declared" in str(e.value)


def test_span_attr_from_bind_malformed_multikey_rejected(tmp_path):
    """A value-reference mapping with more than one key is malformed — it must
    not silently pick one and ignore the other."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: items}\n"
        "    expect:\n      response:\n        - {check: has, field: itemId}\n"
        "  - id: update\n"
        "    request: {method: PUT, path: 'items/{itemId}'}\n"
        "    bind:\n      itemId: {from: create, field: itemId}\n"
        "    expect:\n"
        "      backend_state:\n"
        "        - {check: span_attr, span: item.update, attr: entity_id, op: '==', "
        "value: {from_bind: itemId, extra: 1}}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "single-key mapping" in str(e.value)


def test_span_attr_from_bind_empty_key_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: items}\n"
        "    expect:\n      response:\n        - {check: has, field: itemId}\n"
        "  - id: update\n"
        "    request: {method: PUT, path: 'items/{itemId}'}\n"
        "    bind:\n      itemId: {from: create, field: itemId}\n"
        "    expect:\n"
        "      backend_state:\n"
        "        - {check: span_attr, span: item.update, attr: entity_id, op: '==', "
        "value: {from_bind: ''}}\n",
        encoding="utf-8")
    with pytest.raises(DeclarationError) as e:
        load_scenario(str(bad))
    assert "non-empty key" in str(e.value)


# --- Response value assertions ---------------------------------------------

def test_field_equals_literal_and_from_input_parse(tmp_path):
    good = tmp_path / "good.yaml"
    good.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "inputs: [{rows: 3}]\n"
        "expect:\n  response:\n"
        "    - {check: field_equals, field: state, value: ready}\n"
        "    - {check: field_equals, field: count, value: {from_input: rows}}\n",
        encoding="utf-8")

    scenario = load_scenario(str(good))

    state, count = scenario.steps[0].expect.response
    assert state.params == {"field": "state", "value": "ready"}
    assert count.params == {
        "field": "count",
        "value": model.ValueRef(source="input", key="rows"),
    }


def test_field_equals_from_bind_is_a_valid_bind_use_and_guarantees_source_field(tmp_path):
    """`field_equals` both proves presence for a later bind and may be the only
    use of that binding in its consuming step."""
    good = tmp_path / "good.yaml"
    good.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: items}\n"
        "    expect:\n      response:\n"
        "        - {check: field_equals, field: itemId, value: 42}\n"
        "  - id: archive\n"
        "    request: {method: POST, path: archives}\n"
        "    bind: {itemId: {from: create, field: itemId}}\n"
        "    expect:\n      response:\n"
        "        - {check: field_equals, field: archived, value: {from_bind: itemId}}\n",
        encoding="utf-8")

    scenario = load_scenario(str(good))

    assertion = scenario.steps[1].expect.response[0]
    assert assertion.params["value"] == model.ValueRef(source="bind", key="itemId")


@pytest.mark.parametrize("value_yaml", ["{unexpected: value}", "[one, two]"])
def test_field_equals_rejects_non_scalar_literal(tmp_path, value_yaml):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  response:\n"
        f"    - {{check: field_equals, field: state, value: {value_yaml}}}\n",
        encoding="utf-8")

    with pytest.raises(DeclarationError) as exc_info:
        load_scenario(str(bad))
    assert "scalar or a value reference" in str(exc_info.value)


def test_field_equals_from_input_must_name_one_declared_input(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "inputs: [{rows: 3}]\n"
        "expect:\n  response:\n"
        "    - {check: field_equals, field: count, value: {from_input: missing}}\n",
        encoding="utf-8")

    with pytest.raises(DeclarationError) as exc_info:
        load_scenario(str(bad))
    assert "must name exactly one declared scenario input" in str(exc_info.value)


def test_field_equals_from_bind_must_name_current_step_binding(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: get\n"
        "    request: {method: GET, path: items}\n"
        "    expect:\n      response:\n"
        "        - {check: field_equals, field: itemId, value: {from_bind: itemId}}\n",
        encoding="utf-8")

    with pytest.raises(DeclarationError) as exc_info:
        load_scenario(str(bad))
    assert "must reference a placeholder declared" in str(exc_info.value)


def test_field_equals_duplicate_constraint_for_field_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  response:\n"
        "    - {check: field_equals, field: state, value: ready}\n"
        "    - {check: field_equals, field: state, value: done}\n",
        encoding="utf-8")

    with pytest.raises(DeclarationError) as exc_info:
        load_scenario(str(bad))
    assert "duplicate field_equals" in str(exc_info.value)


# --- Frontend object identity assertions -----------------------------------

def test_object_field_equals_from_input_references_parse(tmp_path):
    good = tmp_path / "good.yaml"
    good.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "inputs: [{item_id: '42'}, {expected_name: target}]\n"
        "expect:\n  frontend:\n"
        "    - {check: object_field_equals, anchor: item_row, "
        "id: {from_input: item_id}, field: name, "
        "value: {from_input: expected_name}}\n",
        encoding="utf-8")

    scenario = load_scenario(str(good))

    assertion = scenario.steps[0].expect.frontend[0]
    assert assertion.params["id"] == model.ValueRef(source="input", key="item_id")
    assert assertion.params["value"] == model.ValueRef(source="input", key="expected_name")


def test_object_field_equals_from_bind_parses_and_counts_as_bind_use(tmp_path):
    good = tmp_path / "good.yaml"
    good.write_text(
        "version: 2\nscenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: items}\n"
        "    expect:\n      response:\n        - {check: has, field: itemId}\n"
        "  - id: inspect\n"
        "    request: {method: GET, path: items}\n"
        "    bind: {itemId: {from: create, field: itemId}}\n"
        "    expect:\n      frontend:\n"
        "        - {check: object_field_equals, anchor: item_row, "
        "id: {from_bind: itemId}, field: state, value: ready}\n",
        encoding="utf-8")

    scenario = load_scenario(str(good))

    assertion = scenario.steps[1].expect.frontend[0]
    assert assertion.params["id"] == model.ValueRef(source="bind", key="itemId")


def test_object_field_equals_literal_id_rejected_at_load(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "expect:\n  frontend:\n"
        "    - {check: object_field_equals, anchor: item_row, "
        "id: '42', field: name, value: target}\n",
        encoding="utf-8")

    with pytest.raises(DeclarationError) as exc_info:
        load_scenario(str(bad))
    assert "'id' must be a value reference" in str(exc_info.value)


@pytest.mark.parametrize("param", ["anchor", "field"])
def test_object_field_equals_requires_nonempty_names(tmp_path, param):
    values = {"anchor": "item_row", "field": "name"}
    values[param] = ""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "inputs: [{item_id: '42'}]\n"
        "expect:\n  frontend:\n"
        "    - {check: object_field_equals, "
        f"anchor: '{values['anchor']}', id: {{from_input: item_id}}, "
        f"field: '{values['field']}', value: target}}\n",
        encoding="utf-8")

    with pytest.raises(DeclarationError) as exc_info:
        load_scenario(str(bad))
    assert f"'{param}' must be a non-empty string" in str(exc_info.value)


def test_object_field_equals_rejects_non_scalar_value(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "inputs: [{item_id: '42'}]\n"
        "expect:\n  frontend:\n"
        "    - {check: object_field_equals, anchor: item_row, "
        "id: {from_input: item_id}, field: name, value: [target]}\n",
        encoding="utf-8")

    with pytest.raises(DeclarationError) as exc_info:
        load_scenario(str(bad))
    assert "scalar or a value reference" in str(exc_info.value)
