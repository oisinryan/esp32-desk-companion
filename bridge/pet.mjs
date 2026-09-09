import { randomUUID } from 'node:crypto';
export const moods = ['happy', 'curious', 'love', 'excited', 'sleepy', 'sad', 'thinking'];
export const actions = ['pet', 'feed', 'play', 'sleep', 'wake'];
export const clamp = n => Math.min(100, Math.max(0, n));
export class PetStore {
  constructor({ demo = false, now = Date.now } = {}) {
    this.demo = demo; this.now = now; this.lastSeen = 0; this.pending = [];
    this.state = { energy: 80, fullness: 75, joy: 75, sleeping: false, mood: 'happy' };
    this.messages = []; this.lastTick = now(); this.emoteAt = now();
  }
  tick() {
    if (!this.demo) return;
    const n = Math.floor((this.now() - this.lastTick) / 60000);
    if (n) {
      this.lastTick += n * 60000;
      this.state.energy = clamp(this.state.energy + n * (this.state.sleeping ? 3 : -1));
      this.state.fullness = clamp(this.state.fullness - n); this.state.joy = clamp(this.state.joy - n);
    }
    if (this.state.sleeping) this.state.mood = 'sleepy';
    else if (this.now() - this.emoteAt > 8000) this.state.mood = this.state.energy < 20 ? 'sleepy' : Math.min(this.state.fullness, this.state.joy) < 20 ? 'sad' : 'curious';
  }
  view() {
    this.tick(); this.prune();
    return { ...this.state, demo: this.demo, connected: !this.demo && this.lastSeen > 0 && this.now() - this.lastSeen < 6000,
      lastSeen: this.lastSeen || null, pending: this.pending.length, messages: this.messages };
  }
  prune() { this.pending = this.pending.filter(c => this.now() - c.created < 30000); }
  message(role, text) { this.messages.push({ role, text, id: randomUUID() }); this.messages = this.messages.slice(-20); }
  enqueue({ action = '', mood = '', text = '' }) {
    this.prune();
    if (this.pending.length >= 8) throw Object.assign(new Error('Pip has a full command queue. Wait for the device to reconnect.'), { status: 429 });
    const command = { id: randomUUID(), action, mood, text: text.normalize('NFKD').replace(/[^\x20-\x7E]/g, '').slice(0, 160), created: this.now() };
    if (this.demo) {
      const p = this.state;
      if (action === 'pet') { p.joy = clamp(p.joy + 12); p.mood = 'love'; }
      if (action === 'feed') { p.fullness = clamp(p.fullness + 20); p.mood = 'excited'; }
      if (action === 'play') { p.sleeping = false; p.energy = clamp(p.energy - 8); p.joy = clamp(p.joy + 18); p.mood = 'excited'; }
      if (action === 'sleep') { p.sleeping = true; p.mood = 'sleepy'; }
      if (action === 'wake') { p.sleeping = false; p.mood = 'happy'; }
      if (moods.includes(mood)) p.mood = mood;
      this.emoteAt = this.now();
    } else this.pending.push(command);
    return command.id;
  }
  heartbeat(body) {
    for (const key of ['energy', 'fullness', 'joy']) {
      if (!Number.isInteger(body[key]) || body[key] < 0 || body[key] > 100) throw Object.assign(new Error('Invalid device state'), { status: 400 });
    }
    if (typeof body.sleeping !== 'boolean' || !moods.includes(body.mood) || typeof body.ack !== 'string' || body.ack.length > 40)
      throw Object.assign(new Error('Invalid device state'), { status: 400 });
    this.prune();
    // Only acknowledge the current head; never discard later commands from an arbitrary ID.
    if (this.pending[0]?.id === body.ack) this.pending.shift();
    this.state = Object.fromEntries(['energy', 'fullness', 'joy', 'sleeping', 'mood'].map(k => [k, body[k]]));
    this.lastSeen = this.now();
    const next = this.pending[0];
    return { command: next ? Object.fromEntries(['id', 'action', 'mood', 'text'].map(k => [k, next[k]])) : null };
  }
}

export async function askOpenAI({ key, model, messages, state, fetchImpl = fetch }) {
  const response = await fetchImpl('https://api.openai.com/v1/responses', {
    method: 'POST', signal: AbortSignal.timeout(25000),
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, store: false, max_output_tokens: 250,
      instructions: 'You are Pip, a warm, playful tiny desktop pet. Reply in English in one short sentence, at most 140 ASCII characters. Be kind, curious, and lightly whimsical. Never claim to see, hear, or control things. Pick an expression fitting your reply. You can express sleepiness but cannot change sleep mode or needs; the human uses the care buttons. Current pet state: ' + JSON.stringify(state),
      input: messages.slice(-10).map(({ role, text }) => ({ role, content: text })),
      text: { format: { type: 'json_schema', name: 'pet_reply', strict: true, schema: {
        type: 'object', properties: { reply: { type: 'string' }, mood: { type: 'string', enum: moods.filter(x => x !== 'thinking') } },
        required: ['reply', 'mood'], additionalProperties: false
      } } }
    })
  });
  if (!response.ok) throw Object.assign(new Error(`OpenAI request failed (${response.status}). Check the server's API key, model access and quota.`), { status: 502 });
  const result = await response.json();
  if (result.status !== 'completed') throw Object.assign(new Error('Pip did not receive a complete reply. Please try again.'), { status: 502 });
  const text = (result.output ?? []).flatMap(item => item.content ?? []).filter(item => item.type === 'output_text').map(item => item.text).join('');
  let parsed;
  try { parsed = JSON.parse(text); } catch { throw Object.assign(new Error('Pip could not read the model reply.'), { status: 502 }); }
  if (typeof parsed.reply !== 'string' || !parsed.reply.trim() || !moods.includes(parsed.mood)) throw Object.assign(new Error('Pip received an invalid reply.'), { status: 502 });
  return { reply: parsed.reply.slice(0, 160), mood: parsed.mood };
}
