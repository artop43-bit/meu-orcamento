import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { ERROR_TEXTS } from '../src/mapping.js'
import { Worker } from '../src/worker.js'

const silent = { warn () {}, error () {}, info () {} }
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/** Sessão de mentira com a mesma interface da Session. */
class FakeSession {
  constructor (id, hooks, behavior = {}) {
    this.id = id
    this.hooks = hooks
    this.status = 'idle'
    this.running = false
    this.behavior = behavior
    this.sent = []
    this.calls = []
  }

  get ready () {
    return this.status === 'ready'
  }

  async start (opts) {
    this.calls.push(['start', opts])
    this.status = this.behavior.startStatus || 'ready'
    this.running = true
  }

  async stop (opts) {
    this.calls.push(['stop', opts])
    this.status = 'stopped'
    this.running = false
    this.hooks.onEnded(this)
  }

  async close () {
    this.calls.push(['close'])
    this.status = 'stopped'
  }

  async send (item) {
    if (this.behavior.delayMs) await sleep(this.behavior.delayMs)
    if (this.behavior.fail) throw new Error('falhou')
    if (this.behavior.skip) return { skipped: true }
    this.sent.push(item.message_id)
    return { externalId: `WA-${item.message_id}` }
  }

  async read (jid, ids) {
    this.calls.push(['read', jid, ids])
    return true
  }

  info () {
    return { id: this.id, status: this.status }
  }
}

function setup ({ outbox = [], behaviors = {} } = {}) {
  const pushed = []
  const outboxCalls = []
  const removed = []
  const notified = []
  const sessions = new Map()
  const api = {
    queued: 0,
    stats: {},
    async getOutbox (ids) {
      outboxCalls.push([...ids])
      return outbox.filter((item) => ids.includes(item.session_id))
    },
    push (event) { pushed.push(event) },
    async drain () {}
  }
  const worker = new Worker({
    api,
    authStore: { async removeAll (id) { removed.push(id) } },
    logger: silent,
    notify: (msg) => notified.push(msg),
    sweepMs: 20,
    createSession: (id, hooks) => {
      const session = new FakeSession(id, hooks, behaviors[id])
      sessions.set(id, session)
      return session
    }
  })
  return { worker, api, pushed, outboxCalls, removed, notified, sessions }
}

const item = (sessionId, n) => ({ message_id: `${sessionId}-m${n}`, session_id: sessionId, remote_jid: '5511888888888@s.whatsapp.net', body: `msg ${n}`, quoted: null })

describe('Worker', () => {
  it('varredura: uma chamada só com as sessões prontas do processo', async () => {
    const ctx = setup({ behaviors: { c: { startStatus: 'qr' } } })
    await ctx.worker.handle({ cmd: 'start', sessionId: 'a' })
    await ctx.worker.handle({ cmd: 'start', sessionId: 'b' })
    await ctx.worker.handle({ cmd: 'start', sessionId: 'c' })
    await ctx.worker.sweep()
    assert.deepEqual(ctx.outboxCalls, [['a', 'b']])
  })

  it('varredura automática a cada intervalo e nenhuma chamada sem sessão pronta', async () => {
    const ctx = setup()
    ctx.worker.startSweeps()
    await sleep(70)
    assert.equal(ctx.outboxCalls.length, 0)
    await ctx.worker.handle({ cmd: 'start', sessionId: 'a' })
    await sleep(70)
    assert.ok(ctx.outboxCalls.length >= 2)
    await ctx.worker.shutdown()
  })

  it('flush envia em ordem e confirma com o id do WhatsApp', async () => {
    const outbox = [item('a', 1), item('a', 2), item('b', 1)]
    const ctx = setup({ outbox, behaviors: { a: { delayMs: 5 } } })
    await ctx.worker.handle({ cmd: 'start', sessionId: 'a' })
    await ctx.worker.handle({ cmd: 'start', sessionId: 'b' })
    await ctx.worker.handle({ cmd: 'flush', sessionId: 'a' })
    assert.deepEqual(ctx.outboxCalls, [['a']])
    assert.deepEqual(ctx.sessions.get('a').sent, ['a-m1', 'a-m2'])
    assert.deepEqual(ctx.pushed, [
      { type: 'ack', session_id: 'a', message_id: 'a-m1', status: 'sent', external_id: 'WA-a-m1' },
      { type: 'ack', session_id: 'a', message_id: 'a-m2', status: 'sent', external_id: 'WA-a-m2' }
    ])
  })

  it('falha no envio vira ack failed com o texto do erro', async () => {
    const ctx = setup({ outbox: [item('a', 1)], behaviors: { a: { fail: true } } })
    await ctx.worker.handle({ cmd: 'start', sessionId: 'a' })
    await ctx.worker.flush(['a'])
    assert.deepEqual(ctx.pushed, [{ type: 'ack', session_id: 'a', message_id: 'a-m1', status: 'failed', error: ERROR_TEXTS.sendFailed }])
  })

  it('sessão caiu entre a reserva e o envio: sem ack (o item volta para a fila depois)', async () => {
    const ctx = setup({ outbox: [item('a', 1)], behaviors: { a: { skip: true } } })
    await ctx.worker.handle({ cmd: 'start', sessionId: 'a' })
    await ctx.worker.flush(['a'])
    assert.deepEqual(ctx.pushed, [])
    assert.equal(ctx.worker.counters.skipped, 1)
  })

  it('item que já foi enviado não sai duas vezes: só confirma de novo', async () => {
    const ctx = setup({ outbox: [item('a', 1)] })
    await ctx.worker.handle({ cmd: 'start', sessionId: 'a' })
    await ctx.worker.flush(['a'])
    await ctx.worker.flush(['a'])
    assert.deepEqual(ctx.sessions.get('a').sent, ['a-m1'])
    assert.equal(ctx.pushed.length, 2)
    assert.deepEqual(ctx.pushed[1], ctx.pushed[0])
    assert.equal(ctx.worker.counters.resent_acks, 1)
  })

  it('o mesmo item pedido duas vezes ao mesmo tempo sai uma vez só', async () => {
    const ctx = setup({ outbox: [item('a', 1)], behaviors: { a: { delayMs: 20 } } })
    await ctx.worker.handle({ cmd: 'start', sessionId: 'a' })
    await Promise.all([ctx.worker.flush(['a']), ctx.worker.flush(['a'])])
    assert.deepEqual(ctx.sessions.get('a').sent, ['a-m1'])
    assert.equal(ctx.pushed.length, 1)
  })

  it('read encaminha para a sessão; sem sessão não faz nada', async () => {
    const ctx = setup()
    await ctx.worker.handle({ cmd: 'read', sessionId: 'x', remote_jid: 'j@lid', external_ids: ['A'] })
    await ctx.worker.handle({ cmd: 'start', sessionId: 'a' })
    await ctx.worker.handle({ cmd: 'read', sessionId: 'a', remote_jid: 'j@lid', external_ids: ['A'] })
    assert.deepEqual(ctx.sessions.get('a').calls.at(-1), ['read', 'j@lid', ['A']])
  })

  it('stop com logout sem sessão aberta ainda apaga as credenciais', async () => {
    const ctx = setup()
    await ctx.worker.handle({ cmd: 'stop', sessionId: 'z', logout: true })
    assert.deepEqual(ctx.removed, ['z'])
    await ctx.worker.handle({ cmd: 'stop', sessionId: 'y', logout: false })
    assert.deepEqual(ctx.removed, ['z'])
  })

  it('start e stop da mesma sessão rodam em ordem; sessão parada avisa o supervisor e sai do mapa', async () => {
    const ctx = setup()
    const a = ctx.worker.handle({ cmd: 'start', sessionId: 'a', ifIdle: true })
    const b = ctx.worker.handle({ cmd: 'stop', sessionId: 'a', logout: true })
    await Promise.all([a, b])
    const session = ctx.sessions.get('a')
    assert.deepEqual(session.calls, [['start', { ifIdle: true }], ['stop', { logout: true }]])
    assert.deepEqual(ctx.notified, [{ type: 'session-ended', sessionId: 'a' }])
    await sleep(10)
    assert.equal(ctx.worker.sessions.has('a'), false)
  })

  it('desligamento fecha as sessões sem logout', async () => {
    const ctx = setup()
    await ctx.worker.handle({ cmd: 'start', sessionId: 'a' })
    await ctx.worker.shutdown()
    assert.deepEqual(ctx.sessions.get('a').calls.at(-1), ['close'])
    assert.equal(ctx.sessions.get('a').calls.some((c) => c[0] === 'stop'), false)
    await ctx.worker.flush(['a'])
    assert.equal(ctx.outboxCalls.length, 0, 'parado não busca mais a fila')
  })

  it('stats conta sessões por status', async () => {
    const ctx = setup({ behaviors: { b: { startStatus: 'qr' } } })
    await ctx.worker.handle({ cmd: 'start', sessionId: 'a' })
    await ctx.worker.handle({ cmd: 'start', sessionId: 'b' })
    const stats = ctx.worker.stats({ detail: true })
    assert.equal(stats.sessions, 2)
    assert.deepEqual(stats.by_status, { ready: 1, qr: 1 })
    assert.equal(stats.list.length, 2)
    assert.ok(stats.rss > 0)
  })
})
