"""Minimal-dependency regression sentinels over the frozen demo scenarios' assertion
strength.

These live at the `tests/` root, NOT under `tests/demo/`, on purpose. Everything here
is a pure declaration check: it loads a YAML scenario with the core loader and inspects
its assertions. It needs only PyYAML + `refracto.declaration.loader` — no demo app, no
browser, no OTel, no network. The `tests/demo/` directory is gated behind
`importorskip("httpx")` and the `demo` extra, so any sentinel placed there does not run
in the offline core-only CI job — exactly the job that must catch a silent loosening of
a frozen scenario.

The lesson from 2026-08-10 was that a claim-strength guard must be runnable under the
minimum dependency set. Sentinels that only run when fastapi/uvicorn/playwright/otel are
installed do not meet that bar. These do.

Each sentinel fails loudly if the corresponding scenario's strongest assertion is ever
removed or weakened back to a near-uninformative bound.
"""
from refracto.declaration.loader import load_scenario
from refracto.declaration.model import ValueRef

CREATE_PATH = "scenarios/demo_item_create.yaml"
DELETE_PATH = "scenarios/demo_item_delete.yaml"
JOB_RUN_PATH = "scenarios/demo_job_run.yaml"

# The two spans demo_job_run holds to the row count it declares in its own `inputs`.
JOB_ROW_COUNT_SPANS = ("job.create", "job.result.read")


def test_frozen_create_scenario_pins_the_exact_row_count_it_declares():
    """demo_item_create's row_count span must compare against the exact declared value.

    A `row_count > 0` assertion passes whether the product recorded 1 row or 3, so it
    cannot detect a hardcoded or off-by-one span attribute. The precise value is
    legitimate because it comes from the declaration itself (`inputs: [{rows: N}]`),
    not from test data, a seeded database, or adapter state.
    """
    scenario = load_scenario(CREATE_PATH)
    declared_rows = next(i.value for i in scenario.inputs if i.kind == "rows")

    (row_count_assertion,) = [
        a for step in scenario.steps for a in step.expect.backend_state
        if a.check == "span_attr" and a.params.get("attr") == "row_count"
    ]

    assert row_count_assertion.params["op"] == "==", (
        f"expected an exact-value comparison, got op "
        f"{row_count_assertion.params['op']!r}"
    )
    assert row_count_assertion.params["value"] == declared_rows, (
        f"asserted row_count {row_count_assertion.params['value']!r} does not match the "
        f"{declared_rows!r} rows this scenario declares in its own inputs"
    )


def test_frozen_create_scenario_anchors_frontend_assertion_to_declared_identity():
    scenario = load_scenario(CREATE_PATH)
    identity_assertions = [
        assertion
        for step in scenario.steps
        for assertion in step.expect.frontend
        if assertion.check == "object_field_equals"
    ]

    assert identity_assertions
    assert any(
        isinstance(assertion.params["id"], ValueRef)
        for assertion in identity_assertions
    )


def test_frozen_delete_scenario_pins_the_remaining_count_derived_from_its_inputs():
    """demo_item_delete's item.delete span must pin the exact remaining count, and that
    count must be derivable from the scenario's own declaration.

    `span_exists` alone passes whether the deletion removed the item or miscounted what
    was left, so it cannot detect an off-by-one in the emitted evidence.

    The asserted value must equal `existing_items - 1`: the scenario declares how many
    items pre-exist (`inputs: [{existing_items: N}]`) and deletes one, so the remaining
    count is a function of the declaration — not knowledge of the demo app's starting
    state. If the declared `existing_items` and the asserted `row_count` ever drift out
    of that relationship, this fails loudly.
    """
    scenario = load_scenario(DELETE_PATH)
    existing = next(i.value for i in scenario.inputs if i.kind == "existing_items")

    (row_count_assertion,) = [
        a for step in scenario.steps for a in step.expect.backend_state
        if a.check == "span_attr"
        and a.params.get("span") == "item.delete"
        and a.params.get("attr") == "row_count"
    ]

    assert row_count_assertion.params["op"] == "==", (
        f"expected an exact-value comparison, got op "
        f"{row_count_assertion.params['op']!r}"
    )
    assert row_count_assertion.params["value"] == int(existing) - 1, (
        f"asserted remaining row_count {row_count_assertion.params['value']!r} is not "
        f"one fewer than the {existing!r} items this scenario declares as existing; the "
        f"remaining count must be derived from the declaration, not from app state"
    )


def test_frozen_job_run_scenario_pins_the_exact_row_count_it_declares():
    """Both of demo_job_run's row-count spans must compare against the exact declared
    value.

    Without a value comparison every assertion in this scenario is a positive existence
    check — `success`, `has`, `span_exists` — and a backend that runs the flow but
    miscounts the rows satisfies all of them. Both ends are pinned on purpose: checking
    only the read side would leave a backend free to misreport the count at submission
    time.
    """
    scenario = load_scenario(JOB_RUN_PATH)
    by_span = {
        a.params["span"]: a
        for step in scenario.steps for a in step.expect.backend_state
        if a.check == "span_attr" and a.params.get("attr") == "row_count"
    }

    assert set(by_span) == set(JOB_ROW_COUNT_SPANS), (
        f"expected a row_count comparison on each of {list(JOB_ROW_COUNT_SPANS)}, "
        f"found {sorted(by_span)}"
    )
    for span_name, assertion in by_span.items():
        assert assertion.params["op"] == "==", (
            f"{span_name}: expected an exact-value comparison, got op "
            f"{assertion.params['op']!r}"
        )
        assert assertion.params["value"] == ValueRef(source="input", key="rows"), (
            f"{span_name}: row_count must reference the scenario's 'rows' input, got "
            f"{assertion.params['value']!r}"
        )


def test_frozen_job_run_scenario_pins_response_values_to_literal_input_and_binding():
    scenario = load_scenario(JOB_RUN_PATH)
    steps = {step.id: step for step in scenario.steps}

    wait_value = next(
        a.params["value"] for a in steps["wait_done"].expect.response
        if a.check == "field_equals" and a.params["field"] == "result"
    )
    count_value = next(
        a.params["value"] for a in steps["fetch_result"].expect.response
        if a.check == "field_equals" and a.params["field"] == "count"
    )
    archived_value = next(
        a.params["value"] for a in steps["archive_job"].expect.response
        if a.check == "field_equals" and a.params["field"] == "archived"
    )

    assert wait_value == "ready"
    assert count_value == ValueRef(source="input", key="rows")
    assert archived_value == ValueRef(source="bind", key="jobId")
