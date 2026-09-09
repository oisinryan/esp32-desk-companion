const $=id=>document.getElementById(id);
let current='idle',token=sessionStorage.getItem('pip-token')||'',manual=false,taskSignature='';
const rows={idle:0,running:7,waiting:6,ready:8,failed:5};
const counts={idle:6,running:6,waiting:6,ready:6,failed:8};
const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
setInterval(()=>{const frame=reduced?0:Math.floor(performance.now()/(current==='idle'?750:160))%counts[current];$('codey').style.backgroundPosition=`-${frame*192}px -${rows[current]*208}px`;},80);
const tokens=n=>n>=1e6?`${(n/1e6).toFixed(1)}M`:n>=1e3?`${(n/1e3).toFixed(1)}k`:String(n);
async function api(path,body){
 const res=await fetch(path,{method:body?'POST':'GET',headers:{Authorization:`Bearer ${token}`,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(4000)});
 if(res.status===401){$('pairing').hidden=false;throw Error('Enter your pairing token for access from another computer.');}
 if(!res.ok)throw Error('Companion service unavailable');return res.json();
}
function render(d){
 manual=Boolean(d.manualSelection);
 $('pairing').hidden=true;$('error').textContent='';current=d.connected?d.status:'idle';
 $('device').textContent=d.deviceConnected?'● ESP32 connected over Wi-Fi':'○ ESP32 offline';
 $('live').textContent=d.appConnected?'Live app data':d.connected?'Live hooks':'App feed offline';
 $('status').textContent=d.selectedTask?.title||'Ready when you are';
 $('detail').textContent=d.selectedTask?`${d.selectedTask.project} · ${d.selectedTask.model} · ${tokens(d.selectedTask.tokens)} total tokens`:'Waiting for task information from Codex.';
 $('count').textContent=d.display?.label||'WAITING';
 $('note').textContent=d.appConnected?'The ESP32 shows this same task. Auto mode rotates recently active tasks every 12 seconds.': 'Keep the companion service running to reconnect the app feed.';
 $('recent').textContent=d.recentCount??'—';$('task-total').textContent=d.tasks?.length??'—';
 $('refreshed').textContent=d.appUpdatedAt?`${Math.max(0,Math.floor((Date.now()-d.appUpdatedAt)/1000))}s`:'—';
 $('auto').textContent=manual?'Resume auto rotate':'Auto rotating';
 const signature=JSON.stringify((d.tasks||[]).map(t=>[t.key,t.title,t.project,t.model]));
 if(signature!==taskSignature){
  $('tasks').replaceChildren();
  for(const t of (d.tasks||[]).slice(0,8)){
   const button=document.createElement('button');button.className='task';button.dataset.key=t.key;button.type='button';
   const title=document.createElement('strong');title.textContent=t.title;
   const detail=document.createElement('span');detail.textContent=`${t.project} · ${t.model}`;
   const usage=document.createElement('small');usage.textContent=`${tokens(t.tokens)} tokens`;
   button.append(title,detail,usage);button.addEventListener('click',()=>select(t.key));$('tasks').append(button);
  }
  taskSignature=signature;
 }
 for(const button of $('tasks').children){const task=d.tasks.find(t=>t.key===button.dataset.key); const usage=button.querySelector('small');const value=`${tokens(task.tokens)} tokens`;if(usage.textContent!==value)usage.textContent=value;const selected=button.dataset.key===d.selectedKey;button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));}
}
async function select(key){try{manual=key!==null;render(await api('/api/desktop/select',{key}));}catch(e){$('error').textContent=e.message;}}
async function poll(){try{render(await api('/api/desktop'));}catch(e){$('error').textContent=e.message;$('live').textContent='Disconnected';current='idle';}setTimeout(poll,1000);}
$('auto').addEventListener('click',()=>select(null));
$('pairing').addEventListener('submit',e=>{e.preventDefault();token=$('token').value.trim();sessionStorage.setItem('pip-token',token);$('token').value='';});
poll();
