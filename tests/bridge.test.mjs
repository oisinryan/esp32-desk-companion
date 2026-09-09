import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { PetStore, askOpenAI } from '../bridge/pet.mjs';
import { createPetServer } from '../bridge/server.mjs';
const token = 'test-only-token-0123456789012345';
const heartbeat = { energy: 80, fullness: 75, joy: 75, sleeping: false, mood: 'happy', ack: '' };
async function fixture(t, options = {}) {
  const { server, pet } = createPetServer({ token, ...options });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  const base = `http://127.0.0.1:${server.address().port}`;
  const call = (path, body, headers = {}) => fetch(base + path, { method: body === undefined ? 'GET' : 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...headers }, body: body === undefined ? undefined : JSON.stringify(body) });
  return { pet, call, base };
}
test('device commands retransmit until ack, preserve order, and expire', () => {
  let now = 10000; const pet = new PetStore({ now: () => now });
  const one = pet.enqueue({ action: 'feed' }), two = pet.enqueue({ action: 'pet' });
  assert.equal(pet.heartbeat(heartbeat).command.id, one);
  assert.equal(pet.heartbeat({ ...heartbeat, ack: two }).command.id, one);
  assert.equal(pet.heartbeat({ ...heartbeat, ack: one }).command.id, two);
  assert.equal(pet.heartbeat({ ...heartbeat, ack: two }).command, null);
  pet.enqueue({ action: 'play' }); now += 31000; assert.equal(pet.heartbeat(heartbeat).command, null);
  now += 6001; assert.equal(pet.view().connected, false);
});
test('device input validation and bounded queue', () => {
  const pet = new PetStore();
  for (let i = 0; i < 8; i++) pet.enqueue({ action: 'pet' });
  assert.throws(() => pet.enqueue({ action: 'pet' }), /queue/);
  assert.throws(() => pet.heartbeat({ ...heartbeat, energy: 1000 }), /Invalid/);
  assert.throws(() => pet.heartbeat({ ...heartbeat, sleeping: 'false' }), /Invalid/);
});
test('demo needs saturate and sleep restores energy', () => {
  let now = 0; const pet = new PetStore({ demo: true, now: () => now });
  pet.enqueue({ action: 'feed' }); pet.enqueue({ action: 'feed' }); assert.equal(pet.view().fullness, 100);
  pet.enqueue({ action: 'sleep' }); now = 60000; assert.equal(pet.view().energy, 83);
  pet.enqueue({ mood: 'happy' }); assert.equal(pet.view().mood, 'sleepy');
  pet.enqueue({ action: 'wake' }); now += 60000; assert.equal(pet.view().energy, 82);
  assert.equal(pet.view().connected, false); assert.equal(pet.pending.length, 0);
});
test('pairing, origin protection, validation and static assets', async t => {
  const { call, base } = await fixture(t);
  assert.equal((await fetch(base + '/api/state')).status, 401);
  assert.equal((await call('/api/state')).status, 200);
  assert.equal((await call('/api/action', { action: 'feed' }, { Origin: 'https://untrusted.example' })).status, 403);
  assert.equal((await call('/api/action', { action: 'bad' })).status, 400);
  assert.equal((await call('/api/chat', { message: 'a'.repeat(501) })).status, 400);
  assert.equal((await call('/api/chat', { message: 'Hello' })).status, 503);
  assert.equal((await call('/api/device', { ...heartbeat, mood: 'bogus' })).status, 400);
  assert.equal((await call('/api/action', { action: 'feed' })).status, 202);
  assert.equal((await (await call('/api/device', heartbeat)).json()).command.action, 'feed');
  for (const path of ['/', '/app.js', '/style.css']) assert.equal((await fetch(base + path)).status, 200);
  assert.equal((await fetch(base + '/.env')).status, 401);
  assert.equal((await call('/api/action', { action: 'a'.repeat(5000) })).status, 413);
});
test('demo works without key and explicitly refuses device connection', async t => {
  const { call } = await fixture(t, { demo: true });
  assert.equal((await (await call('/api/info')).json()).demo, true);
  const reply = await (await call('/api/chat', { message: 'Hi' })).json();
  assert.match(reply.reply, /Demo/); assert.equal(reply.messages.length, 2);
  assert.equal((await call('/api/chat', { message: 'Again' })).status, 429);
  assert.equal((await call('/api/device', heartbeat)).status, 409);
});
test('Responses integration uses validated structured output, bounded context, and no stored response', async () => {
  const result = await askOpenAI({ key: 'test-key', model: 'test-model', messages: [{ role: 'user', text: 'Hi' }], state: heartbeat,
    fetchImpl: async (url, options) => {
      assert.equal(url, 'https://api.openai.com/v1/responses');
      const b = JSON.parse(options.body); assert.equal(b.store, false); assert.equal(b.text.format.type, 'json_schema');
      assert.equal(options.headers.Authorization, 'Bearer test-key');
      return new Response(JSON.stringify({ status: 'completed', output: [{ type: 'message', content: [{ type: 'output_text', text: '{"reply":"Hello friend!","mood":"happy"}' }] }] }));
    } });
  assert.equal(result.reply, 'Hello friend!');
});
test('upstream refusal, incomplete response, malformed reply and quota error are handled', async () => {
  const options = { key: 'test', model: 'test', messages: [], state: {} };
  for (const payload of [{ status: 'incomplete' }, { status: 'completed', output: [] }, { status: 'completed', output: [{ content: [{ type: 'output_text', text: '{"reply":"Hi","mood":"invalid"}' }] }] }])
    await assert.rejects(() => askOpenAI({ ...options, fetchImpl: async () => new Response(JSON.stringify(payload)) }));
  await assert.rejects(() => askOpenAI({ ...options, fetchImpl: async () => new Response('private detail', { status: 429 }) }), /429/);
});
test('chat survives upstream failure and accepts a later successful retry', async t => {
  let now = 10000, failing = true;
  const { call } = await fixture(t, { key: 'test', now: () => now, fetchImpl: async () => failing ? new Response('', { status: 500 }) : new Response(JSON.stringify({ status: 'completed', output: [{ content: [{ type: 'output_text', text: '{"reply":"Hello!","mood":"happy"}' }] }] })) });
  await call('/api/device', heartbeat);
  assert.equal((await call('/api/chat', { message: 'Hi' })).status, 502);
  assert.equal((await (await call('/api/state')).json()).busy, false);
  assert.equal((await (await call('/api/state')).json()).messages.length, 0);
  now += 3100; failing = false;
  assert.equal((await call('/api/chat', { message: 'Hi again' })).status, 200);
  const state = await (await call('/api/state')).json(); assert.equal(state.messages.length, 2); assert.equal(state.pending, 1);
});
