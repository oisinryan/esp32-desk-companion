#!/usr/bin/env python3
"""Capture the ESP32's rendered palette framebuffer, not a photograph of its panel."""
import argparse, binascii, struct, time, zlib
from pathlib import Path
import serial
p=argparse.ArgumentParser(); p.add_argument('--port',required=True); p.add_argument('--out',default='docs/pip-device-frame.png'); p.add_argument('--codey',action='store_true'); a=p.parse_args()
s=serial.Serial(port=None,baudrate=115200,timeout=1)
s.dtr=False;s.rts=False;s.port=a.port;s.open();time.sleep(2.5);s.reset_input_buffer();s.write(b'{"action":"frame"}\n')
end=time.monotonic()+8
while time.monotonic()<end:
    if s.readline().strip()==b'PIP_FRAME 170 320 54400':break
else:raise SystemExit('No framebuffer header from device')
data=bytearray();end=time.monotonic()+12
while len(data)<54400 and time.monotonic()<end:data.extend(s.read(54400-len(data)))
s.close()
if len(data)!=54400:raise SystemExit(f'Incomplete capture: {len(data)} bytes')
colors=[0xe9eee0,0xf9faec,0x293a32,0xc6e3a0,0x738266,0x92a873]
if a.codey:
    import json
    colors=json.loads(Path('artifacts/codey-palette.json').read_text())
if any(v>=len(colors) for v in data):
    from collections import Counter
    Path('artifacts/frame-raw.bin').write_bytes(data)
    raise SystemExit('Unexpected palette values: '+str(Counter(data).most_common(16)))
def chunk(name,content):return struct.pack('>I',len(content))+name+content+struct.pack('>I',binascii.crc32(name+content)&0xffffffff)
raw=bytearray()
for y in range(320):
    raw.append(0)
    for index in data[y*170:(y+1)*170]: raw.extend(colors[index].to_bytes(3,'big'))
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',170,320,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
Path(a.out).write_bytes(png);print(f'Captured device-rendered framebuffer: {a.out}')
