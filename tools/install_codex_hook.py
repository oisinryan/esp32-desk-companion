#!/usr/bin/env python3
"""Install observer definitions, preserving unrelated hooks. Never grants trust."""
import json, shlex, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from codex_pet_hook import EVENTS

command=shlex.quote(str(ROOT/'.venv/bin/python'))+' '+shlex.quote(str(ROOT/'tools/codex_pet_hook.py'))
target=Path.home()/'.codex/hooks.json'
data=json.loads(target.read_text()) if target.exists() else {}
hooks=data.setdefault('hooks',{})
for event in EVENTS:
    entries=hooks.setdefault(event,[])
    if not any(any(h.get('command')==command for h in entry.get('hooks',[])) for entry in entries):
        entries.append({'hooks':[{'type':'command','command':command,'timeout':3}]})
target.write_text(json.dumps(data,indent=2)+'\n')
print('Installed Codex pet observers. Review/trust these definitions in Codex Hooks; no trust settings were changed.')
