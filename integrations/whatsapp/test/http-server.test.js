import assert from 'node:assert/strict'
import { after, before, beforeEach, describe, it } from 'node:test'
import { createHttpServer, tokenMatches } from '../src/http-server.js'

const TOKEN = 'token-de-teste'
const SID = 'AAAAAAAA-bbbb-cccc-dddd-eeeeeeeeeeee'

// Supervisor de mentira: guarda os comandos recebidos.
const dispatched = []
const fakeSupervisor = {
  dispatch (cmd, sessionId, payload) {
    dispatched.push({ cmd, sessionId, payload })
    return true
  },
  health () {
    return { ok: true, workers: 2, sessions: 3, rss_mb: 40 }
  },
  async stats () {
    return { supervisor: { pid: 1 }, workers: [] }
  }
}

const silent = { warn () {}, error () {}, info () {} }
const servers = []

async function start (opts) {
  const server = createHttpServer({ logger: silent, ...opts })
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  servers.push(server)
  return `http://127.0.0.1:${server.address().port}`
}

let base

before(async () => {
  base = await start({ token: TOKEN, supervisor: fakeSupervisor, configured: true })
})

after(() => {
  for (const server of servers) {
    server.closeAllConnections?.()
    server.close()
  }
})

beforeEach(() => {
  dispatched.length = 0
})

function call (path, { method = 'GET', token = TOKEN, body, raw } = {}) {
  const headers = {}
  if (token) headers['x-connector-token'] = token
  if (body !== undefined || raw !== undefined) headers['content-type'] = 'application/json'
  return fetch(base + path, { method, headers, body: raw ?? (body === undefined ? undefined : JSON.stringify(body)) })
}

describe('tokenMatches', () => {
  it('compara em tempo constante e nunca aceita token vazio', () => {
    assert.equal(tokenMatches('abc', 'abc'), true)
    assert.equal(tokenMatches('abc', 'abd'), false)
    assert.equal(tokenMatches('abc', 'abcd'), false)
    assert.equal(tokenMatches('abc', undefined), false)
    assert.equal(tokenMatches('', ''), false)
    assert.equal(tokenMatches('', 'qualquer'), false)
    assert.equal(tokenMatches('abc', ['abc']), false)
  })
})

describe('API HTTP interna', () => {
  it('/health responde sem token', async () => {
    const res = await call('/health', { token: null })
    assert.equal(res.status, 200)
    assert.deepEqual(await res.json(), { ok: true, workers: 2, sessions: 3, rss_mb: 40 })
  })

  it('sem token ou com token errado: 401', async () => {
    assert.equal((await call('/stats', { token: null })).status, 401)
    assert.equal((await call('/stats', { token: 'errado' })).status, 401)
    const res = await call(`/sessions/${SID}/start`, { method: 'POST', token: 'errado' })
    assert.equal(res.status, 401)
    assert.equal(dispatched.length, 0)
  })

  it('/stats com token', async () => {
    const res = await call('/stats')
    assert.equal(res.status, 200)
    assert.equal((await res.json()).supervisor.pid, 1)
  })

  it('start/flush: 202 e encaminha ao supervisor com o id em minúsculas', async () => {
    let res = await call(`/sessions/${SID}/start`, { method: 'POST' })
    assert.equal(res.status, 202)
    assert.deepEqual(await res.json(), { ok: true })
    res = await call(`/sessions/${SID}/flush/`, { method: 'POST' })
    assert.equal(res.status, 202)
    assert.deepEqual(dispatched, [
      { cmd: 'start', sessionId: SID.toLowerCase(), payload: {} },
      { cmd: 'flush', sessionId: SID.toLowerCase(), payload: {} }
    ])
  })

  it('stop leva o logout só quando é true de verdade', async () => {
    await call(`/sessions/${SID}/stop`, { method: 'POST', body: { logout: true } })
    await call(`/sessions/${SID}/stop`, { method: 'POST', body: { logout: false } })
    await call(`/sessions/${SID}/stop`, { method: 'POST', body: { logout: 'sim' } })
    await call(`/sessions/${SID}/stop`, { method: 'POST' })
    assert.deepEqual(dispatched.map((d) => d.payload.logout), [true, false, false, false])
  })

  it('read valida o corpo', async () => {
    let res = await call(`/sessions/${SID}/read`, {
      method: 'POST',
      body: { remote_jid: '5511999999999@s.whatsapp.net', external_ids: ['A1', '', 7, 'B2'] }
    })
    assert.equal(res.status, 202)
    assert.deepEqual(dispatched[0].payload, { remote_jid: '5511999999999@s.whatsapp.net', external_ids: ['A1', 'B2'] })

    res = await call(`/sessions/${SID}/read`, { method: 'POST', body: { remote_jid: 'sem-arroba', external_ids: [] } })
    assert.equal(res.status, 400)
    res = await call(`/sessions/${SID}/read`, { method: 'POST', body: { remote_jid: 'x@lid', external_ids: 'A1' } })
    assert.equal(res.status, 400)
    assert.equal(dispatched.length, 1)
  })

  it('id que não é uuid: 400; JSON inválido: 400', async () => {
    assert.equal((await call('/sessions/nao-e-uuid/start', { method: 'POST' })).status, 400)
    assert.equal((await call('/sessions/%E0%A4%A/start', { method: 'POST' })).status, 400)
    assert.equal((await call(`/sessions/${SID}/stop`, { method: 'POST', raw: '{quebrado' })).status, 400)
    assert.equal(dispatched.length, 0)
  })

  it('corpo grande demais: 413', async () => {
    const res = await call(`/sessions/${SID}/stop`, { method: 'POST', raw: JSON.stringify({ x: 'a'.repeat(70 * 1024) }) }).catch(() => null)
    // O servidor pode cortar a conexão no meio do envio; se respondeu, foi 413.
    if (res) assert.equal(res.status, 413)
    assert.equal(dispatched.length, 0)
  })

  it('rota desconhecida ou método errado: 404', async () => {
    assert.equal((await call('/nada')).status, 404)
    assert.equal((await call(`/sessions/${SID}/start`)).status, 404)
    assert.equal((await call(`/sessions/${SID}/apagar`, { method: 'POST' })).status, 404)
  })

  it('sem configuração: /health continua 200 e o resto responde 503', async () => {
    const off = await start({ token: '', supervisor: null, configured: false })
    let res = await fetch(`${off}/health`)
    assert.equal(res.status, 200)
    const body = await res.json()
    assert.equal(body.ok, true)
    assert.equal(body.configured, false)
    assert.equal(typeof body.rss_mb, 'number')
    // Sem token configurado nada passa.
    res = await fetch(`${off}/sessions/${SID}/start`, { method: 'POST', headers: { 'x-connector-token': '' } })
    assert.equal(res.status, 401)

    const half = await start({ token: TOKEN, supervisor: null, configured: false })
    res = await fetch(`${half}/sessions/${SID}/start`, { method: 'POST', headers: { 'x-connector-token': TOKEN } })
    assert.equal(res.status, 503)
  })

  it('supervisor com processo fora do ar: /health 503', async () => {
    const down = await start({ token: TOKEN, configured: true, supervisor: { ...fakeSupervisor, health: () => ({ ok: false, workers: 1, sessions: 0, rss_mb: 30 }) } })
    const res = await fetch(`${down}/health`)
    assert.equal(res.status, 503)
  })
})
