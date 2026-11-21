import assert from 'node:assert/strict'
import http from 'node:http'
import { after, before, beforeEach, describe, it } from 'node:test'
import { ApiClient, ApiError } from '../src/api-client.js'

// API de mentira: guarda cada chamada e responde conforme `plan` (lista de status, consumida em ordem).
const calls = []
let plan = []
let hang = false
let server
let baseUrl

function waitFor (cond, timeoutMs = 3000) {
  const start = Date.now()
  return new Promise((resolve, reject) => {
    const tick = () => {
      if (cond()) return resolve()
      if (Date.now() - start > timeoutMs) return reject(new Error('tempo esgotado esperando a condição'))
      setTimeout(tick, 5)
    }
    tick()
  })
}

const silent = { warn () {}, error () {}, info () {} }

function client (opts = {}) {
  return new ApiClient({ baseUrl, token: 'segredo', logger: silent, batchMs: 30, retryBaseMs: 20, retryMaxMs: 40, timeoutMs: 500, ...opts })
}

before(async () => {
  server = http.createServer((req, res) => {
    let text = ''
    req.on('data', (c) => { text += c })
    req.on('end', () => {
      calls.push({ method: req.method, url: req.url, headers: req.headers, body: text ? JSON.parse(text) : null, at: Date.now() })
      if (hang) return // nunca responde: testa o tempo limite
      const status = plan.length ? plan.shift() : 200
      res.writeHead(status, { 'content-type': 'application/json' })
      if (req.url.startsWith('/api/messaging/connector/sessions')) {
        res.end(JSON.stringify({ sessions: [{ session_id: 'a' }, { session_id: 'b' }, {}] }))
      } else if (req.url.startsWith('/api/messaging/connector/outbox')) {
        const ids = new URL(req.url, 'http://x').searchParams.get('session_ids').split(',')
        res.end(JSON.stringify({ items: ids.map((id) => ({ message_id: `m-${id}`, session_id: id })) }))
      } else {
        res.end(JSON.stringify({ processed: 1, ignored: 0 }))
      }
    })
  })
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  baseUrl = `http://127.0.0.1:${server.address().port}/`
})

after(() => {
  server.closeAllConnections?.()
  server.close()
})

beforeEach(() => {
  calls.length = 0
  plan = []
  hang = false
})

const events = () => calls.filter((c) => c.url === '/api/messaging/connector/events')

describe('ApiClient', () => {
  it('manda o token em toda chamada e lê a lista de sessões', async () => {
    const ids = await client().getSessions()
    assert.deepEqual(ids, ['a', 'b'])
    assert.equal(calls[0].headers['x-connector-token'], 'segredo')
    assert.equal(calls[0].method, 'GET')
    assert.equal(calls[0].url, '/api/messaging/connector/sessions')
  })

  it('busca a fila com até 200 ids por chamada', async () => {
    const ids = Array.from({ length: 450 }, (_, i) => `s${i}`)
    const items = await client().getOutbox(ids, 50)
    assert.equal(items.length, 450)
    const outbox = calls.filter((c) => c.url.startsWith('/api/messaging/connector/outbox'))
    assert.equal(outbox.length, 3)
    const first = new URL(outbox[0].url, 'http://x').searchParams
    assert.equal(first.get('session_ids').split(',').length, 200)
    assert.equal(first.get('limit'), '50')
  })

  it('junta os eventos de até 500 ms num lote só', async () => {
    const api = client({ batchMs: 60 })
    api.push({ type: 'status', n: 1 })
    api.push({ type: 'status', n: 2 })
    api.push({ type: 'status', n: 3 })
    assert.equal(events().length, 0)
    await waitFor(() => events().length === 1 && api.queued === 0)
    assert.deepEqual(events()[0].body.events.map((e) => e.n), [1, 2, 3])
    assert.equal(api.stats.sent, 3)
  })

  it('lote cheio (100 eventos) vai na hora, em ordem, e o resto vai depois', async () => {
    const api = client({ batchMs: 10000, batchSize: 100 })
    for (let n = 0; n < 250; n++) api.push({ n })
    await waitFor(() => events().length >= 2)
    assert.equal(events()[0].body.events.length, 100)
    assert.equal(events()[1].body.events.length, 100)
    assert.equal(events()[0].body.events[0].n, 0)
    assert.equal(events()[1].body.events[0].n, 100)
    // Os 50 restantes esperam o prazo do lote (aqui 10 s): ainda na fila.
    await new Promise((resolve) => setTimeout(resolve, 50))
    assert.equal(api.queued, 50)
    await api.drain(1000)
    assert.equal(api.queued, 0)
    assert.equal(events().at(-1).body.events.length, 50)
  })

  it('reenvia o mesmo lote com espera quando a API falha, sem perder nem duplicar', async () => {
    plan = [500, 503]
    const api = client()
    api.push({ n: 1 })
    api.push({ n: 2 })
    await waitFor(() => api.queued === 0, 3000)
    const posts = events()
    assert.equal(posts.length, 3)
    for (const post of posts) assert.deepEqual(post.body.events.map((e) => e.n), [1, 2])
    assert.ok(posts[2].at - posts[1].at >= 15, 'espera antes de tentar de novo')
    assert.equal(api.stats.sent, 2)
    assert.equal(api.stats.failedPosts, 2)
    assert.equal(api.failures, 0)
  })

  it('descarta o lote que a API recusa (400), sem tentar de novo', async () => {
    plan = [400]
    const api = client()
    api.push({ n: 1 })
    await waitFor(() => api.queued === 0)
    await new Promise((resolve) => setTimeout(resolve, 80))
    assert.equal(events().length, 1)
    assert.equal(api.stats.discarded, 1)
  })

  it('fila limitada: passa do limite e descarta os mais antigos', async () => {
    const api = client({ batchMs: 10000, batchSize: 1000, maxQueue: 5 })
    for (let n = 0; n < 8; n++) api.push({ n })
    assert.equal(api.queued, 5)
    assert.equal(api.stats.dropped, 3)
    await api.drain(1000)
    assert.deepEqual(events()[0].body.events.map((e) => e.n), [3, 4, 5, 6, 7])
  })

  it('chamada que não responde estoura o tempo limite como falha de rede', async () => {
    hang = true
    const api = client({ timeoutMs: 100 })
    await assert.rejects(api.getSessions(), (err) => err instanceof ApiError && err.status === 0)
  })

  it('erro HTTP vira ApiError com o status', async () => {
    plan = [401]
    await assert.rejects(client().getSessions(), (err) => err instanceof ApiError && err.status === 401)
  })

  it('depois do drain (desligamento) não aceita mais eventos', async () => {
    const api = client()
    await api.drain(100)
    api.push({ n: 1 })
    assert.equal(api.queued, 0)
  })
})
