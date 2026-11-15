"""Actual Chromium frozen-file selection and native multipart request evidence."""
import hashlib
from email import policy
from email.parser import BytesParser
from uuid import uuid4

import pytest

from refracto import ports
from refracto.files import FileConfig
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport
from tests.browser.test_multi_origin_transport import Peer


BINARY = bytes([0, 1, 2, 10, 13, 127, 128, 129, 192, 255, 65, 66, 0, 254])


def upload(data=BINARY, name='sample.bin'):
    return ports.UploadFile(filename=name, data=data, sha256=hashlib.sha256(data).hexdigest())


def permit(action='click', file=None):
    key = uuid4().hex
    return ports.UiActionPermit(execution_id='file-run', action_id=key, step_id='step-'+key,
                               mode='live', action=action, target='neutral', value=None,
                               token=uuid4().hex, file=file)


@pytest.fixture
def setup():
    owned = []

    def create(script='', *, inputs='<input id="upload" type="file" name="attachment">', mode='live', config=None,
               mock_plan=None, timeout_ms=1500):
        app, api = Peer(), Peer()
        app.page = ('<form id="form">' + inputs + '<input name="title" value="neutral"></form>'
                    '<button id="go">go</button><button id="other">other</button><script>const api="' + api.url + '";'
                    'const go=document.querySelector("#go"),other=document.querySelector("#other"),upload=document.querySelector("#upload");'
                    'window.events=[];for(const type of ["input","change","click"])document.addEventListener(type,e=>events.push({type:e.type,trusted:e.isTrusted,target:e.target.id}));'
                    + script + '</script>').encode()
        support = BrowserSupport(app.url, lambda page: {}, timeout_ms=timeout_ms, file_config=config,
                                 network_policy=BrowserNetworkPolicy(api_endpoints=(ApiEndpoint(api.url, '/api', 'records'),)))
        context = support.open(mode, mock_plan=mock_plan)
        owned.append((support, context, app, api))
        p = permit('open')
        if mode == 'mock':
            from dataclasses import replace
            p = replace(p, mode='mock')
        support.perform(context, p, url=app.url+'/')
        return support, context, api

    yield create
    for support, context, app, api in owned:
        support.close(context)
        app.close()
        api.close()


def select(support, context, file=None):
    p = permit('select_file', file=upload() if file is None else file)
    if context.mode == 'mock':
        from dataclasses import replace
        p = replace(p, mode='mock')
    return support.perform(context, p, selector='#upload').evidence


def click(support, context, target='go'):
    p = permit()
    if context.mode == 'mock':
        from dataclasses import replace
        p = replace(p, mode='mock')
    return support.perform(context, p, selector='#'+target).evidence


def script(transport='fetch', mutation='', awaited=True):
    send = "await (await fetch(api+'/api/upload',{method:'POST',body})).json()" if transport == 'fetch' else "await new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST',api+'/api/upload');xhr.onload=resolve;xhr.onerror=reject;xhr.send(body)})"
    return "async function send(){const body=new FormData(document.querySelector('#form'));"+mutation+';'+send+'};go.onclick=async()=>{'+('await Promise.resolve();' if awaited else '')+'await send()}'


def actual_file(request):
    body = request['body']
    header = request['headers']['Content-Type']
    message = BytesParser(policy=policy.default).parsebytes(('Content-Type: '+header+'\r\n\r\n').encode()+body)
    return next(p for p in message.iter_parts() if p.get_filename() is not None)


@pytest.mark.parametrize('transport', ['fetch', 'xhr'])
@pytest.mark.parametrize('awaited', [False, True])
@pytest.mark.parametrize('payload', [BINARY, b'', b'neutral text\n', b'%PDF-1.7\n', b'\x89PNG\r\n\x1a\n'])
def test_selected_frozen_bytes_and_actual_server_upload(setup, transport, awaited, payload):
    support, context, api = setup(script(transport, awaited=awaited))
    selected = select(support, context, upload(payload))
    assert selected.traffic == [] and api.requests == []
    assert selected.file_selection.target_matches == 1
    assert selected.file_selection.file == upload(payload)
    assert context.page.evaluate('events') == [
        {'type': 'input', 'trusted': False, 'target': 'upload'},
        {'type': 'change', 'trusted': False, 'target': 'upload'}]
    result = click(support, context)
    assert len(result.traffic) == 1
    traffic = result.traffic[0]
    assert traffic.action_id == result.action_id
    assert traffic.browser_identity == traffic.response.browser_identity
    assert traffic.request.body == {'title': 'neutral'}
    assert traffic.request.files == {'attachment': upload(payload)}
    assert traffic.response.request.files == traffic.request.files
    assert len(api.requests) == 1
    actual = actual_file(api.requests[0])
    assert actual.get_payload(decode=True) == payload
    assert actual.get_filename() == 'sample.bin'
    assert context.page.evaluate('events.at(-1).trusted') is True


@pytest.mark.parametrize('mutation,name,payload,field', [
    ("body.set('attachment',new File([new Uint8Array([0,255,128])],'other.bin'))", 'other.bin', b'\0\xff\x80', 'attachment'),
    ("body.set('attachment',new File([body.get('attachment').slice(0,3)],'short.bin'))", 'short.bin', BINARY[:3], 'attachment'),
    ("body.set('different',body.get('attachment'));body.delete('attachment')", 'sample.bin', BINARY, 'different'),
])
def test_wrong_well_formed_file_is_observed_for_core_comparison(setup, mutation, name, payload, field):
    support, context, api = setup(script(mutation=mutation))
    select(support, context)
    result = click(support, context)
    assert result.traffic[0].request.files == {field: upload(payload, name)}
    assert actual_file(api.requests[0]).get_payload(decode=True) == payload


def test_complete_missing_file_remains_observed_none(setup):
    support, context, api = setup(script(mutation="body.delete('attachment')"))
    select(support, context)
    result = click(support, context)
    assert result.traffic[0].request.files is None
    assert result.traffic[0].request.body == {'title': 'neutral'}
    assert len(api.requests) == 1


@pytest.mark.parametrize('inputs', ['', '<input id="upload">', '<input id="upload" type="file" hidden>',
    '<input id="upload" type="file" disabled>', '<input id="upload" type="file" multiple>',
    '<input id="upload" type="file" webkitdirectory>',
    '<input id="upload" type="file"><input id="upload" type="file">'])
def test_unavailable_or_ambiguous_file_input_fails_closed(setup, inputs):
    support, context, api = setup(inputs=inputs)
    with pytest.raises(RuntimeError, match='browser action'):
        select(support, context)
    assert context.closed and api.requests == []


def test_replacement_input_fails_same_element_readback(setup):
    support, context, api = setup("upload.onchange=()=>upload.replaceWith(upload.cloneNode())")
    with pytest.raises(RuntimeError, match='browser action'):
        select(support, context)
    assert context.closed and api.requests == []


@pytest.mark.parametrize('mode', ['live', 'mock'])
@pytest.mark.parametrize('trigger', ["upload.oninput=()=>send()", "upload.onchange=async()=>{await Promise.resolve();await send()}",
    "upload.onchange=()=>setTimeout(()=>send(),0)"])
def test_selection_auto_upload_is_rejected_before_delivery(setup, mode, trigger):
    support, context, api = setup(script()+';'+trigger, mode=mode)
    with pytest.raises(RuntimeError, match='browser action'):
        select(support, context)
    assert context.closed and api.requests == []
    assert context.mock_queue.index == 0


@pytest.mark.parametrize('transport', ['fetch', 'xhr'])
@pytest.mark.parametrize('kind', ['background', 'synthetic', 'delayed'])
def test_same_endpoint_unrelated_or_old_upload_never_claims_click(setup, transport, kind):
    behavior = {
        'background': 'go.onclick=async()=>{setTimeout(()=>send(),0);await send()};other.onclick=()=>Promise.resolve()',
        'synthetic': 'other.onclick=()=>send();go.onclick=async()=>{other.click();await send()}',
        'delayed': 'let release;const gate=new Promise(r=>release=r);async function late(){await gate;await send()};go.onclick=()=>{void late()};other.onclick=()=>{release();return Promise.resolve()}',
    }[kind]
    support, context, api = setup(script(transport)+';'+behavior)
    select(support, context)
    first = click(support, context)
    context.page.wait_for_timeout(50)
    if kind == 'delayed':
        second = click(support, context, 'other')
        context.page.wait_for_timeout(50)
        third = click(support, context, 'other')
        assert first.traffic == second.traffic == third.traffic == []
        records = second.diagnostic_recorded + third.diagnostic_recorded
        assert len(records) == 1 and records[0].step_id == first.step_id
        assert len(api.requests) == 1
    else:
        assert len(first.traffic) == 1 and len(api.requests) == 2
        records = first.diagnostic_recorded
        if not records:
            records = click(support, context, 'go' if kind == 'synthetic' else 'other').diagnostic_recorded
        assert records and records[0].step_id is None
        assert records[0].request.files == {'attachment': upload()}
    assert all(actual_file(r).get_payload(decode=True) == BINARY for r in api.requests)


def test_exact_and_over_file_limit_fail_before_extra_delivery(setup):
    support, context, api = setup(script(mutation="body.set('attachment',new File([new Uint8Array(101)],'b.bin'))"), config=FileConfig(max_file_bytes=100))
    select(support, context, upload(b'x'*100))
    with pytest.raises(RuntimeError, match='browser action'):
        click(support, context)
    assert context.closed and api.requests == []


def test_missing_native_empty_file_entry_fails_closed(setup):
    support, context, api = setup(script())
    select(support, context, upload(b''))
    original = context.native._process
    def omit_file_entry(event):
        request = event['request']
        if 'responseStatusCode' not in event and 'postDataEntries' in request:
            entries = request['postDataEntries']
            request['postDataEntries'] = [entries[0], {}, *entries[2:]]
        return original(event)
    context.native._process = omit_file_entry
    with pytest.raises(RuntimeError, match='browser action'):
        click(support, context)
    assert context.closed and api.requests == []


@pytest.mark.parametrize('name,media', [('note.txt', 'text/plain'), ('image.png', 'image/png'),
                                      ('document.pdf', 'application/pdf'), ('sample.unknownext', 'application/octet-stream')])
def test_standard_filename_mime_reaches_input_and_actual_part(setup, name, media):
    support, context, api = setup(script())
    select(support, context, upload(BINARY, name))
    assert context.page.evaluate('upload.files[0].type') == media
    assert context.page.evaluate('document.activeElement === document.body') is True
    click(support, context)
    assert actual_file(api.requests[0]).get_content_type() == media
    assert actual_file(api.requests[0]).get_payload(decode=True) == BINARY


@pytest.mark.parametrize('name', ['quote".txt', 'escape%22.txt', 'escape%0A.txt', 'escape%0d.txt'])
def test_ambiguous_filename_escaping_fails_before_selection(setup, name):
    support, context, api = setup(script())
    with pytest.raises(RuntimeError, match='browser action'):
        select(support, context, upload(BINARY, name))
    assert context.closed and api.requests == []


def test_changed_selected_bytes_fail_readback(setup):
    support, context, api = setup("upload.onchange=()=>{const files=new DataTransfer();files.items.add(new File(['changed'],'sample.bin'));upload.files=files.files}")
    with pytest.raises(RuntimeError, match='browser action'):
        select(support, context)
    assert context.closed and api.requests == []


@pytest.mark.parametrize('mode', ['live', 'mock'])
def test_late_selection_descendant_is_denied_during_later_click(setup, mode):
    support, context, api = setup(script()+";let release;const gate=new Promise(r=>release=r);async function late(){await gate;await send()};upload.onchange=()=>{void late()};go.onclick=()=>release()", mode=mode)
    select(support, context)
    with pytest.raises(RuntimeError, match='browser action'):
        click(support, context)
    assert context.closed and api.requests == [] and context.mock_queue.index == 0


def test_mock_upload_uses_actual_bytes_without_live_forwarding(setup):
    fixture = ports.MockResponse(fixture_id='upload', source='neutral fixture', method='POST',
                                 path='records/upload', response={'id': 'saved'}, status=201,
                                 response_headers={'Access-Control-Allow-Origin': '*'})
    support, context, api = setup(script(), mode='mock', mock_plan=[fixture])
    select(support, context)
    result = click(support, context)
    assert api.requests == [] and context.mock_queue.index == 1
    assert len(result.traffic) == 1
    assert result.traffic[0].request.files == {'attachment': upload()}
    assert result.traffic[0].response.status == 201


def test_real_disk_backed_empty_file_cannot_supply_complete_evidence(setup, tmp_path):
    support, context, api = setup(script())
    select(support, context, upload(b''))
    disk_file = tmp_path / 'empty.bin'
    disk_file.write_bytes(b'')
    context.page.locator('#upload').set_input_files(disk_file)
    with pytest.raises(RuntimeError, match='browser action'):
        click(support, context)
    assert context.closed and api.requests == []


def test_large_background_upload_respects_diagnostic_byte_budget(setup):
    support, context, api = setup(script()+";go.onclick=()=>{setTimeout(()=>send(),0)};other.onclick=()=>Promise.resolve()")
    select(support, context, upload(b'x'*(256*1024)))
    first = click(support, context)
    context.page.wait_for_timeout(50)
    second = click(support, context, 'other')
    assert first.traffic == second.traffic == []
    assert first.diagnostic_recorded == second.diagnostic_recorded == []
    assert 'background diagnostics truncated' in second.diagnostic_notes
    assert context.native.background_bytes <= 256*1024
    assert len(api.requests) == 1


def test_default_ten_mib_limit_matches_actual_server_bytes(setup):
    payload = bytes(range(256)) * (10*1024*1024//256)
    support, context, api = setup(script(), timeout_ms=15000)
    select(support, context, upload(payload))
    result = click(support, context)
    observed = result.traffic[0].request.files['attachment']
    assert observed.data == payload
    assert hashlib.sha256(actual_file(api.requests[0]).get_payload(decode=True)).hexdigest() == observed.sha256


@pytest.mark.parametrize('initially_selected', [False, True])
def test_unselected_input_is_complete_observed_missing_file(setup, initially_selected):
    support, context, api = setup(script())
    if initially_selected:
        select(support, context)
        context.page.evaluate("upload.value=''")
    result = click(support, context)
    assert result.traffic[0].request.files is None
    assert result.traffic[0].request.body == {'title': 'neutral'}
    part = actual_file(api.requests[0])
    assert part.get_filename() == '' and part.get_payload(decode=True) == b''


def test_fill_cannot_expand_into_multipart_submission(setup):
    from dataclasses import replace
    support, context, api = setup(script()+";document.querySelector('#entry').oninput=()=>send()",
        inputs='<input id="upload" type="file" name="attachment"><input id="entry">')
    select(support, context)
    p = replace(permit('fill'), value='text')
    with pytest.raises(RuntimeError, match='browser action'):
        support.perform(context, p, selector='#entry')
    assert context.closed and api.requests == []


def _raw_upload_script(payload):
    import base64
    import json
    raw = (b'--boundary\r\nContent-Disposition: form-data; name="attachment"; filename="sample.bin"\r\n'
           b'Content-Type: application/octet-stream\r\n\r\n'+payload+b'\r\n--boundary--\r\n')
    script = ("go.onclick=async()=>{const body=Uint8Array.from(atob("+json.dumps(base64.b64encode(raw).decode())
              +"),c=>c.charCodeAt(0));await fetch(api+'/api/upload',{method:'POST',headers:{'Content-Type':'multipart/form-data; boundary=boundary'},body})}")
    return raw, script


@pytest.mark.parametrize('embedded', [b'\r\n--boundary--\r\n', b'\r\n--boundary \t\r\n',
                                      b'\r\n--boundary-- \t\r\n', b'\n--boundary\n'])
def test_native_ambiguous_multipart_never_reports_server_framing_as_file_bytes(setup, embedded):
    raw, app_script = _raw_upload_script(b'first'+embedded+b'not-a-file-part')
    independent = BytesParser(policy=policy.default).parsebytes(
        b'Content-Type: multipart/form-data; boundary=boundary\r\n\r\n'+raw)
    assert next(independent.iter_parts()).get_payload(decode=True) == b'first'
    support, context, api = setup(app_script)
    select(support, context)
    with pytest.raises(RuntimeError, match='browser action'):
        click(support, context)
    assert context.closed and api.requests == []


def test_native_literal_near_boundary_binary_matches_actual_server(setup):
    payload = b'\0\xff\r\n--boundaryX\r\n--boundary--X\r\n--boundary-X\r\nlast'
    raw, app_script = _raw_upload_script(payload)
    support, context, api = setup(app_script)
    select(support, context, upload(payload))
    result = click(support, context)
    assert api.requests[0]['body'] == raw
    assert result.traffic[0].request.files['attachment'].data == actual_file(api.requests[0]).get_payload(decode=True) == payload


def test_later_click_awaiting_selection_created_promise_keeps_click_ownership(setup):
    support, context, api = setup(script()+";let ready;upload.onchange=()=>{ready=Promise.resolve()};go.onclick=async()=>{await ready;await send()}")
    select(support, context)
    result = click(support, context)
    assert len(result.traffic) == len(api.requests) == 1
    assert result.traffic[0].action_id == result.action_id
    assert result.traffic[0].request.files == {'attachment': upload()}
