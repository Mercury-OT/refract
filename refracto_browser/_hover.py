"""One real pointer movement to a pinned, visible main-document DOM control."""

from refracto import ports


_ARM = """({selector, actionId}) => {
    const state = window.__refractBrowser;
    const lookup = () => {
        const matches = [...document.querySelectorAll(selector)].filter(element => {
            const style = getComputedStyle(element), rect = element.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.visibility !== 'collapse' &&
                rect.width > 0 && rect.height > 0;
        });
        if (matches.length !== 1) throw new Error('hover target unavailable');
        const control = matches[0];
        if (!control.isConnected || control.ownerDocument !== document)
            throw new Error('hover target unavailable');
        return control;
    };
    const control = lookup(), rect = control.getBoundingClientRect();
    // One integer CSS-pixel point, without scrolling or searching for a gap
    // around an overlay. Tiny/obscured/offscreen centers are outside this slice.
    const x = Math.floor(rect.left + rect.width / 2);
    const y = Math.floor(rect.top + rect.height / 2);
    const hit = () => {
        const element = document.elementFromPoint(x, y);
        return element === control || control.contains(element);
    };
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight ||
        x < rect.left || x >= rect.right || y < rect.top || y >= rect.bottom || !hit())
        throw new Error('hover target unavailable');
    let observed = false, invalid = false;
    const onmove = event => {
        if (!event.isTrusted) return;
        try {
            if (lookup() !== control || event.buttons !== 0 ||
                !(event.target === control || control.contains(event.target)) ||
                event.clientX !== x || event.clientY !== y || !hit())
                throw new Error('hover delivery changed');
            observed = true;
        } catch (_) { invalid = true; }
    };
    window.addEventListener('mousemove', onmove, true);
    const arm = {type: 'hover', action_id: actionId, x, y};
    arm.finish = () => {
        if (window.__refractBrowser !== state || state.armed !== arm ||
            state.errors.length || !observed || invalid || lookup() !== control || !hit())
            throw new Error('hover delivery unavailable');
        return {target_matches: 1, pointer_on_target: true};
    };
    arm.close = () => {
        window.removeEventListener('mousemove', onmove, true);
        if (state.armed === arm) {
            state.armed = null;
            state.event = null;
            state.origin = null;
        }
    };
    state.armed = arm;
    state.event = null;
    return arm;
}"""


class PinnedHover:
    """Pin one DOM object; never reselect, scroll, click or repair focus."""

    def __init__(self, page, selector, action_id, remaining):
        page.wait_for_function("""selector => [...document.querySelectorAll(selector)].some(element => {
            const style = getComputedStyle(element), rect = element.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.visibility !== 'collapse' &&
                rect.width > 0 && rect.height > 0;
        })""", arg=selector, timeout=remaining())
        self.arm = page.evaluate_handle(_ARM, {"selector": selector, "actionId": action_id})
        self.position = self.arm.evaluate("arm => ({x: arm.x, y: arm.y})")

    def receipt(self):
        value = self.arm.evaluate("arm => arm.finish()")
        if (type(value) is not dict or set(value) != {"target_matches", "pointer_on_target"}
                or type(value["target_matches"]) is not int or value["target_matches"] != 1
                or value["pointer_on_target"] is not True):
            raise RuntimeError("browser hover receipt unavailable")
        return ports.UiHover(**value)

    def close(self):
        try:
            self.arm.evaluate("arm => arm.close()")
        finally:
            self.arm.dispose()
