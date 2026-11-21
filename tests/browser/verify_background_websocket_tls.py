"""Manual Linux container gate: python -B -m tests.browser.verify_background_websocket_tls.

Requires a disposable Docker container with Chromium, Playwright, openssl and
certutil installed. It never selects a certificate exception or browser flag.
"""
from contextlib import ExitStack
import json
from pathlib import Path
import pwd
import shutil
import ssl
import subprocess
import sys
import tempfile
from threading import Event
from uuid import uuid4

from refracto_browser import BackgroundWebSocket, BrowserNetworkPolicy, BrowserSupport
from tests.browser.socket_peer import SocketPeer


def run(*args, cwd=None):
    subprocess.run(args, cwd=cwd, stdout=subprocess.DEVNULL, check=True,
                   stderr=subprocess.PIPE, timeout=30)


def install_trial_certificates(tmp, cleanup):
    import os

    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    dirs = [home / '.pki/nssdb', home / '.local/share/pki/nssdb']
    mounts = [Path(line.split()[4]) for line in Path('/proc/self/mountinfo').read_text().splitlines()]
    if (not Path('/.dockerenv').is_file() or home != Path.home()
            or any(db != db.resolve() or any(m != Path('/') and (m.is_relative_to(db)
                   or db.is_relative_to(m)) for m in mounts) for db in dirs)):
        raise SystemExit('Use a disposable container with an unmounted, nonsymlink login home')
    req = ('openssl', 'req', '-newkey', 'rsa:2048', '-nodes')
    run(*req, '-x509', '-days', '1', '-subj', '/CN=EphemeralSocketTestCA',
        '-addext', 'basicConstraints=critical,CA:TRUE', '-keyout', 'ca.key', '-out', 'ca.pem', cwd=tmp)
    identity = ('-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1')
    run(*req, '-new', *identity, '-keyout', 'site.key', '-out', 'site.csr', cwd=tmp)
    run('openssl', 'x509', '-req', '-in', 'site.csr', '-days', '1', '-CA', 'ca.pem',
        '-CAkey', 'ca.key', '-CAcreateserial', '-copy_extensions', 'copy', '-out', 'site.pem', cwd=tmp)
    run(*req, '-x509', '-days', '1', *identity, '-keyout', 'unknown.key', '-out', 'unknown.pem', cwd=tmp)
    nickname = 'ephemeral-socket-' + uuid4().hex
    for db in dirs:
        db.mkdir(mode=0o700, parents=True, exist_ok=True)
        store = 'sql:' + str(db)
        if not (db / 'cert9.db').exists():
            run('certutil', '-N', '--empty-password', '-d', store)
        run('certutil', '-A', '-d', store, '-n', nickname, '-t', 'C,,', '-i', str(tmp / 'ca.pem'))
        cleanup.callback(run, 'certutil', '-D', '-d', store, '-n', nickname)


def server_tls(tmp, name):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.options |= ssl.OP_NO_TICKET
    ctx.load_cert_chain(tmp / (name + '.pem'), tmp / (name + '.key'))
    return ctx


def exercise(tmp, trust_socket):
    accepted, unknown = server_tls(tmp, 'site'), server_tls(tmp, 'unknown')
    switch = Event()
    tls_failures = []
    with SocketPeer() as peer:
        original = peer.server.get_request

        def accept():
            sock, address = original()
            try:
                tls = unknown if switch.is_set() else accepted
                return tls.wrap_socket(sock, server_side=True), address
            except OSError:
                tls_failures.append(switch.is_set())
                sock.close()
                raise

        peer.server.get_request = accept
        peer.url = peer.url.replace('http:', 'https:')
        peer.socket = peer.socket.replace('ws:', 'wss:')
        policy = BrowserNetworkPolicy(credential_origins=(peer.url,),
                                      background_websockets=(BackgroundWebSocket('/socket'),))
        helper = BrowserSupport(peer.url, lambda _: {}, timeout_ms=15000, network_policy=policy)
        ctx = helper.open('live')
        try:
            assert ctx.page.goto(peer.url).status == 200 and ctx.page.locator('#go').count() == 1
            if not trust_socket:
                switch.set()
            observed = ctx.page.evaluate("""url => new Promise(resolve => {
                const s = new WebSocket(url); let opened = false;
                const t = setTimeout(() => resolve('timeout'), 6000);
                const done = value => {clearTimeout(t); resolve(value)};
                s.onopen = () => {opened = true; s.send('receipt')};
                s.onmessage = event => {if (event.data === 'receipt') {s.close(); done('echo')}};
                s.onerror = () => done(opened ? 'opened-then-error' : 'error');
            })""", peer.socket)
        finally:
            helper.close(ctx)
        if trust_socket:
            assert observed == 'echo' and len(peer.upgrades) == 1 and peer.echoes == [b'receipt']
            assert peer.disconnected.wait(3)
        else:
            assert observed == 'error' and not peer.upgrades and not peer.echoes and any(tls_failures)
        return {'trusted': trust_socket, 'observed': observed, 'upgrades': len(peer.upgrades)}


def main():
    if (sys.platform != 'linux' or not Path('/.dockerenv').is_file() or not __debug__
            or not all(shutil.which(x) for x in ('openssl', 'certutil'))):
        raise SystemExit('Requires a disposable Linux Docker container, assertions, openssl and certutil')
    with tempfile.TemporaryDirectory() as fresh, ExitStack() as cleanup:
        tmp = Path(fresh)
        install_trial_certificates(tmp, cleanup)
        print(json.dumps([exercise(tmp, trust) for trust in (True, False, True, False)]))


if __name__ == '__main__':
    main()
