"""Observed object selection against real Chromium and an independent HTTP peer."""

from dataclasses import FrozenInstanceError, replace
from html import escape
from urllib.parse import quote

import pytest

from refracto import ports
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport, ObjectTarget
from tests.browser.test_multi_origin_transport import Peer
from tests.browser.test_support import permit


LINK_ID = "row => Number(new URL(row.querySelector('a').href).pathname.split('/').pop())"
FORM_ID = "row => Number(new URL(row.querySelector('form').action).pathname.split('/').pop())"
STRING_ID = "row => decodeURIComponent(new URL(row.querySelector('a').href).pathname.split('/').pop())"


def row(identity, *, shape="link", controls=1, hidden=False):
    path = "/records/" + quote(str(identity), safe="")
    identity_markup = (f'<a href="{escape(path, quote=True)}">Details</a>' if shape == "link"
                       else f'<form action="{escape(path, quote=True)}"></form>')
    return ('<section class="record"' + (' hidden' if hidden else '') + '>' + identity_markup +
            '<span>Repeated display label</span>' +
            '<button class="edit"><span>Edit</span></button>' * controls + '</section>')


@pytest.fixture
def object_lab():
    resources = []

    def create(*, rows=None, native=False, mode="live", script="", mock_plan=None,
               request=True, awaited=False):
        peer = Peer()
        rows = row(11) + row(22) if rows is None else rows
        # IDs are ordinary detail links / form actions. No testing attribute is
        # inserted, and displayed labels intentionally cannot identify a row.
        peer.page = ('''<!doctype html><main>''' + rows + '''</main><script>
window.productClicks = 0;
document.addEventListener('click', ''' + ('async ' if awaited else '') + '''event => {
  const button = event.target.closest('button.edit');
  if (!button) return;
  window.productClicks++;
  const record = button.closest('.record');
  const link = record.querySelector('a'), form = record.querySelector('form');
  const identity = new URL(link ? link.href : form.action).pathname.split('/').pop();
  ''' + ('await Promise.resolve();' if awaited else '') +
            ("return fetch('/api/edit/' + identity).then(response => response.json());" if request else '') +
            '''});
''' + script + '</script>').encode()
        policy = (BrowserNetworkPolicy(api_endpoints=(ApiEndpoint(peer.url, '/api', 'api'),))
                  if native else None)
        support = BrowserSupport(peer.url, lambda page: {}, timeout_ms=5000, network_policy=policy)
        context = support.open(mode, mock_plan=mock_plan)
        resources.append((peer, support, context))
        support.perform(context, permit('open', mode=mode), url=peer.url + '/')
        return peer, support, context

    yield create
    for peer, support, context in reversed(resources):
        support.close(context)
        peer.close()


def click(support, context, identity=22, *, mapping=None, mode="live"):
    mapping = mapping or ObjectTarget('.record', 'button.edit', LINK_ID)
    return support.perform(context, replace(permit(mode=mode), object_id=identity),
                           object_target=mapping).evidence


def api_requests(peer):
    return [item for item in peer.requests if item['path'].startswith('/api/')]


@pytest.mark.parametrize('native', [False, True], ids=['legacy', 'native'])
@pytest.mark.parametrize('mode', ['live', 'mock'])
@pytest.mark.parametrize('shape,reader', [('link', LINK_ID), ('form', FORM_ID)])
def test_scoped_click_uses_actual_business_identity_in_live_and_mock(object_lab, native, mode, shape, reader):
    fixture = ports.MockResponse(fixture_id='edit', source='neutral expected response',
                                 method='GET', path='api/edit/22', response={'observed': 'mock'})
    peer, support, context = object_lab(rows=row(11, shape=shape) + row(22, shape=shape),
                                      native=native, mode=mode,
                                      mock_plan=[fixture] if mode == 'mock' else None)
    original_dom = context.page.locator('main').inner_html()
    evidence = click(support, context, mapping=ObjectTarget('.record', 'button.edit', reader), mode=mode)
    assert evidence.object_selection == ports.UiObjectSelection(object_id=22, object_matches=1, control_matches=1)
    assert context.page.evaluate('productClicks') == 1
    assert context.page.locator('main').inner_html() == original_dom
    assert [traffic.request.path for traffic in evidence.traffic] == ['api/edit/22']
    assert len(evidence.mock_recordings) == (1 if mode == 'mock' else 0)
    assert len(api_requests(peer)) == (0 if mode == 'mock' else 1)


@pytest.mark.parametrize('identity', [0, -7, 2**53 - 1, -(2**53 - 1)])
def test_exact_browser_integer_identity_including_zero(object_lab, identity):
    peer, support, context = object_lab(rows=row(identity))
    receipt = click(support, context, identity).object_selection
    assert type(receipt.object_id) is int and receipt.object_id == identity
    assert len(api_requests(peer)) == 1


def test_string_identity_is_data_not_css_or_javascript(object_lab):
    identity = "private-id-'\"[x], / +"
    peer, support, context = object_lab(rows=row(identity))
    mapping = ObjectTarget('.record', 'button.edit', STRING_ID)
    receipt = click(support, context, identity, mapping=mapping).object_selection
    assert receipt.object_id == identity and len(api_requests(peer)) == 1
    assert identity not in repr(receipt) and identity not in repr(mapping)


def test_scoped_click_without_request_still_has_observed_receipt(object_lab):
    peer, support, context = object_lab(request=False)
    evidence = click(support, context)
    assert evidence.object_selection.object_id == 22
    assert evidence.traffic == [] and api_requests(peer) == []
    assert context.page.evaluate('productClicks') == 1


@pytest.mark.parametrize('rows,reader,identity', [
    (row(11), LINK_ID, 22),
    (row(22, hidden=True), LINK_ID, 22),
    (row(22, controls=0), LINK_ID, 22),
    (row(22), STRING_ID, 22),
    (row(22), LINK_ID, '22'),
])
def test_unavailable_match_is_bounded_without_click(object_lab, rows, reader, identity):
    peer, support, context = object_lab(rows=rows)
    support._timeout_ms = 200
    with pytest.raises(RuntimeError, match='browser action or evidence collection failed'):
        click(support, context, identity, mapping=ObjectTarget('.record', 'button.edit', reader))
    assert context.closed and api_requests(peer) == []


@pytest.mark.parametrize('rows,reader', [
    (row(22) + row(22), LINK_ID),
    (row(22, controls=2), LINK_ID),
    (row(22) + '<section class="record">Unknown identity</section>', LINK_ID),
    (row(22), 'row => null'),
    (row(22), 'row => true'),
    (row(22), 'row => ({id: 22})'),
    (row(22), 'row => NaN'),
    (row(22), 'row => 9007199254740992'),
    (row(22), 'function(row) { return this?.id; }'),
    (row(22), 'row => { throw new Error("sensitive-reader-error") }'),
    (row(22), '42'),
])
def test_ambiguous_or_unreadable_identity_never_becomes_a_nonmatch(object_lab, rows, reader):
    peer, support, context = object_lab(rows=rows)
    with pytest.raises(RuntimeError) as error:
        click(support, context, mapping=ObjectTarget('.record', 'button.edit', reader))
    assert 'sensitive-reader-error' not in str(error.value)
    assert context.closed and api_requests(peer) == []


@pytest.mark.parametrize('identity', [True, False, None, '', [], {}, 22.0, 2**53, -(2**53)])
def test_unsupported_permit_identity_is_rejected_before_dom_or_action(object_lab, identity):
    peer, support, context = object_lab()
    with pytest.raises(ValueError):
        click(support, context, identity)
    assert context.page.evaluate('productClicks') == 0 and api_requests(peer) == []


@pytest.mark.parametrize('initial,addition', [
    (row(11), row(22)), (row(22, controls=0), '<button class="edit">Edit</button>'),
])
def test_readiness_waits_passively_for_row_or_control(object_lab, initial, addition):
    peer, support, context = object_lab(rows=initial)
    selector = 'main' if initial == row(11) else '.record'
    context.page.evaluate('''({selector, addition}) => setTimeout(() =>
        document.querySelector(selector).insertAdjacentHTML('beforeend', addition), 30)''',
                          {'selector': selector, 'addition': addition})
    assert click(support, context).object_selection.object_id == 22
    assert context.page.evaluate('productClicks') == 1 and len(api_requests(peer)) == 1


@pytest.mark.parametrize('change', [
    "record.querySelector('a').href='/records/33'",
    "document.querySelector('main').append(record.cloneNode(true))",
    "record.append(button.cloneNode(true))",
    "record.replaceWith(record.cloneNode(true))",
    "button.replaceWith(button.cloneNode(true))",
])
def test_dom_changes_during_pointer_events_cannot_redirect_click(object_lab, change):
    script = '''document.addEventListener('pointerdown', event => {
      const button = event.target.closest('button.edit');
      if (!button) return;
      const record = button.closest('.record');
    ''' + change + '; });'
    peer, support, context = object_lab(script=script)
    dispatched = []
    context.page.expose_function('observeProductClick', lambda: dispatched.append(True))
    context.page.evaluate("document.addEventListener('click', () => observeProductClick())")
    with pytest.raises(RuntimeError):
        click(support, context)
    assert dispatched == [] and api_requests(peer) == [] and context.closed


def test_handler_may_remove_selected_row_after_validated_click(object_lab):
    peer, support, context = object_lab(script="""document.addEventListener('click', event => {
      event.target.closest('.record')?.remove();
    });""")
    evidence = click(support, context)
    assert evidence.object_selection.object_id == 22
    assert len(api_requests(peer)) == 1 and context.page.locator('.record').count() == 1


def test_non_html_document_navigation_cannot_claim_a_selection_receipt(object_lab):
    peer, support, context = object_lab(request=False, script="""
      document.addEventListener('click', event => {
        if (event.target.closest('button.edit')) location.href = '/next-document';
      });""")
    with pytest.raises(RuntimeError, match='browser action or evidence collection failed'):
        click(support, context)
    assert context.closed and api_requests(peer) == []
    assert any(item['path'] == '/next-document' for item in peer.requests)


@pytest.mark.parametrize('rows,control', [('text=Repeated display label', 'button.edit'),
                                         ('.record', 'text=Edit')])
def test_only_native_css_is_accepted_for_mapping(object_lab, rows, control):
    peer, support, context = object_lab()
    with pytest.raises(RuntimeError):
        click(support, context, mapping=ObjectTarget(rows, control, LINK_ID))
    assert context.closed and api_requests(peer) == []


def test_nested_candidate_scope_cannot_borrow_another_objects_control(object_lab):
    rows = row(22, controls=0).replace('</section>', row(33) + '</section>')
    peer, support, context = object_lab(rows=rows)
    with pytest.raises(RuntimeError):
        click(support, context)
    assert context.closed and api_requests(peer) == []


def test_native_await_association_preserved_after_scoped_click(object_lab):
    peer, support, context = object_lab(native=True, awaited=True)
    evidence = click(support, context)
    assert evidence.object_selection.object_id == 22
    assert [traffic.request.path for traffic in evidence.traffic] == ['api/edit/22']
    assert len(api_requests(peer)) == 1


def test_mapping_is_explicit_and_exclusive_and_ordinary_click_has_no_receipt(object_lab):
    peer, support, context = object_lab()
    mapping = ObjectTarget('.record', 'button.edit', LINK_ID)
    scoped = replace(permit(), object_id=22)
    for candidate, options in [
        (scoped, {'selector': 'button.edit'}),
        (scoped, {'selector': 'button.edit', 'object_target': mapping}),
        (scoped, {'url': peer.url, 'object_target': mapping}),
        (permit(), {'object_target': mapping}),
        (replace(permit('fill', value='x'), object_id=22), {'object_target': mapping}),
    ]:
        with pytest.raises(ValueError):
            support.perform(context, candidate, **options)
    assert context.page.evaluate('productClicks') == 0
    evidence = support.perform(context, permit(), selector='.record:last-child button.edit').evidence
    assert evidence.object_selection is None and len(api_requests(peer)) == 1


@pytest.mark.parametrize('field', ['rows', 'control', 'read_id'])
@pytest.mark.parametrize('invalid', ['', ' ', None, 1])
def test_mapping_fields_require_nonempty_strings(field, invalid):
    values = dict(rows='.record', control='button.edit', read_id=LINK_ID)
    values[field] = invalid
    with pytest.raises(ValueError):
        ObjectTarget(**values)


def test_mapping_is_frozen_and_sensitive_fields_are_hidden():
    mapping = ObjectTarget('secret-rows', 'secret-control', 'secret-reader')
    with pytest.raises(FrozenInstanceError):
        mapping.rows = 'changed'
    assert repr(mapping) == 'ObjectTarget()'
