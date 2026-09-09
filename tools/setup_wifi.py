#!/usr/bin/env python3
"""Local-only Wi-Fi setup form. Passwords are sent over USB, never logged."""
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs
from pathlib import Path
import argparse, html, json, secrets, time
import serial

PORT = 8788
SERIAL_PORT = None
CSRF = secrets.token_urlsafe(32)
STATUS = ''
PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Pip Wi-Fi setup</title>
<style>body{background:#edf0e5;color:#304333;font:16px system-ui;margin:0;padding:40px 20px}main{max-width:470px;margin:5vh auto;background:#fffef8;padding:32px;border-radius:24px}h1{font-size:32px;margin:0 0 14px}p{line-height:1.6;color:#66775a}label{display:block;margin:22px 0 8px}input,button{box-sizing:border-box;width:100%;font:inherit;padding:13px;border:1px solid #d8dfce;border-radius:10px}button{background:#49643e;color:white;margin-top:25px;cursor:pointer}small{display:block;color:#7d8873;margin-top:20px;line-height:1.6}.status{background:#edf3e3;border-radius:10px;padding:12px}</style>
<main><h1>Get Pip online.</h1><p>Connect your ESP32 to a 2.4 GHz Wi-Fi network. Keep the USB cable connected while saving.</p>STATUS
<form method="post" action="/configure"><input type="hidden" name="csrf" value="CSRF"><label for="ssid">Wi-Fi network name</label><input id="ssid" name="ssid" maxlength="32" required autocomplete="off"><label for="password">Wi-Fi password</label><input id="password" name="password" type="password" maxlength="63" autocomplete="off"><button>Save to Pip and reconnect</button></form><small>The password goes directly to your ESP32 over USB and is stored on the device. It is never printed, sent to OpenAI, or saved by this page.</small></main></html>'''
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def allowed(self):
        return self.headers.get('Host') in (f'127.0.0.1:{PORT}', f'localhost:{PORT}')
    def send(self, status, body):
        b=body.encode(); self.send_response(status)
        self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(b)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if not self.allowed(): return self.send(403,'Host denied')
        if self.path != '/': return self.send(404,'Not found')
        status = '<p class="status" role="status">'+html.escape(STATUS)+'</p>' if STATUS else ''
        self.send(200,PAGE.replace('STATUS',status).replace('CSRF',CSRF))
    def do_POST(self):
        global STATUS
        origin=self.headers.get('Origin')
        if not self.allowed() or origin not in (f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'):
            return self.send(403,'Origin denied')
        if self.path != '/configure': return self.send(404,'Not found')
        try: length=int(self.headers.get('Content-Length','0'))
        except ValueError: return self.send(400,'Invalid request')
        if not 0 < length <= 2048: return self.send(413,'Invalid request size')
        data=parse_qs(self.rfile.read(length).decode(),keep_blank_values=True)
        if not secrets.compare_digest(data.get('csrf',[''])[0],CSRF): return self.send(403,'Reload the setup form')
        ssid=data.get('ssid',[''])[0]; password=data.get('password',[''])[0]
        if not 0 < len(ssid.encode()) <= 32 or len(password.encode()) > 63: return self.send(400,'Invalid Wi-Fi name or password length')
        try:
            s=serial.Serial(port=None,baudrate=115200,timeout=.25)
            s.dtr=False; s.rts=False; s.port=SERIAL_PORT; s.open()
            time.sleep(3)
            s.write((json.dumps({'action':'configure','ssid':ssid,'password':password})+'\n').encode()); s.flush()
            ssid=password=''; data.clear()
            end=time.monotonic()+8; saved=False
            while time.monotonic()<end:
                if s.readline().strip()==b'PIP_CONFIG_SAVED': saved=True; break
            s.close()
            STATUS='Wi-Fi settings saved. Pip is restarting. Return to the companion page in a few seconds.' if saved else 'No acknowledgement from Pip. Check that the flashed pet is running and try again.'
        except Exception:
            STATUS='Could not open Pip over USB. Close any serial monitor, check the cable, then retry.'
        self.send_response(303); self.send_header('Location','/'); self.end_headers()
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, help='USB serial port')
    parser.add_argument('--http-port', type=int, default=8788)
    args=parser.parse_args()
    SERIAL_PORT=args.port; PORT=args.http_port
    print(f'Pip local Wi-Fi setup: http://127.0.0.1:{PORT}',flush=True)
    HTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
