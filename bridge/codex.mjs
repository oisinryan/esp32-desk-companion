import { readdir, readFile } from 'node:fs/promises';

export const desktopStates = ['idle','running','waiting','ready','failed'];
export function summarizeEvents(events, now = Date.now()) {
  const recent = events.filter(e => desktopStates.includes(e.status) && Number.isFinite(e.at) && e.at <= now + 5000 && now-e.at < 30*60_000);
  const counts = Object.fromEntries(desktopStates.map(state => [state, recent.filter(e => e.status === state && (state !== 'ready' || now-e.at < 120_000)).length]));
  const status = ['waiting','failed','ready','running','idle'].find(s => counts[s]) || 'idle';
  return { enabled:true, connected:recent.length>0, status, count:counts[status], running:counts.running,
    source:'codex-hooks', lastEventAt:Math.max(0,...recent.map(e=>e.at)) };
}

export function watchCodex(folder, {now=Date.now}={}) {
  let events=[], stopped=false, timer;
  async function refresh() {
    try {
      const names=(await readdir(folder)).filter(n=>/^[a-f0-9]{32}\.json$/.test(n)).slice(-512);
      const results=await Promise.allSettled(names.map(async n=>{
        const value=JSON.parse(await readFile(new URL(n,folder),'utf8'));
        return {status:value.status,at:value.at};
      }));
      events=results.filter(r=>r.status==='fulfilled').map(r=>r.value);
    } catch { events=[]; }
    if(!stopped) { timer=setTimeout(refresh,500); timer.unref(); }
  }
  refresh();
  return { view:()=>summarizeEvents(events,now()), close:()=>{stopped=true;clearTimeout(timer);} };
}
