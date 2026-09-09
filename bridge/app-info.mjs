import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';

export function watchAppInfo() {
  let last={ok:false,at:0,tasks:[]}, closed=false;
  const child=spawn(fileURLToPath(new URL(process.platform==='win32'?'../.venv/Scripts/python.exe':'../.venv/bin/python',import.meta.url)),[fileURLToPath(new URL('../tools/app_info.py',import.meta.url))],{stdio:['ignore','pipe','ignore']});
  const lines=createInterface({input:child.stdout});
  lines.on('line',line=>{
    if(line.length>16384)return;
    try {
      const data=JSON.parse(line);
      if(typeof data.ok==='boolean' && Number.isFinite(data.at) && Array.isArray(data.tasks) && data.tasks.length<=16)last=data;
    }catch{}
  });
  child.on('error',()=>{last={ok:false,at:0,tasks:[]};});
  child.on('exit',()=>{if(!closed)last={ok:false,at:0,tasks:[]};});
  return {view:()=>last,close:()=>{closed=true;lines.close();child.kill();}};
}

const text=(value,max=100)=>String(value??'').replace(/[\u0000-\u001f\u007f]/g,' ').slice(0,max);
const ascii=(value,max=23)=>text(value,100).normalize('NFKD').replace(/[^\x20-\x7e]/g,'').slice(0,max);
export const compactTokens=n=>n>=1e6?`${(n/1e6).toFixed(1)}M`:n>=1e3?`${(n/1e3).toFixed(1)}k`:String(n);

export function usefulInfo(hooks, app, now=Date.now(), selectedKey=null) {
  const fresh=app.ok && Number.isFinite(app.at) && now-app.at<10_000 && app.at<=now+5000;
  const tasks=fresh?app.tasks.map(t=>({key:text(t.key,32),title:text(t.title),project:text(t.project,48),model:text(t.model,40),tokens:Math.max(0,Number(t.tokens)||0),updatedAt:Number(t.updatedAt)||0})):[];
  const recent=tasks.filter(t=>now-t.updatedAt<120_000 && t.updatedAt<=now+5000);
  // Database activity is deliberately labelled "recent", never an exact running state.
  const candidates=recent.length?recent:tasks.slice(0,4);
  const selected=tasks.find(t=>t.key===selectedKey) || candidates[Math.floor(now/12000)%Math.max(1,candidates.length)];
  const observed=hooks.connected;
  const status=observed?hooks.status:recent.length?'running':'idle';
  const labels={idle:'CODEX CONNECTED',running:'CODEX WORKING',waiting:'NEEDS YOUR INPUT',ready:'TASK FINISHED',failed:'NEEDS ATTENTION'};
  let display={label:'APP FEED UNAVAILABLE',line1:'Keep companion running',line2:'Waiting for app data',footer:'WI-FI COMPANION'};
  if(fresh){
    const detailPage=Math.floor(now/6000)%2;
    display={label:observed?labels[status]:(recent.length?`${recent.length} RECENTLY ACTIVE`:'CODEX TASKS'),
      line1:ascii(selected?.title||'No named tasks yet'),
      line2:ascii(selected?(detailPage?`${compactTokens(selected.tokens)} total tokens`:`${selected.project} / ${selected.model}`):'Ready when you are'),
      footer:'BOOT NEXT / HOLD AUTO'};
  }
  return {...hooks,connected:fresh||observed,status,count:observed?hooks.count:recent.length,
    source:observed?'codex-hooks+task-index':'codex-task-index',exactStatus:observed,
    appConnected:fresh,appUpdatedAt:fresh?app.at:null,recentCount:recent.length,
    tasks,manualSelection:Boolean(selectedKey && tasks.some(t=>t.key===selectedKey)),selectedKey:selected?.key??null,selectedTask:selected??null,display};
}
