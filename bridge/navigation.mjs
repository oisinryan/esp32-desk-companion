import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
const run=promisify(execFile);

export async function openCodexChat(id) {
  if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id))throw Error('Invalid chat ID');
  // Installed Codex protocol handler accepts codex://threads/<conversationId>.
  // Only the hardware navigation event invokes this; never the automatic carousel.
  await run('/usr/bin/open',['-b','com.openai.codex',`codex://threads/${id}`],{timeout:3000});
}

export function createNavigator({view,select,resolveId,open=openCodexChat,now=Date.now}) {
  const completed=new Map();
  let chain=Promise.resolve(),ring=[],ringAt=0;
  const handle=async event=>{
    if(!event || !/^[0-9a-f]{8}-[0-9a-f]{8}$/.test(event.id) || !['next','auto'].includes(event.action))throw Object.assign(Error('Invalid navigation event'),{status:400});
    if(completed.has(event.id))return completed.get(event.id);
    let result={id:event.id,ok:true,action:event.action};
    if(event.action==='auto') {select(null);ring=[];}
    else {
      const state=view();
      const recent=state.tasks.filter(t=>now()-t.updatedAt<120000 && t.updatedAt<=now()+5000);
      const keys=recent.map(t=>t.key).sort();
      // Stable order across token updates; refreshing metadata must not reorder clicks.
      if(now()-ringAt>120000 || keys.join()!==[...ring].sort().join()){
        ring=recent.map(t=>t.key);ringAt=now();
      }
      if(!state.appConnected || !ring.length)result={...result,ok:false,reason:'No recently active chats'};
      else {
        const index=ring.indexOf(state.selectedKey);
        const key=ring[(index+1)%ring.length];
        const id=resolveId(key);
        if(!id)result={...result,ok:false,reason:'Chat no longer available'};
        else {
          select(key);
          try {await open(id);result={...result,selectedKey:key};}
          catch {result={...result,ok:false,reason:'Could not open Codex chat'};}
        }
      }
    }
    completed.set(event.id,result);
    while(completed.size>64)completed.delete(completed.keys().next().value);
    return result;
  };
  return {handle:event=>{
    const result=chain.then(()=>handle(event));chain=result.catch(()=>{});return result;
  }};
}
