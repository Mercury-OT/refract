"""Real Chromium native Enter/form causality and programmatic counterexamples."""
import pytest
from refracto import ports
from tests.browser.test_enter_press import lab, focus, press, permit
MARKUP = '<form id="form"><input id="entry" name="q"><button id="go">Search</button></form><input id="other"><form id="otherform"><input id="otherentry"><button id="othergo">Other</button></form>'

@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('script', ["form.addEventListener('submit',e=>{e.preventDefault();send()})", 'form.onsubmit=e=>{e.preventDefault();send()}', "document.addEventListener('submit',e=>{if(e.target===form){e.preventDefault();send()}})", 'form.onsubmit=e=>{e.preventDefault();Promise.resolve().then(()=>send())}'])
def test_handlers(lab, native, script):
    (support, ctx, app, api) = lab(script, markup=MARKUP, native=native)
    focus(ctx)
    ev = press(support, ctx)
    assert len(ev.traffic) == 1
    assert ev.traffic[0].request.body == {'tag': 'action'}
    assert ev.key_press.keydown_count == ev.key_press.keyup_count == 1

@pytest.mark.parametrize('script', ['form.onsubmit=async e=>{e.preventDefault();await Promise.resolve();await send()}', "document.addEventListener('submit',async e=>{if(e.target===form){e.preventDefault();await Promise.resolve();await send()}})"])
def test_native_await(lab, script):
    (support, ctx, _, _) = lab(script, markup=MARKUP)
    focus(ctx)
    ev = press(support, ctx)
    assert len(ev.traffic) == 1

def test_parsed_inline(lab):
    markup = MARKUP.replace('<form id="form">', '<form id="form" onsubmit="event.preventDefault();return (async()=>{await Promise.resolve();await send()})()">')
    (support, ctx, _, _) = lab(markup=markup)
    focus(ctx)
    ev = press(support, ctx)
    assert len(ev.traffic) == 1

@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('invocation', ['form.requestSubmit(go)', 'go.click()', "go.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}))", 'Promise.resolve().then(()=>form.requestSubmit(go))', 'setTimeout(()=>form.requestSubmit(go),0)', 'otherform.requestSubmit(othergo)'])
def test_programmatic_not_evidence(lab, native, invocation):
    script = "form.onsubmit=otherform.onsubmit=e=>{e.preventDefault();send('programmatic').then(()=>window.programmaticDone=true)};entry.onkeypress=e=>{e.preventDefault();" + invocation + '}'
    (support, ctx, app, api) = lab(script, markup=MARKUP, native=native)
    focus(ctx)
    ev = press(support, ctx)
    assert ev.traffic == []
    # Observe completion instead of assuming a background response finishes in
    # a fixed sleep on every CI machine.
    ctx.page.wait_for_function('window.programmaticDone === true', timeout=5000)
    if native:
        ctx.native.collect(ev.action_id)
    assert len(api.requests if native else [r for r in app.requests if r['path'] == '/api/echo']) == 1
    assert not ctx.traffic

@pytest.mark.parametrize('native', [False, True])
def test_same_path_timer_remains_diagnostic(lab, native):
    script = "form.onsubmit=e=>{e.preventDefault();setTimeout(()=>send('background'),0);send()}"
    (support, ctx, _, _) = lab(script, markup=MARKUP, native=native)
    focus(ctx)
    ev = press(support, ctx)
    assert [t.request.body for t in ev.traffic] == [{'tag': 'action'}]

def test_nested_programmatic_submit_cannot_borrow_origin(lab):
    script = "otherform.onsubmit=async e=>{e.preventDefault();await Promise.resolve();await send('nested')};form.onsubmit=e=>{e.preventDefault();otherform.requestSubmit(othergo);send()}"
    (support, ctx, _, _) = lab(script, markup=MARKUP)
    focus(ctx)
    ev = press(support, ctx)
    assert [t.request.body for t in ev.traffic] == [{'tag': 'action'}]

def test_button_disabled_after_submission(lab):
    script = 'form.onsubmit=e=>{e.preventDefault();go.disabled=true;send()}'
    (support, ctx, _, _) = lab(script, markup=MARKUP)
    focus(ctx)
    ev = press(support, ctx)
    assert len(ev.traffic) == 1

def test_implicit_click_request_is_background(lab):
    script = "go.onclick=()=>send('implicitclick');form.onsubmit=e=>{e.preventDefault();send()}"
    (support, ctx, _, _) = lab(script, markup=MARKUP)
    focus(ctx)
    ev = press(support, ctx)
    assert [t.request.body for t in ev.traffic] == [{'tag': 'action'}]

def test_property_return_false(lab):
    script = 'form.onsubmit=()=>{send();return false}'
    (support, ctx, _, _) = lab(script, markup=MARKUP)
    focus(ctx)
    ev = press(support, ctx)
    assert len(ev.traffic) == 1

def test_native_input_submitter(lab):
    markup = MARKUP.replace('<button id="go">Search</button>', '<input type="submit" id="go" value="Search">')
    script = 'form.onsubmit=e=>{e.preventDefault();send()}'
    (support, ctx, _, _) = lab(script, markup=markup)
    focus(ctx)
    ev = press(support, ctx)
    assert len(ev.traffic) == 1

def test_external_default_submitter(lab):
    markup = MARKUP.replace('<button id="go">Search</button>', '').replace('<input id="other">', '<button id="go" form="form">Search</button><input id="other">')
    script = 'form.onsubmit=e=>{e.preventDefault();send()}'
    (support, ctx, _, _) = lab(script, markup=markup)
    focus(ctx)
    ev = press(support, ctx)
    assert len(ev.traffic) == 1

@pytest.mark.parametrize('native', [False, True])
def test_xhr_submit(lab, native):
    (support, ctx, app, api) = lab(markup=MARKUP, native=native)
    ctx.page.evaluate("url=>{form.onsubmit=e=>{e.preventDefault();const x=new XMLHttpRequest();x.open('POST',url);x.send(JSON.stringify({tag:'xhr'}))}}", (api.url if native else app.url) + '/api/echo')
    focus(ctx)
    ev = press(support, ctx)
    assert [t.request.body for t in ev.traffic] == [{'tag': 'xhr'}]

@pytest.mark.parametrize('native', [False, True])
def test_explicit_mock(lab, native):
    fixture = ports.MockResponse(fixture_id='form-mock', source='neutral', method='POST', path='records/echo' if native else 'api/echo', response={'success': True}, response_headers={'access-control-allow-origin': '*'})
    script = 'form.onsubmit=e=>{e.preventDefault();send()}'
    (support, ctx, app, api) = lab(script, markup=MARKUP, native=native, mode='mock', fixtures=[fixture])
    focus(ctx)
    ev = press(support, ctx)
    assert len(ev.traffic) == len(ev.mock_recordings) == 1
    assert ev.traffic[0].mock_fixture_id == 'form-mock'
    assert not api.requests
    assert not [r for r in app.requests if r['path'] == '/api/echo']

def test_native_validation_is_not_repaired(lab):
    markup = MARKUP.replace('name="q"', 'name="q" required')
    script = 'form.onsubmit=e=>{e.preventDefault();send()}'
    (support, ctx, _, api) = lab(script, markup=markup)
    focus(ctx)
    ev = press(support, ctx)
    assert not ev.traffic and (not api.requests)
    assert ctx.page.evaluate('entry.validity.valueMissing') is True

@pytest.mark.parametrize('native', [False, True])
def test_implicit_click_native_await_stays_diagnostic(lab, native):
    script = "go.onclick=async()=>{await Promise.resolve();await send('onclick')};form.onsubmit=e=>{e.preventDefault();send()}"
    (support, ctx, _, _) = lab(script, markup=MARKUP, native=native)
    focus(ctx)
    ev = press(support, ctx)
    assert [t.request.body for t in ev.traffic] == [{'tag': 'action'}]

@pytest.mark.parametrize('script', ['go.onclick=()=>otherform.requestSubmit(othergo)', 'go.onclick=()=>Promise.resolve().then(()=>otherform.requestSubmit(othergo))', "form.addEventListener('submit',()=>otherform.requestSubmit(othergo))"])
def test_nested_programmatic_trusted_submit(lab, script):
    script = "otherform.onsubmit=async e=>{e.preventDefault();await Promise.resolve();await send('nested')};form.onsubmit=e=>{e.preventDefault();send()};" + script
    (support, ctx, _, _) = lab(script, markup=MARKUP)
    focus(ctx)
    ev = press(support, ctx)
    assert [t.request.body for t in ev.traffic] == [{'tag': 'action'}]

def test_product_stop_propagation_retains_submit(lab):
    script = 'form.onsubmit=e=>{e.preventDefault();e.stopPropagation();send()}'
    (support, ctx, _, _) = lab(script, markup=MARKUP)
    focus(ctx)
    ev = press(support, ctx)
    assert len(ev.traffic) == 1

def test_cancelled_key_has_no_submit_request(lab):
    script = 'entry.onkeydown=e=>e.preventDefault();form.onsubmit=e=>{e.preventDefault();send()}'
    (support, ctx, _, api) = lab(script, markup=MARKUP)
    focus(ctx)
    ev = press(support, ctx)
    assert ev.key_press.keydown_count == ev.key_press.keyup_count == 1
    assert not ev.traffic and (not api.requests)

def test_submitter_disabled_after_submit_bubbling_remains_historical(lab):
    script = "form.onsubmit=e=>{e.preventDefault();go.disabled=true;send()};document.addEventListener('submit',()=>window.sawSubmit=true)"
    (support, ctx, _, _) = lab(script, markup=MARKUP)
    focus(ctx)
    ev = press(support, ctx)
    assert len(ev.traffic) == 1 and ctx.page.evaluate('window.sawSubmit') is True

def test_two_actual_submit_requests_are_both_retained(lab):
    script = "form.onsubmit=e=>{e.preventDefault();send('first');send('second')}"
    (support, ctx, _, _) = lab(script, markup=MARKUP)
    focus(ctx)
    ev = press(support, ctx)
    assert sorted((t.request.body['tag'] for t in ev.traffic)) == ['first', 'second']

@pytest.mark.parametrize('script', ['entry.onkeypress=()=>go.replaceWith(go.cloneNode(true))', "entry.onkeypress=()=>go.form.insertBefore(document.createElement('button'),entry)", "entry.onkeypress=()=>{go.setAttribute('form','otherform')}", "entry.onkeypress=()=>{form.id='changed';entry.setAttribute('form','otherform')}"])
def test_changed_form_source_is_not_rebound(lab, script):
    script += ';form.onsubmit=otherform.onsubmit=e=>{e.preventDefault();send()}'
    (support, ctx, _, _) = lab(script, markup=MARKUP)
    focus(ctx)
    with pytest.raises(RuntimeError):
        press(support, ctx)

@pytest.mark.parametrize('markup', [MARKUP.replace('<button id="go">Search</button>', ''), MARKUP.replace('<button id="go">Search</button>', '<input id="go" type="image">')])
def test_unsupported_form_shape_fails_closed(lab, markup):
    (support, ctx, _, _) = lab('form.onsubmit=e=>{e.preventDefault();send()}', markup=markup)
    focus(ctx)
    with pytest.raises(RuntimeError):
        press(support, ctx)

@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('markup', [MARKUP.replace('<form id="form">', '<form id="form" target="_blank">'), MARKUP.replace('<button id="go">', '<button id="go" formtarget="_blank">'), MARKUP.replace('<form id="form">', '<form id="form" target="_self">')])
def test_cancelled_submit_stays_same_page_despite_target_attribute(lab, native, markup):
    (support, ctx, _, _) = lab('form.onsubmit=e=>{e.preventDefault();send()}', markup=markup, native=native)
    focus(ctx)
    ev = press(support, ctx)
    assert len(ev.traffic) == 1
    assert len(ctx.browser_context.pages) == len(ctx.page.frames) == 1

@pytest.mark.parametrize('markup', [MARKUP.replace('<form id="form">', '<form id="form" target="_blank">'), MARKUP.replace('<button id="go">', '<button id="go" formtarget="_blank">')])
def test_uncancelled_target_cannot_pass_by_navigation_guard(lab, markup):
    (support, ctx, _, _) = lab(markup=markup)
    focus(ctx)
    with pytest.raises(RuntimeError):
        press(support, ctx)

def test_first_of_two_submitters_is_native_default(lab):
    markup = MARKUP.replace('</form><input id="other">', '<button id="later">Later</button></form><input id="other">')
    script = "form.onsubmit=e=>{e.preventDefault();send(e.submitter===go?'action':'wrong')}"
    (support, ctx, _, _) = lab(script, markup=markup)
    focus(ctx)
    ev = press(support, ctx)
    assert [t.request.body for t in ev.traffic] == [{'tag': 'action'}]

def test_nested_inline_programmatic_submit_native_await(lab):
    markup = MARKUP.replace('<form id="otherform">', '<form id="otherform" onsubmit="event.preventDefault();return (async()=>{await Promise.resolve();await send(\'nestedinline\')})()">')
    script = 'form.onsubmit=e=>{e.preventDefault();otherform.requestSubmit(othergo);send()}'
    (support, ctx, _, _) = lab(script, markup=markup)
    focus(ctx)
    ev = press(support, ctx)
    assert [t.request.body for t in ev.traffic] == [{'tag': 'action'}]

@pytest.mark.parametrize('script', ['form.onsubmit=e=>{send()}', "form.onsubmit=e=>{e.preventDefault();location.href='/?moved';send()}", 'form.onsubmit=e=>{e.preventDefault();other.focus();entry.focus();send()}', 'entry.onkeypress=e=>{otherform.appendChild(entry)};form.onsubmit=e=>{e.preventDefault();send()}'])
def test_invalid_transition(lab, script):
    (support, ctx, _, _) = lab(script, markup=MARKUP)
    focus(ctx)
    with pytest.raises(RuntimeError):
        press(support, ctx)


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('inline', [False, True])
def test_explicit_click_keeps_existing_submit_property_scope(lab, native, inline):
    markup = MARKUP.replace('<button id="go">', '<button id="go" type="button">')
    callback = "event.preventDefault();send('click-submit')"
    if inline:
        markup = markup.replace('<form id="form">', '<form id="form" onsubmit="' + callback + '">')
    script = 'go.onclick=()=>form.requestSubmit();'
    if not inline:
        script += 'form.onsubmit=event=>{' + callback + '}'
    support, ctx, _, _ = lab(script, markup=markup, native=native)
    evidence = support.perform(ctx, permit('click'), selector='#go').evidence
    assert [t.request.body for t in evidence.traffic] == [{'tag': 'click-submit'}]


@pytest.mark.parametrize('inline', [False, True])
def test_nonpress_submit_property_retains_native_await_ancestry(lab, inline):
    markup = MARKUP.replace('<button id="go">', '<button id="go" type="button">')
    callback = "event.preventDefault();return (async()=>{await Promise.resolve();await send('click-await')})()"
    if inline:
        markup = markup.replace('<form id="form">', '<form id="form" onsubmit="' + callback + '">')
    script = 'go.onclick=()=>form.requestSubmit();'
    if not inline:
        script += 'form.onsubmit=event=>{' + callback + '}'
    support, ctx, _, _ = lab(script, markup=markup)
    evidence = support.perform(ctx, permit('click'), selector='#go').evidence
    assert [t.request.body for t in evidence.traffic] == [{'tag': 'click-await'}]


@pytest.mark.parametrize('native', [False, True])
def test_shared_property_callback_identity_and_event_scopes(lab, native):
    markup = MARKUP.replace('<button id="go">', '<button id="go" type="button">')
    script = "function shared(event){if(event.type==='click'){form.requestSubmit()}else{event.preventDefault();send('shared')}};form.onsubmit=shared;go.onclick=shared;window.sharedOriginal=shared"
    support, ctx, _, _ = lab(script, markup=markup, native=native)
    assert ctx.page.evaluate('form.onsubmit === sharedOriginal && go.onclick === sharedOriginal')
    evidence = support.perform(ctx, permit('click'), selector='#go').evidence
    assert [t.request.body for t in evidence.traffic] == [{'tag': 'shared'}]
    assert ctx.page.evaluate('form.onsubmit === sharedOriginal && go.onclick === sharedOriginal')


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('inline', [False, True])
def test_submit_property_reused_by_explicit_click_after_enter(lab, native, inline):
    markup = MARKUP + '<button id="later" type="button">Later explicit click</button>'
    callback = "send('shared-page');return false"
    if inline:
        markup = markup.replace('<form id="form">', '<form id="form" onsubmit="' + callback + '">')
    script = 'later.onclick=()=>form.requestSubmit(go);'
    if not inline:
        script += 'form.onsubmit=()=>{' + callback + '}'
    support, ctx, _, _ = lab(script, markup=markup, native=native)
    focus(ctx)
    first = press(support, ctx)
    second = support.perform(ctx, permit('click'), selector='#later').evidence
    assert [t.request.body for t in first.traffic] == [{'tag': 'shared-page'}]
    assert [t.request.body for t in second.traffic] == [{'tag': 'shared-page'}]
    assert first.action_id != second.action_id
    assert first.traffic[0].request_id != second.traffic[0].request_id
