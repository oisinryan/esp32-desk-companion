#!/usr/bin/env python3
"""Exercise actual flashed lifecycle over USB. Does not simulate a device heartbeat."""
import json, re, time
from pathlib import Path
import serial
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', required=True)
args=parser.parse_args()
Path('artifacts').mkdir(exist_ok=True)
s=serial.Serial(port=None,baudrate=115200,timeout=.25)
s.dtr=False;s.rts=False;s.port=args.port;s.open();time.sleep(3)
results=[]
def status():
    s.write(b'{"action":"status"}\n');end=time.monotonic()+4
    while time.monotonic()<end:
        line=s.readline().decode('utf8','replace').strip()
        if line.startswith('PIP_STATUS '):
            result={k:(int(v) if v.isdigit() else v) for k,v in re.findall(r'(\w+)=([^ ]+)',line)}
            results.append(result);print(line,flush=True);return result
    raise RuntimeError('No device status')
def action(name):
    s.write((json.dumps({'action':name})+'\n').encode());time.sleep(.25);return status()
first=status()
assert action('sleep')['sleeping']==1
assert action('wake')['sleeping']==0
before=status();after=action('feed');assert after['fullness']==min(100,before['fullness']+20)
before=after;after=action('play');assert after['energy']==max(0,before['energy']-8)
assert after['joy']==min(100,before['joy']+18)
assert action('pet')['mood']=='love'
print('Lifecycle checks passed; observing 45 seconds of runtime.',flush=True)
for _ in range(9):time.sleep(5);status()
assert all(b['uptime']>a['uptime'] for a,b in zip(results,results[1:])), 'Device reset detected'
assert min(r['heap'] for r in results)>20000, 'Low heap'
s.close()
Path('artifacts/hardware-status.json').write_text(json.dumps({'passed':True,'samples':results},indent=2))
print('PASS: physical-device lifecycle, no reset during observation, heap above 20 KB.',flush=True)
