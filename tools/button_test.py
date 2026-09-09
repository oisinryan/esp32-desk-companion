#!/usr/bin/env python3
"""Exercise the hardware's navigation handler over USB, then Wi-Fi to Codex.
GPIO presses themselves need a human; debounce/hold logic has a native test.
"""
import json,time,urllib.request
from pathlib import Path
import serial
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', required=True)
args=parser.parse_args()

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8787'
def api(path,body=None):
    headers={'Origin':BASE,'Content-Type':'application/json'}
    req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    with urllib.request.urlopen(req,timeout=5) as r:return json.load(r)

state=api('/api/desktop')
original=state['selectedTask']
assert original, 'Open a named task first'
assert sum(time.time()*1000-t['updatedAt']<120000 for t in state['tasks'])>=2, 'Two recently active tasks are needed'
(ROOT/'artifacts').mkdir(exist_ok=True)
api('/api/desktop/select',{'key':original['key']})
s=serial.Serial(port=None,baudrate=115200,timeout=.3)
s.dtr=False;s.rts=False;s.port=args.port;s.open();time.sleep(3)
results=[]
try:
    for action in ['next','next','auto']:
        s.reset_input_buffer();s.write(json.dumps({'action':action}).encode()+b'\n')
        deadline=time.monotonic()+15;lines=[]
        while time.monotonic()<deadline:
            line=s.readline().decode(errors='replace').strip()
            if line.startswith(('CODEY_BUTTON ','CODEY_NAV_ACK ')):lines.append(line)
            if line.startswith('CODEY_NAV_ACK '):
                assert 'ok=1' in line,line
                break
        else:raise AssertionError(f'No successful device navigation acknowledgement: {lines}')
        current=api('/api/desktop')
        results.append({'action':action,'selected':current['selectedTask']['title'],
                        'manual':current['manualSelection'],'serial':lines})
        print(action, '->', current['selectedTask']['title'], 'manual=', current['manualSelection'])
    assert results[0]['selected']!=original['title']
    assert results[0]['manual'] and results[1]['manual'] and not results[2]['manual']
    (ROOT/'artifacts/codey-button-test.json').write_text(json.dumps(results,indent=2)+'\n')
finally:s.close()
