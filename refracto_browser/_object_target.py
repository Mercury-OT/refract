"""Read-only DOM selection and a final trusted-click identity guard."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ObjectTarget:
    """Product mapping; the identity reader receives an actual row only.

    The JavaScript reader is ordinary adapter code, not a sandbox. Desired IDs
    are passed separately as data and never interpolated into selectors/code.
    """

    rows: str = field(repr=False)
    control: str = field(repr=False)
    read_id: str = field(repr=False)

    def __post_init__(self):
        if any(type(value) is not str or not value.strip()
               for value in (self.rows, self.control, self.read_id)):
            raise ValueError("object target mapping requires nonempty strings")


def require_browser_id(value):
    if type(value) is str and value != "":
        return
    if type(value) is int and abs(value) <= 2 ** 53 - 1:
        return
    raise ValueError("browser object identity must be a string or safe integer")


_READER = """source => {
    // Indirect eval gives the adapter function no closure over the wanted ID.
    const read = (0, eval)('(' + source + ')');
    if (typeof read !== 'function') throw new Error('invalid identity reader');
    return read;
}"""

_LOOKUP = """() => config => {
    const visible = element => {
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.visibility !== 'hidden' && style.visibility !== 'collapse' &&
            rect.width > 0 && rect.height > 0;
    };
    const validId = value => (typeof value === 'string' && value !== '') ||
        (typeof value === 'number' && Number.isSafeInteger(value));
    // Native CSS rejects additional selector engines. Every visible row's ID
    // must be readable; an unknown identity is not a proven nonmatch.
    const rows = [...document.querySelectorAll(config.rows)].filter(visible);
    const matching = [];
    for (const row of rows) {
        // A method call would expose config (including the wanted ID) as `this`.
        // Adapter readers receive only the observed row, with no config receiver.
        const id = Reflect.apply(config.read, undefined, [row]);
        if (!validId(id)) throw new Error('object identity unavailable');
        if (typeof id === typeof config.id && id === config.id) matching.push({row, id});
    }
    if (matching.length > 1) throw new Error('object identity ambiguous');
    if (!matching.length) return null;
    const match = matching[0];
    const controls = [...match.row.querySelectorAll(config.control)].filter(visible);
    if (controls.length > 1) throw new Error('object control ambiguous');
    if (!controls.length) return null;
    const control = controls[0];
    // A nested candidate row must not lend its control to another object.
    if (rows.filter(row => row.contains(control)).length !== 1)
        throw new Error('object control scope ambiguous');
    return {row: match.row, control, id: match.id, object_matches: matching.length,
        control_matches: controls.length};
}"""

_ARM = """({config, selected, actionId}) => {
    const state = window.__refractBrowser;
    const arm = {action_id: actionId, type: 'click', selection: null, control: selected.control};
    arm.guard = event => {
        const current = config.lookup(config);
        if (!current || !selected.row.isConnected || !selected.control.isConnected ||
            current.row !== selected.row || current.control !== selected.control ||
            !(event.target instanceof Element) ||
            !(selected.control === event.target || selected.control.contains(event.target))) return false;
        // The receipt is observed again at dispatch, rather than echoing a permit.
        arm.selection = {object_id: current.id, object_matches: current.object_matches,
            control_matches: current.control_matches};
        return true;
    };
    state.armed = arm;
    state.event = null;
}"""


class PinnedObjectTarget:
    """Own browser handles only for the duration of one authorized click."""

    def __init__(self, page, mapping, object_id, action_id, remaining):
        self.handles = []
        try:
            read = page.evaluate_handle(_READER, mapping.read_id)
            self.handles.append(read)
            lookup = page.evaluate_handle(_LOOKUP)
            self.handles.append(lookup)
            config = {"rows": mapping.rows, "control": mapping.control, "read": read,
                      "lookup": lookup, "id": object_id}
            selected = page.wait_for_function("config => config.lookup(config)",
                                             arg=config, timeout=remaining())
            self.handles.append(selected)
            control = selected.get_property("control")
            self.handles.append(control)
            self.control = control.as_element()
            if self.control is None:
                raise ValueError("object control is unavailable")
            page.evaluate(_ARM, {"config": config, "selected": selected, "actionId": action_id})
        except Exception:
            self.close()
            raise

    def close(self):
        for handle in reversed(self.handles):
            try:
                handle.dispose()
            except Exception:
                # Context failure may already have disposed these handles.
                pass
        self.handles.clear()


def observed_selection(page, action_id):
    from refracto.ports import UiObjectSelection

    result = page.evaluate("""actionId => {
        const state = window.__refractBrowser;
        const arm = state?.armed;
        if (!arm || arm.action_id !== actionId || !state.event || !arm.selection)
            throw new Error('object click was not observed');
        return arm.selection;
    }""", action_id)
    require_browser_id(result["object_id"])
    return UiObjectSelection(**result)
