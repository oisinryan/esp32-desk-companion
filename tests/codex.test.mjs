import test from 'node:test';
import assert from 'node:assert/strict';
import {summarizeEvents} from '../bridge/codex.mjs';
import {createPetServer} from '../bridge/server.mjs';
import {usefulInfo} from '../bridge/app-info.mjs';

test('task metadata is fresh, honest about inferred activity, selectable and bounded for the display',()=>{
  const now=2_000_000;
  const hooks=summarizeEvents([],now);
  const task={key:'a'.repeat(32),title:'A very long user-facing task title that needs truncation',project:'Game',model:'gpt-test',tokens:1250000,updatedAt:now};
  const app={ok:true,at:now,tasks:[task,{...task,key:'b'.repeat(32),title:'Second task'}]};
  const result=usefulInfo(hooks,app,now,task.key);
  assert.equal(result.connected,true);assert.equal(result.exactStatus,false);assert.equal(result.recentCount,2);
  assert.equal(result.selectedTask.title,task.title);
  assert.equal(result.display.label,'2 RECENTLY ACTIVE');
  for(const value of Object.values(result.display))assert.ok(value.length<=23);
  assert.equal(usefulInfo(hooks,app,now+11000).appConnected,false);
  const waiting=usefulInfo(summarizeEvents([{status:'waiting',at:now}],now),app,now);
  assert.equal(waiting.status,'waiting');assert.equal(waiting.exactStatus,true);
});

test('local selection requires same-origin and compact device response excludes task list',async()=>{
  let selected=null;
  const desktop={view:()=>({tasks:[{key:'valid'}],selectedKey:selected}),select:key=>{selected=key;},deviceView:()=>({status:'idle',connected:true,count:0,display:{line1:'Useful task'}})};
  const token='test-codey-private-token-value';const {server}=createPetServer({token,desktop});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${server.address().port}`;
  const post=(path,body,headers={})=>fetch(origin+path,{method:'POST',headers:{'Content-Type':'application/json',...headers},body:JSON.stringify(body)});
  try{
    assert.equal((await post('/api/desktop/select',{key:'valid'})).status,401);
    assert.equal((await post('/api/desktop/select',{key:'valid'},{Origin:'https://foreign.example'})).status,403);
    assert.equal((await post('/api/desktop/select',{key:'valid'},{Origin:origin})).status,200);
    assert.equal(selected,'valid');
    assert.equal((await post('/api/desktop/select',{key:'missing'},{Origin:origin})).status,400);
    const res=await post('/api/device',{energy:80,fullness:75,joy:75,sleeping:false,mood:'happy',ack:''},{Authorization:`Bearer ${token}`});
    const wire=await res.text();assert.ok(wire.length<1024);assert.equal(JSON.parse(wire).desktop.tasks,undefined);
  }finally{await new Promise(resolve=>server.close(resolve));}
});

test('desktop aggregation prioritises attention and expires completed/stale tasks',()=>{
  const now=2_000_000;
  const event=status=>({status,at:now});
  assert.equal(summarizeEvents([],now).connected,false);
  assert.equal(summarizeEvents([event('running'),event('ready')],now).status,'ready');
  assert.equal(summarizeEvents([event('running'),event('ready'),event('waiting')],now).status,'waiting');
  assert.equal(summarizeEvents([{status:'ready',at:now-121_000}],now).status,'idle');
  assert.equal(summarizeEvents([{status:'running',at:now-1_801_000}],now).connected,false);
  assert.equal(summarizeEvents([{status:'running',at:NaN},{status:'injected',at:now}],now).connected,false);
  assert.equal(summarizeEvents([event('running'),event('running')],now).count,2);
});

test('authenticated device heartbeat carries desktop status independently of care commands',async()=>{
  const desktop={view:()=>({enabled:true,connected:true,status:'running',count:2})};
  const token='test-codey-private-token-value';
  const {server}=createPetServer({token,desktop});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  try {
    const url=`http://127.0.0.1:${server.address().port}/api/device`;
    const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`},body:JSON.stringify({energy:80,fullness:75,joy:75,sleeping:false,mood:'happy',ack:''})});
    assert.equal(res.status,200); const data=await res.json();
    assert.equal(data.desktop.status,'running');assert.equal(data.desktop.count,2);assert.equal(data.command,null);
  } finally {await new Promise(resolve=>server.close(resolve));}
});
