import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { timingSafeEqual } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { PetStore, actions, askOpenAI } from './pet.mjs';
import { watchCodex } from './codex.mjs';
import { watchAppInfo, usefulInfo } from './app-info.mjs';
import { createNavigator } from './navigation.mjs';

const assetRoot = new URL('./public/', import.meta.url);
const fail = (message, status = 400) => Object.assign(new Error(message), { status });
async function readJSON(req) {
  if (!req.headers['content-type']?.startsWith('application/json')) throw fail('JSON required', 415);
  let size = 0; const chunks = [];
  for await (const chunk of req) { size += chunk.length; if (size > 4096) throw fail('Request too large', 413); chunks.push(chunk); }
  try { const body = JSON.parse(Buffer.concat(chunks).toString()); if (!body || Array.isArray(body) || typeof body !== 'object') throw Error(); return body; }
  catch { throw fail('Invalid JSON'); }
}
export function createPetServer({ demo = false, token = '', key = '', model = 'gpt-4.1-mini', fetchImpl = fetch, now = Date.now, desktop = null } = {}) {
  if (!demo && (token.length < 24 || token.startsWith('replace-'))) throw Error('Set PET_TOKEN to a random token of at least 24 characters. See .env.example.');
  const pet = new PetStore({ demo, now });
  let busy = false, lastChat = -Infinity;
  const server = http.createServer(async (req, res) => {
    const send = (status, data, type = 'application/json') => {
      const body = type === 'application/json' ? JSON.stringify(data) : data;
      res.writeHead(status, { 'Content-Type': type, 'Content-Length': Buffer.byteLength(body), 'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
        'Content-Security-Policy': "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'" });
      res.end(body);
    };
    try {
      const url = new URL(req.url, 'http://localhost');
      // No CORS. Reject cross-origin writes, including browser-based attacks on a LAN endpoint.
      if (req.headers.origin && req.headers.origin !== `http://${req.headers.host}`) throw fail('Origin denied', 403);
      const files = { '/': ['index.html', 'text/html; charset=utf-8'], '/app.js': ['app.js', 'text/javascript; charset=utf-8'], '/style.css': ['style.css', 'text/css; charset=utf-8'] };
      if (desktop) Object.assign(files, {'/':['codey.html','text/html; charset=utf-8'], '/codey.js':['codey.js','text/javascript; charset=utf-8'], '/codey.css':['codey.css','text/css; charset=utf-8'], '/codey-sheet.webp':['codey-sheet.webp','image/webp']});
      if (req.method === 'GET' && files[url.pathname]) {
        const [file, type] = files[url.pathname]; return send(200, await readFile(new URL(file, assetRoot)), type);
      }
      if (url.pathname === '/api/info' && req.method === 'GET') return send(200, { demo, aiConfigured: Boolean(key) && !demo, authRequired: !demo, desktop: Boolean(desktop) });
      const loopback = ['127.0.0.1','::1','::ffff:127.0.0.1'].includes(req.socket.remoteAddress);
      const localHost = /^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$/.test(req.headers.host ?? '');
      const localDesktopRead = req.method === 'GET' && url.pathname === '/api/desktop' && loopback && localHost;
      const localDesktopSelect = req.method === 'POST' && url.pathname === '/api/desktop/select' && loopback && localHost && Boolean(req.headers.origin);
      if (!demo && !localDesktopRead && !localDesktopSelect) {
        const supplied = Buffer.from(req.headers.authorization ?? ''); const expected = Buffer.from(`Bearer ${token}`);
        if (supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) throw fail('Enter your pairing token to connect.', 401);
      }
      if (req.method === 'GET' && url.pathname === '/api/desktop' && desktop) return send(200, { ...desktop.view(), deviceConnected:pet.view().connected });
      if (req.method === 'GET' && url.pathname === '/api/state') return send(200, { ...pet.view(), busy, desktop: desktop?.view() ?? null });
      if (req.method !== 'POST') throw fail('Not found', 404);
      const body = await readJSON(req);
      if (url.pathname === '/api/desktop/select' && desktop?.select) {
        if (body.key !== null && !desktop.view().tasks.some(t=>t.key===body.key)) throw fail('Unknown task');
        desktop.select(body.key);
        return send(200, { ...desktop.view(), deviceConnected:pet.view().connected });
      }
      if (url.pathname === '/api/device') {
        if (demo) throw fail('Device connection is disabled in browser demo mode.', 409);
        const heartbeat=pet.heartbeat(body);
        const navigation=body.navigation && desktop?.navigate ? await desktop.navigate(body.navigation) : null;
        return send(200, { ...heartbeat, desktop: desktop?.deviceView?.() ?? desktop?.view() ?? null, navigation });
      }
      if (url.pathname === '/api/action') {
        if (!actions.includes(body.action)) throw fail('Unknown action');
        const id = pet.enqueue({ action: body.action });
        return send(202, { id, ...pet.view() });
      }
      if (url.pathname === '/api/chat') {
        if (typeof body.message !== 'string' || !body.message.trim() || body.message.length > 500) throw fail('Use a message between 1 and 500 characters.');
        if (busy || now() - lastChat < 3000) throw fail('Give Pip a moment before the next message.', 429);
        if (!demo && !key) throw fail('Chat is not configured. Set OPENAI_API_KEY in the companion service .env file.', 503);
        if (!demo && !pet.view().connected) throw fail('Connect your ESP32 before chatting, or start the browser demo.', 409);
        busy = true; lastChat = now();
        try {
          const message = body.message.trim();
          const result = demo ? { reply: /sleep|tired/i.test(message) ? 'A little nap sounds lovely. You can tuck me in with the Sleep button.' : 'A tiny desk adventure! I am happy you stopped by. [Demo reply]', mood: /sleep|tired/i.test(message) ? 'sleepy' : 'happy' }
            : await askOpenAI({ key, model, messages: [...pet.messages, { role: 'user', text: message }], state: pet.state, fetchImpl });
          pet.enqueue({ mood: result.mood, text: result.reply });
          pet.message('user', message); pet.message('assistant', result.reply);
          return send(200, { ...result, ...pet.view() });
        } finally { busy = false; }
      }
      throw fail('Not found', 404);
    } catch (error) {
      if (!res.headersSent) send(error.status ?? 500, { error: error.status ? error.message : 'Pip could not reach the chat service. Please try again.' });
      else res.end();
    }
  });
  server.requestTimeout = 10000; server.headersTimeout = 10000;
  return { server, pet };
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const demo = process.argv.includes('--demo');
  const host = demo ? '127.0.0.1' : process.env.HOST || '127.0.0.1';
  const port = Number(process.env.PORT || 8787);
  let desktop = null;
  if (!demo && process.env.CODEX_PET === '1') {
    const hooks=watchCodex(new URL('../runtime/codex-events/', import.meta.url)), app=watchAppInfo();
    let selectedKey=null;
    const view=()=>usefulInfo(hooks.view(),app.view(),Date.now(),selectedKey);
    const select=key=>{selectedKey=key;};
    const navigator=createNavigator({view,select,resolveId:key=>app.view().tasks.find(t=>t.key===key)?.threadId});
    desktop={view,select,navigate:navigator.handle,deviceView:()=>{
      const {connected,status,count,display}=view(); return {connected,status,count,display};
    },close:()=>{hooks.close();app.close();}};
  }
  const { server } = createPetServer({ demo, token: process.env.PET_TOKEN, key: process.env.OPENAI_API_KEY, model: process.env.OPENAI_MODEL, desktop });
  server.on('close', () => desktop?.close());
  server.listen(port, host, () => console.log(`Pip ${demo ? 'browser demo (scripted chat)' : 'Wi-Fi companion'}: http://${host}:${port}`));
  server.on('error', error => { console.error(`Cannot start companion: ${error.code}`); process.exitCode = 1; });
}
