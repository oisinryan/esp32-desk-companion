const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('pip-token') || '';
let info = {}, state = { mood: 'happy', sleeping: false }, sending = false, paired = false;
let previousMessages = '', offline = false;
const moodLabels = { happy: 'Happy to see you', curious: 'Feeling curious', love: 'Feeling loved', excited: 'Ready for adventure', sleepy: 'A little sleepy', sad: 'Needs a little care', thinking: 'Deep in thought' };
async function api(path, body) {
  const res = await fetch(path, { method: body ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(30000) });
  const data = await res.json();
  if (!res.ok) { if (res.status === 401) { paired = false; $('pairing').hidden = false; } throw new Error(data.error || 'Connection failed'); }
  return data;
}
function showError(error) { $('error').textContent = error.message; $('error').hidden = false; }
function render(next) {
  state = next; offline = false;
  $('connection').textContent = info.demo ? 'Browser demo' : next.connected ? 'ESP32 connected' : 'ESP32 offline';
  $('mode-note').textContent = info.demo ? 'BROWSER DEMO · This pet is simulated. Chat replies are scripted; no device or API key is needed.' : !info.aiConfigured ? 'Care controls are ready. Add OPENAI_API_KEY to the companion service to enable chat.' : next.connected ? 'Your ESP32 is connected. Care commands and chat expressions travel over Wi-Fi.' : 'Waiting for your ESP32. Check its Wi-Fi settings and companion address.';
  $('mood').textContent = moodLabels[next.mood] || 'Just hanging out';
  for (const key of ['energy', 'fullness', 'joy']) { $(key).value = next[key]; $(key + '-value').textContent = next[key] + '%'; }
  $('sleep').dataset.action = next.sleeping ? 'wake' : 'sleep';
  $('sleep').replaceChildren(Object.assign(document.createElement('span'), { textContent: next.sleeping ? '☀' : '☾' }), document.createTextNode(next.sleeping ? 'Wake' : 'Sleep'));
  $('delivery').textContent = next.pending ? `${next.pending} COMMAND${next.pending > 1 ? 'S' : ''} WAITING FOR DEVICE` : info.demo ? 'BROWSER DEMO · NO HARDWARE' : next.connected ? 'DEVICE SYNCHRONISED' : 'DEVICE DISCONNECTED';
  const serialized = JSON.stringify(next.messages);
  if (next.messages.length && serialized !== previousMessages) {
    $('messages').replaceChildren();
    for (const m of next.messages) { const item = document.createElement('div'); item.className = 'bubble ' + (m.role === 'user' ? 'user' : 'pet'); const name = document.createElement('small'); name.textContent = m.role === 'user' ? 'You' : 'Pip'; item.append(name, document.createTextNode(m.text)); $('messages').append(item); }
    $('messages').scrollTop = $('messages').scrollHeight;
  }
  previousMessages = serialized;
  $('thinking').hidden = !(sending || next.busy);
  $('pet-caption').textContent = next.sleeping ? 'Recharging my tiny social battery.' : next.mood === 'love' ? 'This is my favourite part of the day.' : next.mood === 'excited' ? 'Oh! That was lovely.' : 'Your little pocket of calm.';
  controls();
}
function controls() {
  const ready = paired && !offline;
  for (const button of document.querySelectorAll('[data-action]')) button.disabled = !ready;
  const chatReady = ready && (info.demo || (info.aiConfigured && state.connected)) && !sending && !state.busy;
  $('send').disabled = !chatReady;
  for (const button of document.querySelectorAll('[data-say]')) button.disabled = !chatReady;
}
async function poll() {
  if (paired) try { render(await api('/api/state')); } catch (error) { offline = true; $('connection').textContent = 'Companion unavailable'; controls(); showError(error); }
  setTimeout(poll, 1000);
}
$('pairing').addEventListener('submit', async event => {
  event.preventDefault(); token = $('token').value.trim();
  try { const next = await api('/api/state'); paired = true; sessionStorage.setItem('pip-token', token); $('token').value = ''; $('pairing').hidden = true; $('error').hidden = true; render(next); } catch (error) { showError(error); }
});
for (const button of document.querySelectorAll('[data-action]')) button.addEventListener('click', async () => {
  $('error').hidden = true;
  try { render(await api('/api/action', { action: button.dataset.action })); } catch (error) { showError(error); }
});
async function chat(message) {
  if (sending) return;
  sending = true; controls(); $('thinking').hidden = false; $('error').hidden = true;
  try { render(await api('/api/chat', { message })); $('message').value = ''; }
  catch (error) { showError(error); }
  finally { sending = false; $('thinking').hidden = true; controls(); }
}
$('chat').addEventListener('submit', event => { event.preventDefault(); if (!$('send').disabled) chat($('message').value); });
for (const button of document.querySelectorAll('[data-say]')) button.addEventListener('click', () => chat(button.dataset.say));

const ctx = $('face').getContext('2d'), reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
function draw(time) {
  ctx.clearRect(0, 0, 512, 256); ctx.fillStyle = '#c6e3a0'; ctx.strokeStyle = '#c6e3a0'; ctx.lineWidth = 9; ctx.lineCap = 'round';
  const m = sending ? 'thinking' : state.mood;
  const blink = !reduced && time % 4700 < 140;
  const sleepy = state.sleeping || m === 'sleepy';
  const happy = ['happy', 'love', 'excited'].includes(m);
  const offset = reduced ? 0 : Math.sin(time / 2200) * 8;
  for (const x of [153, 313]) {
    ctx.beginPath();
    if (sleepy || blink) { ctx.moveTo(x - 23, 112); ctx.lineTo(x + 23, 112); ctx.stroke(); }
    else if (happy) { ctx.arc(x, 122, 25, Math.PI + .2, Math.PI * 2 - .2); ctx.stroke(); }
    else { ctx.roundRect(x - 19 + offset, m === 'sad' ? 94 : 78, 38, m === 'sad' ? 39 : m === 'thinking' ? 52 : 67, 17); ctx.fill(); }
  }
  ctx.beginPath(); ctx.moveTo(219, 160); ctx.quadraticCurveTo(244, sleepy ? 160 : 187, 269, 160); ctx.stroke();
  if (m === 'love') { ctx.fillStyle = '#90b977'; for (const x of [107, 362]) { ctx.beginPath(); ctx.ellipse(x, 154, 16, 8, 0, 0, Math.PI * 2); ctx.fill(); } }
  if (sleepy) { ctx.font = '28px monospace'; ctx.fillText('z', 405, 67); }
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);
controls();
try {
  info = await api('/api/info');
  $('chat-note').textContent = info.demo ? 'Demo chat uses scripted replies. No AI requests are sent.' : 'AI replies can be mistaken. Your API key stays on the server.';
  paired = info.demo || Boolean(token); $('pairing').hidden = paired;
  if (!paired) { $('connection').textContent = 'Ready to pair'; $('mode-note').textContent = 'Enter your pairing token to connect to Pip.'; }
  poll();
} catch (error) { showError(error); }
