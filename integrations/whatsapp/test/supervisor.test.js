import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { describe, it } from 'node:test'
import { shardFor } from '../src/mapping.js'
import { Supervisor } from '../src/supervisor.js'

// Processo filho de mentira: guarda as mensagens e deixa o teste simular "ready", respostas e quedas.
class FakeChild extends EventEmitter {
  constructor (index, pid) {
    super()
    this.index = index
    this.pid = pid
    this.sent = []
    this.exitCode = null
    this.killed = null
  }

  send (message) {
    if (this.exitCode !== null) throw new Error('canal fechado')
    this.sent.push(message)
    if (message.type === 'shutdown') setImmediate(() => this.die(0))
    if (message.type === 'stats' && this.answerStats) {
      setImmediate(() => this.emit('message', { type: 'reply', id: message.id, result: { sessions: 2, rss: 50 * 1048576 } }))
    }
  }

  kill (signal) {
    this.killed = signal
    this.die(null, signal)
  }

  ready () {
    this.emit('message', { type: 'ready', pid: this.pid })
  }

  die (code = 1, signal = null) {
    if (this.exitCode !== null) return
    this.exitCode = code ?? 0
    this.emit('exit', code, signal)
  }

  cmds () {
    return this.sent.filter((m) => m.type === 'cmd')
  }
}

const silent = { warn () {}, error () {}, info () {} }
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function waitFor (cond, timeoutMs = 2000) {
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

function setup (opts = {}) {
  const children = []
  let pid = 100
  const sup = new Supervisor({
    workers: 2,
    logger: silent,
    restoreSpacingMs: 20,
    restartBaseMs: 20,
    restartMaxMs: 80,
    retryBaseMs: 10,
    retryMaxMs: 20,
    statsTimeoutMs: 100,
    fork: (index) => {
      const child = new FakeChild(index, pid++)
      children.push(child)
      return child
    },
    ...opts
  })
  sup.start()
  const current = (index) => children.filter((c) => c.index === index).at(-1)
  return { sup, children, current }
}

// Ids com processo conhecido (hash estável): dois de cada processo.
const IDS = Array.from({ length: 40 }, (_, i) => `00000000-0000-4000-8000-${String(i).padStart(12, '0')}`)
const ON_0 = IDS.filter((id) => shardFor(id, 2) === 0)
const ON_1 = IDS.filter((id) => shardFor(id, 2) === 1)

describe('Supervisor', () => {
  it('cada sessão vai sempre para o processo hash(id) % WORKERS', () => {
    const { sup, current } = setup()
    current(0).ready()
    current(1).ready()
    for (const id of [...ON_0.slice(0, 3), ...ON_1.slice(0, 3)]) {
      sup.dispatch('start', id)
      sup.dispatch('flush', id.toUpperCase().toLowerCase())
    }
    for (const msg of current(0).cmds()) assert.equal(shardFor(msg.sessionId, 2), 0)
    for (const msg of current(1).cmds()) assert.equal(shardFor(msg.sessionId, 2), 1)
    assert.equal(current(0).cmds().length, 6)
    assert.equal(current(1).cmds().length, 6)
    assert.deepEqual(current(0).cmds()[0], { type: 'cmd', cmd: 'start', sessionId: ON_0[0] })
  })

  it('leva o payload junto (stop com logout, read com ids)', () => {
    const { sup, current } = setup()
    current(0).ready()
    sup.dispatch('stop', ON_0[0], { logout: true })
    sup.dispatch('read', ON_0[0], { remote_jid: 'x@lid', external_ids: ['A'] })
    assert.deepEqual(current(0).cmds(), [
      { type: 'cmd', cmd: 'stop', sessionId: ON_0[0], logout: true },
      { type: 'cmd', cmd: 'read', sessionId: ON_0[0], remote_jid: 'x@lid', external_ids: ['A'] }
    ])
  })

  it('antes do processo ficar pronto: start é reenviado no ready e stop fica guardado', async () => {
    const { sup, current } = setup()
    sup.dispatch('start', ON_0[0])
    sup.dispatch('start', ON_0[1])
    sup.dispatch('stop', ON_0[1])
    sup.dispatch('flush', ON_0[0]) // flush sem processo é descartado (a varredura cobre)
    assert.equal(current(0).cmds().length, 0)
    current(0).ready()
    await waitFor(() => current(0).cmds().length >= 2)
    await sleep(40)
    assert.deepEqual(current(0).cmds(), [
      { type: 'cmd', cmd: 'stop', sessionId: ON_0[1] },
      { type: 'cmd', cmd: 'start', sessionId: ON_0[0], ifIdle: true }
    ])
  })

  it('processo que cai é religado com espera e recebe de novo o start das suas sessões, espaçados', async () => {
    const { sup, children, current } = setup()
    current(0).ready()
    current(1).ready()
    const mine = ON_0.slice(0, 3)
    for (const id of mine) sup.dispatch('start', id)
    sup.dispatch('start', ON_1[0])
    // Uma das sessões terminou sozinha (QR expirou): não volta depois da queda.
    current(0).emit('message', { type: 'session-ended', sessionId: mine[2] })

    const old = current(0)
    old.die(1)
    assert.equal(sup.health().ok, false)
    assert.equal(sup.health().workers, 1)
    await waitFor(() => current(0) !== old)
    assert.equal(children.length, 3, 'só o processo que caiu foi religado')
    current(0).ready()
    await waitFor(() => current(0).cmds().length === 2)
    const replayed = current(0).cmds()
    assert.deepEqual(replayed.map((m) => m.sessionId), mine.slice(0, 2))
    assert.ok(replayed.every((m) => m.cmd === 'start' && m.ifIdle === true))
    assert.equal(current(1).cmds().length, 1, 'o outro processo não é afetado')
    assert.equal(sup.health().ok, true)
    assert.equal(sup.slots[0].restarts, 1)
  })

  it('quedas seguidas aumentam a espera para religar', async () => {
    const { sup, current } = setup({ restartBaseMs: 30, restartMaxMs: 1000, stableMs: 60000 })
    current(0).ready()
    const t0 = Date.now()
    let child = current(0)
    child.die(1)
    await waitFor(() => current(0) !== child)
    const first = Date.now() - t0
    child = current(0)
    const t1 = Date.now()
    child.die(1)
    await waitFor(() => current(0) !== child)
    const second = Date.now() - t1
    assert.ok(first >= 25, `primeira espera ${first} ms`)
    assert.ok(second >= 55, `segunda espera ${second} ms (dobrou)`)
    assert.equal(sup.slots[0].crashes, 2)
    await sup.shutdown(100)
  })

  it('restaura da API com novas tentativas e espaçamento entre as sessões', async () => {
    let calls = 0
    const api = {
      async getSessions () {
        calls += 1
        if (calls < 3) throw new Error('API ainda subindo')
        return [ON_0[0], ON_1[0], ON_0[1]]
      }
    }
    const { sup, current } = setup({ api, restoreSpacingMs: 30 })
    current(0).ready()
    current(1).ready()
    const t0 = Date.now()
    const ids = await sup.restore()
    const took = Date.now() - t0
    assert.equal(calls, 3)
    assert.deepEqual(ids, [ON_0[0], ON_1[0], ON_0[1]])
    assert.ok(took >= 60, `duas esperas de 30 ms entre as 3 sessões (levou ${took} ms)`)
    assert.deepEqual(current(0).cmds().map((m) => [m.sessionId, m.ifIdle]), [[ON_0[0], true], [ON_0[1], true]])
    assert.deepEqual(current(1).cmds().map((m) => m.sessionId), [ON_1[0]])
  })

  it('restore para quando o desligamento é pedido', async () => {
    const controller = new AbortController()
    const api = { async getSessions () { throw new Error('fora do ar') } }
    const { sup } = setup({ api })
    const done = sup.restore({ signal: controller.signal })
    await sleep(30)
    controller.abort()
    assert.deepEqual(await done, [])
  })

  it('health soma memória e sessões dos processos; stats pergunta a cada um', async () => {
    const { sup, current } = setup()
    current(0).ready()
    current(1).ready()
    current(0).emit('message', { type: 'stats', sessions: 3, rss: 100 * 1048576 })
    current(1).emit('message', { type: 'stats', sessions: 4, rss: 100 * 1048576 })
    const health = sup.health()
    assert.equal(health.ok, true)
    assert.equal(health.workers, 2)
    assert.equal(health.sessions, 7)
    assert.ok(health.rss_mb >= 200)

    current(0).answerStats = true // o processo 1 não responde: cai no tempo limite
    const stats = await sup.stats()
    assert.equal(stats.workers.length, 2)
    assert.equal(stats.workers[0].sessions, 2)
    assert.equal(stats.workers[0].rss_mb, 50)
    assert.equal(stats.workers[1].sessions, 4, 'usa o último stats enviado')
  })

  it('desligamento pede para cada processo fechar (sem logout) e não religa ninguém', async () => {
    const { sup, children, current } = setup()
    current(0).ready()
    current(1).ready()
    await sup.shutdown(500)
    for (const child of children) {
      assert.ok(child.sent.some((m) => m.type === 'shutdown'))
      assert.equal(child.killed, null, 'saiu sozinho, sem SIGKILL')
    }
    await sleep(50)
    assert.equal(children.length, 2)
  })

  it('desligamento mata quem não sai a tempo', async () => {
    const { sup, current } = setup()
    current(0).ready()
    current(0).send = function (message) { this.sent.push(message) } // ignora o pedido
    current(1).ready()
    await sup.shutdown(50)
    assert.equal(current(0).killed, 'SIGKILL')
  })
})
