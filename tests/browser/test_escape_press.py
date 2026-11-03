"""Real Escape delivery, focus ownership and page-only transport boundaries."""
from dataclasses import asdict, replace
import time

import pytest

from refracto import ports
from tests.browser.test_enter_press import focus, lab, permit


def escape(support, context, *, selector="#entry"):
    return support.perform(context, replace(permit(mode=context.mode), key="Escape"),
                           selector=selector).evidence


@pytest.mark.parametrize("input_type", ["text", "search"])
@pytest.mark.parametrize("handler", ["listener", "property"])
def test_trusted_escape_pair_dismisses_without_keypress_or_focus_repair(lab, monkeypatch, input_type, handler):
    callback = "event=>{if(event.key==='Escape'){event.preventDefault();document.querySelector('#panel').hidden=true}}"
    script = ("entry.addEventListener('keydown'," + callback + ")" if handler == "listener"
              else "entry.onkeydown=" + callback)
    markup = '<input id="entry" type="' + input_type + '" value="report"><div id="panel">Report</div>'
    support, context, _, api = lab(script, markup=markup)
    focus(context)
    monkeypatch.setattr(context.page, "locator", lambda *_a, **_k: pytest.fail("implicit focus or selection"))
    evidence = escape(support, context)
    assert asdict(evidence.key_press) == dict(key="Escape", target_matches=1, focused=True,
                                            keydown_count=1, keyup_count=1)
    assert evidence.traffic == [] and api.requests == []
    assert context.page.evaluate("[entry.value,document.activeElement===entry,document.querySelector('#panel').hidden]") == ["report", True, True]
    assert context.page.evaluate("events") == [
        {"type": phase, "key": "Escape", "trusted": True, "target": "entry"}
        for phase in ("keydown", "keyup")]


@pytest.mark.parametrize("markup,selector", [
    ('<input id="other">', '#entry'),
    ('<input id="entry"><input id="other">', 'input'),
    ('<input id="entry" disabled>', '#entry'),
    ('<input id="entry" readonly>', '#entry'),
    ('<input id="entry" aria-disabled="true">', '#entry'),
    ('<input id="entry" aria-readonly="true">', '#entry'),
    ('<div inert><input id="entry"></div>', '#entry'),
    ('<input id="entry" type="password">', '#entry'),
    ('<textarea id="entry"></textarea>', '#entry'),
    ('<input id="entry" style="display:none">', '#entry'),
])
def test_unavailable_or_ambiguous_target_sends_no_escape(lab, monkeypatch, markup, selector):
    support, context, _, api = lab(markup=markup)
    context.page.evaluate("document.querySelector('#entry')?.focus()")
    monkeypatch.setattr(context.page.keyboard, "down", lambda _: pytest.fail("unexpected delivery"))
    with pytest.raises(RuntimeError, match="browser action"):
        escape(support, context, selector=selector)
    assert context.closed and api.requests == []


def test_wrong_focus_does_not_get_repaired(lab, monkeypatch):
    support, context, _, api = lab()
    context.page.locator("#other").focus()
    monkeypatch.setattr(context.page.keyboard, "down", lambda _: pytest.fail("unexpected delivery"))
    with pytest.raises(RuntimeError, match="browser action"):
        escape(support, context)
    assert context.closed and api.requests == []


@pytest.mark.parametrize("fault", ["synthetic", "missing_down", "missing_up", "wrong_key", "repeat"])
def test_missing_invalid_or_synthetic_pair_cannot_pass(lab, monkeypatch, fault):
    support, context, _, _ = lab()
    focus(context)
    # An earlier valid pair is not evidence for the next action.
    assert escape(support, context).key_press.key == "Escape"
    down = context.page.keyboard.down
    if fault == "synthetic":
        for method, phase in [("down", "keydown"), ("up", "keyup")]:
            monkeypatch.setattr(context.page.keyboard, method,
                lambda _, phase=phase: context.page.evaluate(
                    "phase=>entry.dispatchEvent(new KeyboardEvent(phase,{key:'Escape',code:'Escape',bubbles:true}))", phase))
    elif fault == "missing_down":
        monkeypatch.setattr(context.page.keyboard, "down", lambda _: None)
    elif fault == "missing_up":
        monkeypatch.setattr(context.page.keyboard, "up", lambda _: None)
    elif fault == "wrong_key":
        monkeypatch.setattr(context.page.keyboard, "down", lambda _: down("Enter"))
    else:
        def twice(key):
            down(key)
            down(key)
        monkeypatch.setattr(context.page.keyboard, "down", twice)
    with pytest.raises(RuntimeError, match="browser action"):
        escape(support, context)
    assert context.closed


@pytest.mark.parametrize("change", [
    "other.focus()",
    "other.focus();entry.focus()",
    "entry.replaceWith(entry.cloneNode(true));document.querySelector('#entry').focus()",
    "entry.remove()",
    "entry.style.visibility='hidden'",
])
def test_focus_loss_or_target_change_during_delivery_is_not_repaired(lab, change):
    support, context, _, _ = lab("entry.onkeydown=()=>{" + change + "}")
    focus(context)
    with pytest.raises(RuntimeError, match="browser action"):
        escape(support, context)
    assert context.closed


@pytest.mark.parametrize("change", ["other.focus();entry.focus()", "document.body.append(entry.cloneNode(true))"])
def test_final_snapshot_cannot_hide_focus_loss_or_ambiguity(lab, change):
    def rendered(page):
        if page.evaluate("window.__refractBrowser?.armed?.key === 'Escape'"):
            page.evaluate("()=>{" + change + "}")
        return {}
    support, context, _, _ = lab(rendered=rendered)
    focus(context)
    with pytest.raises(RuntimeError, match="browser action"):
        escape(support, context)
    assert context.closed


@pytest.mark.parametrize("callback", [
    "entry.addEventListener('keydown',()=>tracked())",
    "entry.onkeydown=()=>tracked()",
    "entry.onkeyup=()=>tracked()",
    "document.addEventListener('keyup',e=>e.target===entry&&tracked())",
    "entry.onkeydown=()=>Promise.resolve().then(()=>tracked())",
    "entry.onkeyup=async()=>{await Promise.resolve();await tracked()}",
    "entry.onkeyup=()=>setTimeout(()=>tracked(),0)",
])
def test_escape_http_is_diagnostic_even_for_supported_enter_callback_shapes(lab, callback):
    script = "window.done=[];function tracked(tag='escape'){return send(tag).finally(()=>done.push(tag))};" + callback
    support, context, _, api = lab(script)
    focus(context)
    first = escape(support, context)
    context.page.wait_for_function("done.includes('escape')")
    context.native.collect(first.action_id)
    assert first.traffic == [] and context.traffic == []
    assert any(r.request.body == {"tag": "escape"} for r in context.diagnostics)
    assert len(api.requests) == 1
    assert not any(name.lower().startswith("x-refract-") for name in api.requests[0]["headers"])


@pytest.mark.parametrize("following", ["click", "Enter"])
@pytest.mark.parametrize("handler", ["listener", "property", "inline"])
def test_deferred_escape_cannot_become_following_action_evidence(lab, following, handler):
    script = """window.release=null;window.pending=new Promise(resolve=>release=resolve);
    window.done=[];function tracked(tag){return send(tag).finally(()=>done.push(tag))};
    go.onclick=()=>{release();return tracked('click')};"""
    callback = "async event=>{if(event.key==='Escape'){await pending;return tracked('escape')}release();return tracked('enter')}"
    markup = '<input id="entry"><input id="other"><button id="go">Read</button>'
    if handler == "listener":
        script += "entry.addEventListener('keyup'," + callback + ")"
    elif handler == "property":
        script += "entry.onkeyup=" + callback
    else:
        markup = markup.replace('<input id="entry">', '<input id="entry" onkeyup="return (' + callback + ')(event)">')
    support, context, _, api = lab(script, markup=markup)
    focus(context)
    assert escape(support, context).traffic == []
    if following == "click":
        next_evidence = support.perform(context, permit("click"), selector="#go").evidence
    else:
        next_evidence = support.perform(context, permit(), selector="#entry").evidence
    context.page.wait_for_function("done.includes('escape') && done.length===2")
    context.native.collect(next_evidence.action_id)
    assert [t.request.body for t in next_evidence.traffic] == [{"tag": following.lower()}]
    assert any(r.request.body == {"tag": "escape"} for r in context.diagnostics)
    assert len(api.requests) == 2


def test_nested_synthetic_inline_await_has_no_escape_or_following_click_origin(lab):
    markup = '<input id="entry"><input id="other" onkeyup="return (async()=>{await Promise.resolve();await send(\'nested\');window.done=true})()"><button id="go">Read</button>'
    script = "window.done=false;entry.onkeyup=()=>other.dispatchEvent(new KeyboardEvent('keyup',{key:'Escape',bubbles:true}));go.onclick=()=>{}"
    support, context, _, api = lab(script, markup=markup)
    focus(context)
    assert escape(support, context).traffic == []
    context.page.wait_for_function("done")
    evidence = support.perform(context, permit("click"), selector="#go").evidence
    assert evidence.traffic == []
    assert len(api.requests) == 1
    assert any(r.request.body == {"tag": "nested"} for r in context.diagnostics)


@pytest.mark.parametrize("native", [False, True])
def test_same_path_escape_request_cannot_rescue_missing_click_request(lab, native):
    script = "window.done=false;entry.onkeyup=()=>send('escape').finally(()=>done=true);go.onclick=()=>{}"
    support, context, _, _ = lab(script, native=native)
    focus(context)
    assert escape(support, context).traffic == []
    context.page.wait_for_function("done")
    assert support.perform(context, permit("click"), selector="#go").evidence.traffic == []


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("deferred", [False, True])
def test_mock_escape_cannot_consume_later_fixture_or_reach_live_service(lab, native, deferred):
    fixture = ports.MockResponse(fixture_id="click-fixture", source="neutral", method="POST",
        path="records/echo" if native else "api/echo", response={"ok": True},
        response_headers={"access-control-allow-origin": "*"})
    script = """window.release=null;window.pending=new Promise(resolve=>release=resolve);
    window.done=[];function tracked(tag){return send(tag).catch(()=>{}).finally(()=>done.push(tag))};
    entry.onkeyup=async()=>{WAIT;await tracked('escape')};
    go.onclick=()=>{release();return tracked('click')};""".replace("WAIT", "await pending" if deferred else "")
    support, context, app, api = lab(script, mode="mock", native=native, fixtures=[fixture])
    focus(context)
    first = escape(support, context)
    assert first.traffic == [] and first.mock_recordings == []
    second = support.perform(context, permit("click", mode="mock"), selector="#go").evidence
    context.page.wait_for_function("done.includes('escape')")
    assert [t.request.body for t in second.traffic] == [{"tag": "click"}]
    assert [r.mock_fixture_id for r in second.mock_recordings] == ["click-fixture"]
    assert context.mock_queue.index == 1
    assert api.requests == [] and not any(r["path"].startswith("/api/") for r in app.requests)


@pytest.mark.parametrize("transition", [
    "location.href='/?next'",
    "history.pushState({},'', '/next')",
    "window.open('about:blank')",
    "document.body.insertAdjacentHTML('beforeend','<iframe></iframe>')",
    "const a=document.createElement('a');a.href='data:text/plain,neutral';a.download='neutral';a.click()",
    "document.open();document.write('<p>replacement</p>');document.close()",
])
def test_unsupported_escape_transition_fails(lab, transition):
    support, context, _, _ = lab("entry.onkeydown=()=>{" + transition + "}")
    focus(context)
    with pytest.raises(RuntimeError, match="browser action"):
        escape(support, context)
    assert context.closed


@pytest.mark.parametrize("key", ["Escape", "Enter"])
@pytest.mark.parametrize("attempt", range(2))
def test_rejected_popup_aborts_pending_key_without_running_new_target(lab, key, attempt):
    support, context, _, api = lab("entry.onkeydown=()=>window.open(window.destination)")
    context.page.evaluate("url=>window.destination=url", api.url + "/api/echo")
    focus(context)
    with pytest.raises(RuntimeError, match="browser action"):
        support.perform(context, replace(permit(), key=key), selector="#entry")
    assert context.closed and api.requests == []


def test_escape_does_not_enter_native_form_submit_chain(lab):
    markup = '<form onsubmit="event.preventDefault();send()"><input id="entry"><button id="go">Submit</button></form>'
    support, context, _, api = lab(markup=markup)
    focus(context)
    evidence = escape(support, context)
    assert evidence.key_press.key == "Escape" and evidence.traffic == [] and api.requests == []
    assert not any(event["type"] == "click" for event in context.page.evaluate("events"))


def test_protected_idle_gap_rejects_navigation_before_next_action(lab, monkeypatch):
    support, context, _, _ = lab()
    focus(context)
    escape(support, context)
    context.page.evaluate("history.pushState({},'', '/late')")
    monkeypatch.setattr(context.page, "locator", lambda *_a, **_k: pytest.fail("next action delivered"))
    with pytest.raises(RuntimeError, match="browser action"):
        support.perform(context, permit("click"), selector="#go")
    assert context.closed


@pytest.mark.parametrize("failure", ["host_error", "deadline"])
def test_final_receipt_rechecks_boundary_and_budget(lab, monkeypatch, failure):
    from refracto_browser._key_press import PinnedKeyPress
    support, context, _, _ = lab()
    focus(context)
    receipt = PinnedKeyPress.receipt
    def delayed(pinned):
        result = receipt(pinned)
        if failure == "host_error":
            context.errors.append("browser keyboard transition is unsupported")
        else:
            context.deadline = time.monotonic() - 1
        return result
    monkeypatch.setattr(PinnedKeyPress, "receipt", delayed)
    with pytest.raises(RuntimeError, match="browser action"):
        escape(support, context)
    assert context.closed


def test_next_authorized_enter_retains_its_native_form_behavior(lab):
    markup = '<form onsubmit="event.preventDefault();return send(\'submit\')"><input id="entry"><button id="go">Submit</button></form>'
    support, context, _, api = lab(markup=markup)
    focus(context)
    assert escape(support, context).traffic == []
    evidence = support.perform(context, permit(), selector="#entry").evidence
    assert evidence.key_press.key == "Enter"
    assert [t.request.body for t in evidence.traffic] == [{"tag": "submit"}]
    assert len(api.requests) == 1
