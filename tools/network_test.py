#!/usr/bin/env python3
"""Real-board Wi-Fi control and companion outage test. Uses local pairing config."""
import json, os, re, signal, subprocess, time, urllib.request
from pathlib import Path
import serial
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', required=True)
args=parser.parse_args()
Path('artifacts').mkdir(exist_ok=True)
config=dict(line.split('=',1) for line in Path('.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
base='http://127.0.0.1:'+config.get('PORT','8787')
def api(path, body=None):
    req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+config['PET_TOKEN'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=5) as r:return json.load(r)
def until(predicate,seconds=25):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        state=api('/api/state')
        if predicate(state):return state
        time.sleep(.5)
    raise AssertionError('Timed out waiting for real-device state')
s=serial.Serial(port=None,baudrate=115200,timeout=.25)
s.dtr=False;s.rts=False;s.port=args.port;s.open();time.sleep(2)
def status():
    s.reset_input_buffer();s.write(b'{"action":"status"}\n');end=time.monotonic()+4
    while time.monotonic()<end:
        line=s.readline().decode('utf8','replace').strip()
        if line.startswith('PIP_STATUS '):return {k:(int(v) if v.isdigit() else v) for k,v in re.findall(r'(\w+)=([^ ]+)',line)}
    raise AssertionError('No USB status')
# Wait for a fresh heartbeat after the expected serial-open reset.
start_ms=int(time.time()*1000)
state=until(lambda x:x['connected'] and x['lastSeen']>start_ms)
records=[]
def action(name,check):
    api('/api/action',{'action':name});r=until(lambda x:x['pending']==0 and check(x))
    report={k:r[k] for k in ['energy','fullness','joy','sleeping','mood','connected','pending']}
    records.append({'action':name,'state':report});print(name, json.dumps(report),flush=True);return r
state=action('wake',lambda x:not x['sleeping'])
state=action('sleep',lambda x:x['sleeping'])
state=action('wake',lambda x:not x['sleeping'])
fullness=state['fullness'];state=action('feed',lambda x:x['fullness']==min(100,fullness+20))
energy=state['energy'];joy=state['joy'];state=action('play',lambda x:x['energy']==max(0,energy-8) and x['joy']==min(100,joy+18))
joy=state['joy'];state=action('pet',lambda x:x['joy']==min(100,joy+12) and x['mood']=='love')
before=status();assert before['wifi']==3 and before['bridge']==1
pid=int(subprocess.check_output(['lsof','-tiTCP:'+config.get('PORT','8787'),'-sTCP:LISTEN'],text=True).strip())
command=subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True)
assert 'bridge/server.mjs' in command and '--demo' not in command
print('Pausing this companion for 10 seconds to test timeout recovery.',flush=True)
os.kill(pid,signal.SIGSTOP)
try:
    time.sleep(10);during=status();assert during['wifi']==3 and during['bridge']==0
finally:os.kill(pid,signal.SIGCONT)
resume_ms=int(time.time()*1000)
state=until(lambda x:x['connected'] and x['lastSeen']>resume_ms)
after=status()
# A queued, timed-out request can update server lastSeen immediately on resume.
# Wait for the ESP32 itself to acknowledge a successful response.
end=time.monotonic()+10
while after['bridge']!=1 and time.monotonic()<end:
    time.sleep(.5);after=status()
print('Outage diagnostics',json.dumps({'before':before,'during':during,'after':after}),flush=True)
assert after['bridge']==1 and after['uptime']>during['uptime']>before['uptime']
assert min(before['heap'],during['heap'],after['heap'])>20000
s.close()
result={'passed':True,'actions':records,'before_outage':before,'during_outage':during,'after_recovery':after}
Path('artifacts/network-test.json').write_text(json.dumps(result,indent=2))
print('PASS: Wi-Fi controls acknowledged; HTTP timeout detected; connection recovered without a board reset.',flush=True)
