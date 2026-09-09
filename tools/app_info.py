#!/usr/bin/env python3
"""Read only public-facing task metadata from Codex's local task index.

Never queries messages, previews, transcripts, auth, or hook trust settings.
The SQLite connection is read-only. Schema changes fail closed.
"""
import hashlib,json,sqlite3,sys,time
from pathlib import Path

DB=Path.home()/'.codex/state_5.sqlite'
def snapshot(database=DB):
    with sqlite3.connect(f'file:{database}?mode=ro',uri=True,timeout=1) as db:
        db.execute('PRAGMA query_only=ON')
        rows=db.execute('''SELECT id,name,cwd,model,tokens_used,updated_at
            FROM threads WHERE archived=0 AND name IS NOT NULL AND name != ''
            AND (model IS NULL OR model NOT LIKE '%auto-review%')
            AND agent_role IS NULL
            ORDER BY updated_at DESC LIMIT 16''').fetchall()
    tasks=[]
    for ident,name,cwd,model,tokens,updated in rows:
        tasks.append({'key':hashlib.sha256(ident.encode()).hexdigest()[:32], 'threadId':ident,
            'title':str(name)[:100], 'project':('ChatGPT project' if Path(cwd).name.startswith('g-p-') else Path(cwd).name[:48]),
            'model':str(model or 'Unknown')[:40], 'tokens':max(0,int(tokens or 0)),
            'updatedAt':int(updated or 0)*1000})
    return {'ok':True,'at':int(time.time()*1000),'tasks':tasks}

if __name__=='__main__':
    while True:
        try: result=snapshot()
        except (sqlite3.Error,OSError,ValueError,TypeError):
            result={'ok':False,'at':int(time.time()*1000),'tasks':[]}
        try: print(json.dumps(result,separators=(',',':')),flush=True)
        except BrokenPipeError:break
        if '--once' in sys.argv:break
        time.sleep(3)
