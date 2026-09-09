#!/usr/bin/env python3
"""USB diagnostics and Wi-Fi setup. Never prints Wi-Fi credentials."""
import argparse, getpass, json, time
import serial
p = argparse.ArgumentParser()
p.add_argument('action', choices=['status','pet','feed','play','sleep','wake','scan','configure'])
p.add_argument('--port', required=True)
p.add_argument('--ssid')
a = p.parse_args()
s = serial.Serial(port=None, baudrate=115200, timeout=.25)
s.dtr = False; s.rts = False; s.port = a.port; s.open()
time.sleep(3)
body = {'action': a.action}
if a.action == 'configure':
    body['ssid'] = a.ssid or input('Wi-Fi name (SSID): ')
    body['password'] = getpass.getpass('Wi-Fi password (not displayed): ')
    if not 0 < len(body['ssid'].encode()) <= 32 or len(body['password'].encode()) > 63:
        raise SystemExit('SSID must be 1–32 bytes and password at most 63 bytes.')
s.write((json.dumps(body)+'\n').encode()); s.flush()
body.clear()
if a.action not in ['configure','status']:
    time.sleep(.1); s.write(b'{"action":"status"}\n')
end = time.monotonic()+8
while time.monotonic()<end:
    line = s.readline().decode('utf8','replace').strip()
    if line.startswith(('PIP_STATUS','PIP_IP','PIP_SCAN','PIP_CONFIG','Pip ST7789','Pip OLED')):
        print(line)
s.close()
