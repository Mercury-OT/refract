"""Pinned, already-focused Enter delivery and a bounded document guard."""

from refracto import ports


_ARM = """({selector, actionId}) => {
    const state = window.__refractBrowser;
    const lookup = () => {
        const matches = [...document.querySelectorAll(selector)].filter(element => {
            const style = getComputedStyle(element), rect = element.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.visibility !== 'collapse' &&
                rect.width > 0 && rect.height > 0;
        });
        if (matches.length !== 1) throw new Error('keyboard target unavailable');
        const element = matches[0];
        if (!(element instanceof HTMLInputElement) ||
            !['text', 'search'].includes(element.type) || element.matches(':disabled') ||
            element.closest('[aria-disabled="true"], [inert]') ||
            element.getAttribute('aria-readonly') === 'true' ||
            element.readOnly || !element.isConnected || element.ownerDocument !== document ||
            document.activeElement !== element)
            throw new Error('keyboard target unavailable');
        return element;
    };
    const control = lookup();
    const form = control.form;
    // Chromium's default submitter is the first form-owned submit control in
    // document order, including external controls with a form attribute.
    const defaultButton = () => [...document.querySelectorAll('button,input')].find(button =>
        button.form === form && (button instanceof HTMLButtonElement && button.type === 'submit' ||
        button instanceof HTMLInputElement && ['submit', 'image'].includes(button.type))) || null;
    const button = form ? defaultButton() : null;
    let activation = null, submission = null;
    const currentForm = () => form instanceof HTMLFormElement && form.isConnected &&
        form.ownerDocument === document && control.form === form && defaultButton() === button &&
        (button instanceof HTMLButtonElement || button instanceof HTMLInputElement) &&
        button.type === 'submit' && button.isConnected && !button.matches(':disabled') &&
        !button.closest('[aria-disabled="true"], [inert]');
    const seen = new WeakSet();
    let keypresses = 0;
    const result = {key: 'Enter', target_matches: 1, focused: true,
        keydown_count: 0, keyup_count: 0};
    const arm = {type: 'press', action_id: actionId, control};
    arm.guard = event => {
        if (['click', 'submit'].includes(event.type)) {
            if (lookup() !== control || !event.isTrusted) return false;
            if (seen.has(event)) return true;
            if (!currentForm()) return false;
            if (result.keydown_count !== 1 || result.keyup_count || keypresses !== 1) return false;
            if (event.type === 'click') {
                if (activation || event.target !== button || event.detail !== 0 || event.button !== 0 ||
                    event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return false;
                activation = event;
            } else {
                if (submission || !activation || activation.defaultPrevented ||
                    event.target !== form || event.submitter !== button) return false;
                submission = event;
            }
            seen.add(event);
            return true;
        }
        if (lookup() !== control || event.target !== control || !event.isTrusted ||
            event.key !== 'Enter' || event.code !== 'Enter' || event.location !== 0 ||
            event.repeat || event.isComposing || event.altKey || event.ctrlKey ||
            event.metaKey || event.shiftKey) return false;
        if (seen.has(event)) return true;
        if (event.type === 'keydown') {
            if (result.keydown_count || result.keyup_count) return false;
            result.keydown_count++;
        } else if (event.type === 'keypress') {
            if (result.keydown_count !== 1 || result.keyup_count || keypresses) return false;
            keypresses++;
        } else if (event.type === 'keyup') {
            if (result.keydown_count !== 1 || result.keyup_count) return false;
            result.keyup_count++;
        } else return false;
        seen.add(event);
        return true;
    };
    arm.finish = () => {
        if (window.__refractBrowser !== state || state.armed !== arm ||
            state.errors.length || lookup() !== control ||
            result.keydown_count !== 1 || result.keyup_count !== 1 ||
            submission && !submission.defaultPrevented)
            throw new Error('keyboard delivery unavailable');
        // Validation or a cancelled click may prevent submit altogether. A
        // key receipt then carries no form request; core checks declared needs.
        // For an observed submit, require product cancellation after dispatch.
        // Navigation-guard cancellation is a different event and cannot fill it.
        return {...result};
    };
    state.armed = arm;
    state.event = null;
    return arm;
}"""


class PinnedKeyPress:
    """Retain the actual DOM object; neither select a replacement nor focus it."""

    def __init__(self, page, selector, action_id):
        self.arm = page.evaluate_handle(_ARM, {"selector": selector, "actionId": action_id})

    def receipt(self):
        value = self.arm.evaluate("""arm => {
            const value = arm.finish(), state = window.__refractBrowser;
            state.armed = null;
            state.event = null;
            state.origin = null;
            return value;
        }""")
        if (type(value) is not dict or set(value) != {
                "key", "target_matches", "focused", "keydown_count", "keyup_count"}
                or value["key"] != "Enter" or value["focused"] is not True
                or any(type(value[name]) is not int or value[name] != 1
                       for name in ("target_matches", "keydown_count", "keyup_count"))):
            raise RuntimeError("browser keyboard receipt unavailable")
        return ports.UiKeyPress(**value)

    def close(self):
        self.arm.dispose()


class KeyPressBoundary:
    """Reject unsupported transitions during press and its following idle gap.

    The next authorized primitive resumes its own existing navigation rules.
    A successful receipt cannot prove that an unbounded future timer is safe.
    """

    def __init__(self, context):
        self.context = context
        self.protected = False
        self.session = context.browser_context.new_cdp_session(context.page)
        for event in ("Page.frameRequestedNavigation", "Page.frameStartedNavigating",
                      "Page.frameNavigated", "Page.navigatedWithinDocument",
                      "Page.frameAttached"):
            self.session.on(event, self._transition)
        self.session.on("Network.requestWillBeSent", self._request)
        context.browser_context.on("page", self._page)
        context.page.on("download", self._transition)
        self.session.send("Page.enable")
        self.session.send("Network.enable")

    def _transition(self, _):
        if self.protected:
            self.context.errors.append("browser keyboard transition is unsupported")

    def _request(self, event):
        if event.get("type") == "Document":
            self._transition(event)

    def _page(self, page):
        if page is not self.context.page:
            self._transition(page)

    def begin(self):
        if len(self.context.page.frames) != 1 or len(self.context.browser_context.pages) != 1:
            raise RuntimeError("browser keyboard document is unavailable")
        self.protected = True

    def check(self):
        # Browser reads pump protocol events, so inspect the host ledger after
        # the final DOM receipt read as well as the ordinary helper checks.
        if self.context.errors:
            raise RuntimeError("browser keyboard boundary failed")
