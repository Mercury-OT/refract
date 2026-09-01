import dataclasses

from refracto.report import (
    BLOCKED,
    CheckResult,
    DEGRADED,
    DomainResult,
    EMPTY,
    ERROR,
    FAILED,
    NOT_SELECTED,
    PASSED,
    RunReport,
    SKIPPED,
    StepResult,
)


def _ok(step=""):
    return CheckResult("p", "c", True, step=step)


def _bad(step=""):
    return CheckResult("p", "c", False, step=step)


def test_domain_passed_when_step_passed_with_ok_checks():
    step = StepResult("s1", PASSED, checks=[_ok("s1")])
    d = DomainResult("backend", steps=[step])
    assert d.status == PASSED and d.passed


def test_domain_failed_when_step_failed():
    step = StepResult("s1", FAILED, checks=[_bad("s1")])
    d = DomainResult("backend", steps=[step])
    assert d.status == FAILED and not d.passed


def test_domain_degraded_when_a_step_skipped():
    step = StepResult("s1", SKIPPED)
    d = DomainResult("backend", steps=[step])
    assert d.status == DEGRADED and d.passed


def test_domain_degraded_when_step_has_skipped_notes_but_ok_checks():
    step = StepResult("s1", PASSED, checks=[_ok("s1")], skipped=["s1 span_exists — no probe"])
    d = DomainResult("backend", steps=[step])
    assert d.status == DEGRADED and d.passed


def test_domain_empty_when_no_steps():
    d = DomainResult("frontend", steps=[])
    assert d.status == EMPTY and not d.passed


def test_domain_empty_when_step_passed_but_asserts_nothing():
    step = StepResult("s1", PASSED, checks=[])
    d = DomainResult("backend", steps=[step])
    assert d.status == EMPTY and not d.passed


def test_domain_degraded_when_step_has_only_skipped_no_checks():
    step = StepResult("s1", PASSED, checks=[], skipped=["s1 span_exists — no probe"])
    d = DomainResult("backend", steps=[step])
    assert d.status == DEGRADED and d.passed


def test_domain_checks_property_aggregates_across_steps():
    s1 = StepResult("s1", PASSED, checks=[_ok("s1")])
    s2 = StepResult("s2", FAILED, checks=[_bad("s2")])
    d = DomainResult("backend", steps=[s1, s2])
    assert d.checks == [s1.checks[0], s2.checks[0]]


def test_report_not_selected_is_not_passed():
    r = RunReport("x", selected=False)
    assert r.status == NOT_SELECTED and not r.passed


def test_report_empty_when_no_domains_but_selected():
    r = RunReport("x", domains=[])
    assert r.status == EMPTY and not r.passed


def test_report_failed_when_any_domain_failed():
    ok_step = StepResult("s1", PASSED, checks=[_ok("s1")])
    bad_step = StepResult("s1", FAILED, checks=[_bad("s1")])
    r = RunReport("x", domains=[DomainResult("b", steps=[ok_step]), DomainResult("f", steps=[bad_step])])
    assert r.status == FAILED and not r.passed


def test_report_degraded_when_domain_has_only_domain_level_skipped_no_steps():
    d = DomainResult("b", steps=[], skipped=["backend_state span_exists — no probe"])
    r = RunReport("x", domains=[d])
    assert r.status == DEGRADED and r.passed


def test_report_passed_when_all_domains_passed():
    s1 = StepResult("s1", PASSED, checks=[_ok("s1")])
    s2 = StepResult("s1", PASSED, checks=[_ok("s1")])
    r = RunReport("x", domains=[DomainResult("b", steps=[s1]), DomainResult("f", steps=[s2])])
    assert r.status == PASSED and r.passed


def test_localize_returns_projection_step_point_check_detail_5tuple():
    bad = CheckResult("resp", "status_eq", False, detail="expected 200 got 500", step="create_item")
    step = StepResult("create_item", FAILED, checks=[bad])
    r = RunReport("x", domains=[DomainResult("backend", steps=[step])])
    assert r.localize() == [("backend", "create_item", "resp", "status_eq", "expected 200 got 500")]


def test_degradations_flattens_domain_and_step_skipped_reasons():
    step = StepResult(
        "create_item",
        PASSED,
        checks=[_ok("create_item")],
        skipped=["span_exists — no StateProbe"],
    )
    domain = DomainResult(
        "backend",
        steps=[step],
        skipped=["projection capability unavailable"],
    )
    report = RunReport("x", domains=[domain])

    assert report.degradations() == [
        ("backend", None, "projection capability unavailable"),
        ("backend", "create_item", "span_exists — no StateProbe"),
    ]


def test_resolved_bindings_default_is_private_per_step_and_positional_api_is_unchanged():
    first = StepResult("first", PASSED)
    second = StepResult("second", PASSED)
    first.resolved_bindings["item_id"] = 7

    assert second.resolved_bindings == {}

    positional = StepResult("step", PASSED, [], [], 2, "trace", "detail")
    assert positional.attempts == 2
    assert positional.trace_id == "trace"
    assert positional.detail == "detail"
    assert positional.resolved_bindings == {}


def test_resolved_bindings_is_sensitive_kw_only_non_comparing_and_hidden_from_repr():
    sentinel = "sensitive-value-that-must-not-appear"
    with_binding = StepResult(
        "step",
        PASSED,
        resolved_bindings={"credential": sentinel},
    )
    without_binding = StepResult("step", PASSED)
    report = RunReport(
        "scenario",
        domains=[DomainResult("backend", steps=[with_binding])],
    )
    resolved_field = next(
        item for item in dataclasses.fields(StepResult)
        if item.name == "resolved_bindings"
    )

    assert with_binding == without_binding
    assert "resolved_bindings" not in StepResult.__match_args__
    assert resolved_field.metadata["sensitive"] is True
    assert sentinel not in repr(with_binding)
    assert sentinel not in repr(report)
    assert dataclasses.asdict(with_binding)["resolved_bindings"] == {
        "credential": sentinel,
    }


def test_resolved_bindings_does_not_change_status_localization_or_degradations():
    bad = CheckResult(
        "response",
        "field_equals",
        False,
        detail="wrong object",
        step="update",
    )
    step = StepResult(
        "update",
        FAILED,
        checks=[bad],
        skipped=["span_exists — no StateProbe"],
        resolved_bindings={"item_id": 42},
    )
    domain = DomainResult("backend", steps=[step])
    report = RunReport("scenario", domains=[domain])

    assert domain.status == FAILED
    assert report.status == FAILED
    assert report.localize() == [
        ("backend", "update", "response", "field_equals", "wrong object"),
    ]
    assert report.degradations() == [
        ("backend", "update", "span_exists — no StateProbe"),
    ]
