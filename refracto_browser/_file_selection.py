"""One pinned file input, populated only from the permit's immutable bytes."""
import base64
import hashlib
import mimetypes
import re
from pathlib import PurePath
from urllib.parse import unquote

from refracto import ports
from refracto.files import require_browser_file, require_files


_MIME = mimetypes.MimeTypes(filenames=())


def selection_ancestry(stack, permits):
    """Reject selection descendants; unsupported ownership edges grant no rights.

    Timer ancestry is useful only for denial, never for assigning a request to
    an action. Bound the scan exactly as native ownership bounds its ancestry.
    """
    seen = 0
    for _ in range(33):
        if type(stack) is not dict or type(stack.get('callFrames')) is not list:
            return False
        frames = stack['callFrames']
        seen += len(frames)
        if len(frames) > 128 or seen > 1024:
            return False
        for frame in frames:
            name = frame.get('functionName') if type(frame) is dict else None
            if type(name) is not str or len(name) > 4096:
                return False
            marker = re.fullmatch(r'__refract_invocation_[0-9a-f]{32}__(.*)', name)
            permit = permits.get(unquote(marker.group(1))) if marker else None
            if permit is not None and permit.action == 'select_file':
                return True
        stack = stack.get('parent')
    return False


_ARM = """({selector, actionId}) => {
    const state = window.__refractBrowser;
    const lookup = () => {
        const matches = [...document.querySelectorAll(selector)];
        if (matches.length !== 1) throw new Error('file target unavailable');
        const control = matches[0], style = getComputedStyle(control), rect = control.getBoundingClientRect();
        if (!(control instanceof HTMLInputElement) || control.type !== 'file' ||
            control.multiple || control.webkitdirectory || control.matches(':disabled') ||
            !control.isConnected || control.ownerDocument !== document ||
            style.visibility === 'hidden' || style.visibility === 'collapse' ||
            rect.width <= 0 || rect.height <= 0)
            throw new Error('file target unavailable');
        return control;
    };
    const control = lookup();
    const arm = {type: 'select_file', action_id: actionId, control};
    arm.check = () => {
        if (window.__refractBrowser !== state || state.armed !== arm || lookup() !== control)
            throw new Error('file target changed');
    };
    arm.read = async ({limit, timeout}) => {
        arm.check();
        if (control.files.length !== 1) throw new Error('file selection unavailable');
        const file = control.files[0];
        if (file.size > limit) throw new Error('file selection byte budget exceeded');
        let timer;
        try {
            const buffer = await Promise.race([file.arrayBuffer(), new Promise((_, reject) => {
                timer = setTimeout(() => reject(new Error('file read timeout')), timeout);
            })]);
            arm.check();
            if (control.files.length !== 1 || control.files[0] !== file || buffer.byteLength !== file.size)
                throw new Error('file selection changed');
            const bytes = new Uint8Array(buffer), chunks = [];
            for (let i = 0; i < bytes.length; i += 32768)
                chunks.push(String.fromCharCode(...bytes.subarray(i, i + 32768)));
            return {target_matches: 1, filename: file.name, data: btoa(chunks.join(''))};
        } finally { clearTimeout(timer); }
    };
    arm.close = () => {
        if (state.armed === arm) {state.armed = null;state.event = null;state.origin = null;}
    };
    state.armed = arm; state.event = null;
    return arm;
}"""


class PinnedFileSelection:
    def __init__(self, page, selector, action_id, remaining, config):
        self.remaining, self.config = remaining, config
        self.arm = page.evaluate_handle(_ARM, {'selector': selector, 'actionId': action_id})
        self.control = self.arm.get_property('control').as_element()
        if self.control is None:
            raise ValueError('browser file target unavailable')

    def select(self, file):
        require_browser_file(file)
        if len(file.data) > self.config.max_file_bytes:
            raise ValueError('browser file byte budget exceeded')
        self.expected = file
        suffix = PurePath(file.filename).suffix.lower()
        mime = _MIME.types_map[1].get(suffix, 'application/octet-stream')
        self.arm.evaluate('arm => arm.check()')
        self.control.set_input_files({'name': file.filename, 'mimeType': mime,
                                      'buffer': file.data}, timeout=self.remaining())

    def receipt(self):
        value = self.arm.evaluate('(arm, options) => arm.read(options)', {
            'limit': self.config.max_file_bytes, 'timeout': self.remaining()})
        if (type(value) is not dict or set(value) != {'target_matches', 'filename', 'data'}
                or type(value['target_matches']) is not int or value['target_matches'] != 1
                or type(value['filename']) is not str or type(value['data']) is not str
                or len(value['data']) > 4 * ((self.config.max_file_bytes + 2) // 3)):
            raise ValueError('browser file receipt unavailable')
        data = base64.b64decode(value['data'], validate=True)
        if len(data) > self.config.max_file_bytes:
            raise ValueError('browser file byte budget exceeded')
        file = ports.UploadFile(filename=value['filename'], data=data, sha256=hashlib.sha256(data).hexdigest())
        require_files({'file': file})
        if file != self.expected:
            raise ValueError('browser selected file changed')
        return ports.UiFileSelection(target_matches=1, file=file)

    def close(self):
        try:
            self.arm.evaluate('arm => arm.close()')
        finally:
            self.control.dispose()
            self.arm.dispose()
