"""A loopback page/API/echo peer with independent handshake and close receipts."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import urlsplit


class SocketPeer:
    def __init__(self, tls=None):
        self.page = b'<!doctype html><button id="go">Read</button><button id="idle">Done</button>'
        self.upgrades = []
        self.echoes = []
        self.http_replies = []
        self.closed_count = 0
        self.disconnected = threading.Event()
        self.redirect = None
        peer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.headers.get('Upgrade', '').lower() == 'websocket':
                    return self.upgrade()
                path = urlsplit(self.path).path
                if path == '/api/read':
                    serial = len(peer.http_replies) + 1
                    peer.http_replies.append(serial)
                    body, kind = json.dumps({'serial': serial}).encode(), 'application/json'
                else:
                    body, kind = peer.page, 'text/html'
                self.send_response(200)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)

            def upgrade(self):
                peer.upgrades.append({'path': self.path, 'cookie': self.headers.get('Cookie'),
                                      'origin': self.headers.get('Origin'),
                                      'subprotocol': self.headers.get('Sec-WebSocket-Protocol')})
                self.close_connection = True
                if peer.redirect:
                    self.send_response(307)
                    self.send_header('Location', peer.redirect)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                key = self.headers['Sec-WebSocket-Key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
                self.send_response(101)
                self.send_header('Upgrade', 'websocket')
                self.send_header('Connection', 'Upgrade')
                self.send_header('Sec-WebSocket-Accept', base64.b64encode(hashlib.sha1(key.encode()).digest()).decode())
                self.end_headers()
                try:
                    self.connection.settimeout(20)
                    while True:
                        header = self.rfile.read(2)
                        if len(header) != 2:
                            break
                        opcode, size = header[0] & 15, header[1] & 127
                        if not header[1] & 128 or size > 125 or opcode not in {1, 8}:
                            raise AssertionError('unexpected synthetic client frame')
                        mask = self.rfile.read(4)
                        data = self.rfile.read(size)
                        if len(mask) != 4 or len(data) != size:
                            break
                        content = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
                        if opcode == 1:
                            peer.echoes.append(content)
                        self.wfile.write(bytes([128 | opcode, size]) + content)
                        self.wfile.flush()
                        if opcode == 8:
                            break
                except (ConnectionError, TimeoutError):
                    pass
                finally:
                    peer.closed_count += 1
                    peer.disconnected.set()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        if tls:
            self.server.socket = tls.wrap_socket(self.server.socket, server_side=True)
        self.url = ('https' if tls else 'http') + '://127.0.0.1:' + str(self.server.server_port)
        self.socket = self.url.replace('http', 'ws', 1) + '/socket'
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
