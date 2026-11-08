# -*- coding: utf-8 -*-
"""Приём фрагментов разметки HLTV из управляемого браузера: POST /save?name=X."""
import os
from http.server import BaseHTTPRequestHandler
from socketserver import TCPServer
from urllib.parse import urlparse, parse_qs

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hltv', 'fragments')


class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        u = urlparse(self.path)
        name = (parse_qs(u.query).get('name') or ['frag'])[0]
        name = ''.join(c for c in name if c.isalnum() or c in '-_')
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n)
        if not os.path.isdir(OUT):
            os.makedirs(OUT)
        with open(os.path.join(OUT, name + '.json'), 'wb') as f:
            f.write(body)
        self.send_response(200)
        self._cors()
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(('ok %d' % len(body)).encode())

    def log_message(self, *a):
        pass


TCPServer(('127.0.0.1', 8766), H).serve_forever()
