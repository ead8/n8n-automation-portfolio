#!/usr/bin/env python3
"""Mock outbound server (python port of mock-server.js, used for the actual test run
because the sandbox intermittently EPERMs write() syscalls from the node binary).
Identical protocol: POST /mock/email and /mock/slack append JSON body to
$HELPDESK_DATA_DIR/captures.jsonl and reply 200 {"ok": true}.
"""
import json, os, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

DATA_DIR = os.environ.get('HELPDESK_DATA_DIR', '/tmp/helpdesk-data')
CAPTURES = os.path.join(DATA_DIR, 'captures.jsonl')
os.makedirs(DATA_DIR, exist_ok=True)

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path not in ('/mock/email', '/mock/slack'):
            self.send_response(404); self.end_headers(); return
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length)
        try: body = json.loads(raw)
        except Exception: body = {'_raw': raw.decode('utf-8', 'replace')}
        rec = {'ts': datetime.datetime.utcnow().isoformat() + 'Z',
               'endpoint': self.path, 'body': body}
        with open(CAPTURES, 'a') as f:
            f.write(json.dumps(rec) + '\n')
        out = b'{"ok": true}'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)
    def log_message(self, *a): pass

if __name__ == '__main__':
    HTTPServer(('127.0.0.1', 8899), Handler).serve_forever()
    print('mock server on 8899')
