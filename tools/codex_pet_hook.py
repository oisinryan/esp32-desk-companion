#!/usr/bin/env python3
"""Codex observer hook. No decisions, chat storage, network, or transcript access."""
import hashlib, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVENTS = {
    'SessionStart':'idle', 'UserPromptSubmit':'running',
    'PreToolUse':'running', 'PostToolUse':'running',
    'PermissionRequest':'waiting', 'PreCompact':'running',
    'PostCompact':'running', 'Stop':'ready', 'Interrupt':'idle',
    'SessionEnd':'closed',
}

def sanitize(body):
    event = body.get('hook_event_name')
    session = body.get('session_id')
    if event not in EVENTS or not isinstance(session,str) or not 1 <= len(session) <= 200:
        return None
    status = EVENTS[event]
    # Inspect the tool *name* only; never tool arguments, results or messages.
    if event == 'PreToolUse' and body.get('tool_name','').endswith(('request_user_input','request_user_input_async')):
        status = 'waiting'
    if event == 'PostToolUse' and body.get('tool_name','').endswith('request_user_input_async'):
        return None # The asynchronous question remains pending.
    return {'session':hashlib.sha256(session.encode()).hexdigest()[:32],
            'status':status, 'at':int(time.time()*1000), 'event':event}

def main():
    try:
        # Consume hook input only in memory; discard all non-allowlisted fields.
        raw=sys.stdin.buffer.read(2*1024*1024+1)
        if len(raw)>2*1024*1024: return
        event=sanitize(json.loads(raw))
        if event is None: return
        folder=ROOT/'runtime/codex-events'; folder.mkdir(mode=0o700,parents=True,exist_ok=True)
        target=folder/(event['session']+'.json')
        temp=target.with_suffix(f'.{os.getpid()}.tmp')
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f: json.dump(event,f)
        os.replace(temp,target)
    except Exception:
        pass # An unavailable pet must never interfere with Codex.
    finally:
        print('{}') # Stop requires JSON; this makes no control decisions.

if __name__=='__main__': main()
