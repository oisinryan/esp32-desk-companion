#!/usr/bin/env python3
"""Inject explicitly synthetic lifecycle events and verify the physical ESP32.

This proves hook script -> service -> Wi-Fi -> device, not Codex hook trust.
"""
import hashlib,json,subprocess,time,urllib.request
from pathlib import Path
import serial
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', required=True)
args=parser.parse_args()
Path('artifacts').mkdir(exist_ok=True)

ROOT=Path(__file__).resolve().parents[1]
session='codey-hardware-test-synthetic'
event_file=ROOT/'runtime/codex-events'/f'{hashlib.sha256(session.encode()).hexdigest()[:32]}.json'
s=serial.Serial(port=None,baudrate=115200,timeout=.4)
s.dtr=False;s.rts=False;s.port=args.port;s.open()
evidence=[]
def status():
    s.reset_input_buffer();s.write(b'{"action":"status"}\n')
    deadline=time.monotonic()+2; out={}
    while time.monotonic()<deadline:
        line=s.readline().decode(errors='replace').strip()
        if line.startswith('CODEY_STATUS ') or line.startswith('PIP_STATUS '):
            out.update(dict(v.split('=',1) for v in line.split()[1:]))
        if line.startswith('PIP_IP '):break
    return out
try:
    time.sleep(3)
    for event,expected in [('UserPromptSubmit','running'),('PermissionRequest','waiting'),('Stop','ready'),('Interrupt','idle')]:
        body={'session_id':session,'hook_event_name':event,'prompt':'TEST_CONTENT_MUST_NOT_BE_STORED'}
        p=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/codex_pet_hook.py')],input=json.dumps(body).encode(),capture_output=True)
        assert p.returncode==0 and p.stdout.strip()==b'{}'
        assert 'TEST_CONTENT' not in event_file.read_text()
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            sample=status()
            if sample.get('state')==expected and sample.get('linked')=='1':break
            time.sleep(.7)
        else:raise AssertionError(f'{expected} not received: {sample}')
        assert sample.get('wifi')=='3' and sample.get('bridge')=='1'
        evidence.append({'syntheticEvent':event,'expected':expected,'device':sample})
        print(event,'->',expected,'verified on ESP32')
    assert int(evidence[-1]['device']['uptime']) > int(evidence[0]['device']['uptime'])
    (ROOT/'artifacts/codey-hardware-test.json').write_text(json.dumps(evidence,indent=2)+'\n')
finally:
    s.close(); event_file.unlink(missing_ok=True)
