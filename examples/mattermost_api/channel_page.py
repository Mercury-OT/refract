"""Live page mappings for the disposable, fixed-version private-channel pilot."""
import copy
import re
from urllib.parse import urlsplit
from uuid import uuid4

from refracto import ports
from refracto.errors import ActionFailure, ActionFailureReason
from refracto_browser import ApiEndpoint, BackgroundWebSocket, BrowserNetworkPolicy, BrowserSupport, ResourceRoute


class ChannelPageAuth(ports.Authenticator):
    """Reuse one independently verified ordinary member's browser session."""

    def __init__(self, member_id, storage_state):
        self.member_id = member_id
        self._state = copy.deepcopy(storage_state)
        self._used = False

    def identify(self, user):
        if user != 'owner':
            raise ValueError('unknown pilot member')
        return self.member_id

    def session(self, user):
        principal = self.identify(user)
        if self._used:
            raise ValueError('another browser lease requires independent authentication')
        self._used = True
        return ports.UserSession(principal_id=principal, authentication_id=uuid4().hex,
                                 credentials={'storage_state': copy.deepcopy(self._state)})


# Observe one coherent DOM snapshot. The narrow timeline bounds are specific to
# this small, newly prepared channel. Neither the expected text nor the server
# response is available to the observer. Keep unreadable rows visible as gaps.
_READ_CHANNEL = r"""() => {
    const visible = e => e.checkVisibility({visibilityProperty: true, opacityProperty: true}) &&
        e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0;
    const views = [...document.querySelectorAll('#post-list[role="main"]')].filter(visible);
    const inputs = [...document.querySelectorAll('#create_post #post_textbox')].filter(visible);
    if (views.length !== 1 || inputs.length !== 1 || !(inputs[0] instanceof HTMLTextAreaElement)) {
        return false;
    }
    const lists = views[0].querySelectorAll('#postListContent #postListScrollContainer');
    if (lists.length !== 1 || !visible(lists[0])) return false;
    const list = lists[0];
    const atLatest = Math.abs(list.scrollHeight - list.clientHeight - list.scrollTop) <= 2;
    if (!atLatest || !list.querySelector('#channelIntro') ||
            list.querySelector('.loading__content:not(.hideAnimation), .more-messages-text')) {
        return false;
    }
    const directText = node => [...node.childNodes].some(n =>
        n.nodeType === Node.TEXT_NODE && n.textContent.trim() !== '');
    const inner = list.querySelectorAll(':scope > .innerList');
    if (inner.length !== 1 || directText(inner[0])) return false;
    const wrappers = inner[0].children;
    if (wrappers.length === 0 || wrappers.length > 100) return false;
    const posts = {identified: [], anonymous: []};
    let grouped = 0;
    let intros = 0;
    function isGroupedActivity(card, text) {
        const match = /^post_(user-activity-[a-z0-9]{26}(?:_[a-z0-9]{26})+)$/.exec(card.id);
        if (!match || !card.classList.contains('post--system')) return false;
        const compound = match[1];
        const ids = compound.slice('user-activity-'.length).split('_');
        if (new Set(ids).size !== ids.length) return false;
        const root = ':scope > .post__content[data-testid="postContent"]';
        if (card.querySelectorAll(root).length !== 1) return false;
        const content = root + ' > div';
        const bodies = card.querySelectorAll(content + ' > .post__body[data-testid="post-body"]');
        const links = card.querySelectorAll(content + ' > .post__header > div > a.post__permalink');
        return bodies.length === 1 && links.length === 1 &&
            bodies[0].parentElement === links[0].parentElement.parentElement.parentElement &&
            bodies[0].contains(text) && bodies[0].id === compound + '_message' &&
            text.id === 'postMessageText_' + compound && links[0].id === 'CENTER_time_' + compound;
    }
    for (const wrapper of wrappers) {
        // Inspect the actual row root. A class or ID embedded in rendered user
        // content cannot turn an unknown wrapper into a separator or system row.
        if (!wrapper.matches('div.item_measurer') || wrapper.children.length !== 1 || directText(wrapper)) return false;
        const padding = wrapper.firstElementChild;
        if (padding.tagName !== 'DIV' || padding.children.length !== 1 || directText(padding)) return false;
        const card = padding.firstElementChild;
        const roots = wrapper.querySelectorAll('.post, [data-testid="postView"]');
        if (card.matches('div#channelIntro.channel-intro') && !roots.length) {
            intros++;
            continue;
        }
        if (card.matches('div.Separator.BasicSeparator[data-testid="basicSeparator"]') && !roots.length) continue;
        if (!card.matches('div.post[data-testid="postView"]') || roots.length !== 1 || !visible(card)) return false;
        const bodies = card.querySelectorAll('[data-testid="post-message-text"]');
        if (bodies.length !== 1 || !visible(bodies[0])) return false;
        if (isGroupedActivity(card, bodies[0])) {
            grouped++;
            continue;
        }
        const fields = {message: bodies[0].innerText};
        const match = /^post_([a-z0-9]{26})$/.exec(card.id);
        if (match && bodies[0].id === 'postMessageText_' + match[1]) {
            fields.post_id = match[1];
            posts.identified.push({id: match[1], fields});
        } else {
            posts.anonymous.push({fields});
        }
    }
    if (intros !== 1) return false;
    return {
        'channel.view': {anonymous: [{fields: {path: location.pathname, grouped_activity_count: grouped}}]},
        'channel.composer': {anonymous: [{fields: {value: inputs[0].value}}]},
        'channel.posts': posts
    };
}"""


def read_rendered(page):
    # Wait only for observable loading, never for the expected message or ID.
    snapshot = page.wait_for_function(_READ_CHANNEL, timeout=8000, polling=100)
    try:
        return snapshot.json_value()
    finally:
        snapshot.dispose()


class ChannelPageUi(ports.UiDriver, ports.StepwiseUiDriver):
    def __init__(self, base_url, channel_path):
        origin = urlsplit(base_url)
        if (origin.scheme != 'http' or origin.hostname != '127.0.0.1' or not origin.port
                or origin.username or origin.password or origin.path or origin.query
                or origin.fragment or not re.fullmatch(r'/[a-z0-9_-]+/channels/[a-z0-9_-]+', channel_path)):
            raise ValueError('expected an isolated local channel page')
        self.channel_url = base_url + channel_path
        self.posts_url = base_url + '/api/v4/posts'
        self.observations = {}
        self.diagnostic_posts = []
        self.browser = BrowserSupport(base_url, read_rendered, timeout_ms=30000,
            network_policy=BrowserNetworkPolicy(
                api_endpoints=(ApiEndpoint(base_url, '/api/v4', ''),),
                credential_origins=(base_url,),
                resource_routes=(ResourceRoute(base_url, '/static/files'),),
                background_beacon_paths=('/api/v4/client_perf',),
                background_websockets=(BackgroundWebSocket('/api/v4/websocket',
                    query_keys=('connection_id', 'sequence_number', 'posted_ack')),)))

    def supports_stepwise_mode(self, mode):
        return mode == 'live'

    def open_stepwise(self, session, *, mode, mock_plan=None, mock_queue=None,
                      user=None, session_generation=0, context_id=''):
        if mode != 'live' or user != 'owner':
            raise ValueError('expected one ordinary live browser member')
        context = self.browser.open(mode, context_options=session, user=user,
                                    session_generation=session_generation, context_id=context_id)
        context.page.on('response', self._observe_post_status)
        return context

    def _observe_post_status(self, response):
        if (response.url == self.posts_url and response.request.method == 'POST'
                and len(self.diagnostic_posts) < 8):
            self.diagnostic_posts.append({'method': 'POST', 'path': '/api/v4/posts',
                                          'status': response.status})

    def perform_step(self, context, permit, *, business_header_names=()):
        observation = {'action': permit.action, 'target': permit.target,
                       'action_id': permit.action_id, 'context_id': permit.context_id}
        self.observations[permit.step_id] = observation
        self.browser.validate_request_header_names(context, business_header_names)
        if (permit.action, permit.target) == ('open', 'channel.page'):
            # The frame tree's loader identity changes on a full document load.
            # BrowserSupport owns navigation; this read-only session adds no action.
            inspector = context.browser_context.new_cdp_session(context.page)
            try:
                before = inspector.send('Page.getFrameTree')['frameTree']['frame']
                result = self.browser.perform(context, permit, url=self.channel_url)
                after = inspector.send('Page.getFrameTree')['frameTree']['frame']
                changed = (bool(after['loaderId']) and before['loaderId'] != after['loaderId']
                           and before['id'] == after['id'])
                observation.update(new_document=changed, frame_id=after['id'],
                                   document_before=before['loaderId'], document_after=after['loaderId'])
                if not changed:
                    raise ActionFailure(ActionFailureReason.EVIDENCE_INVALID)
            finally:
                if not context.closed:
                    inspector.detach()
        else:
            selector = {
                ('fill', 'channel.composer'): '#create_post #post_textbox',
                ('click', 'channel.send_button'): '#create_post button[data-testid="SendMessageButton"]',
            }[(permit.action, permit.target)]
            result = self.browser.perform(context, permit, selector=selector)
        evidence = result.evidence
        observation.update(rendered=copy.deepcopy(evidence.rendered), timeline_complete=True,
                           associated_count=len(evidence.traffic))
        return result

    def close_stepwise(self, context):
        self.browser.close(context)
