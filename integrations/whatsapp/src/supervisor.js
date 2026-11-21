// Supervisor: liga os processos filhos, distribui cada sessão pelo hash do id, religa quem cair
// (reenviando o start das sessões dele) e restaura as sessões da API ao ligar.

import { backoffDelay, shardFor } from './mapping.js'

const MB = 1024 * 1024
const MAX_QUEUED = 1000

export class Supervisor {
  /**
   * opts: { workers, fork(index) → ChildProcess (ou objeto parecido), api?, logger,
   *         restoreSpacingMs?, restartBaseMs?, restartMaxMs?, stableMs?, statsTimeoutMs?, retryBaseMs? }
   */
  constructor ({
    workers,
    fork,
    api,
    logger,
    restoreSpacingMs = 300,
    restartBaseMs = 1000,
    restartMaxMs = 30000,
    stableMs = 60000,
    statsTimeoutMs = 3000,
    retryBaseMs = 2000,
    retryMaxMs = 30000
  }) {
    this.count = Math.max(1, workers)
    this.forkFn = fork
    this.api = api
    this.logger = logger
    this.restoreSpacingMs = restoreSpacingMs
    this.restartBaseMs = restartBaseMs
    this.restartMaxMs = restartMaxMs
    this.stableMs = stableMs
    this.statsTimeoutMs = statsTimeoutMs
    this.retryBaseMs = retryBaseMs
    this.retryMaxMs = retryMaxMs
    this.slots = []
    this.requestId = 0
    this.shuttingDown = false
    this.restoreTimer = null
  }

  start () {
    for (let index = 0; index < this.count; index++) {
      this.slots.push({
        index,
        child: null,
        alive: false,
        startedAt: 0,
        crashes: 0,
        restarts: 0,
        restartTimer: null,
        replayTimer: null,
        stats: null,
        pending: new Map(),
        active: new Set(),
        queued: []
      })
      this.spawn(this.slots[index])
    }
  }

  spawn (slot) {
    const child = this.forkFn(slot.index)
    slot.child = child
    slot.alive = false
    slot.startedAt = Date.now()
    child.on('message', (message) => this.onMessage(slot, child, message))
    child.on('exit', (code, signal) => this.onExit(slot, child, code, signal))
    child.on('error', (err) => this.logger.error({ worker: slot.index, err: err?.message }, 'Erro no processo filho'))
  }

  onMessage (slot, child, message) {
    if (slot.child !== child || !message || typeof message !== 'object') return
    switch (message.type) {
      case 'ready':
        slot.alive = true
        this.replay(slot)
        break
      case 'stats':
        slot.stats = { ...message, at: Date.now() }
        break
      case 'reply': {
        const pending = slot.pending.get(message.id)
        if (pending) {
          clearTimeout(pending.timer)
          slot.pending.delete(message.id)
          pending.resolve(message.result)
        }
        break
      }
      case 'session-ended':
        slot.active.delete(message.sessionId)
        break
      default:
        break
    }
  }

  onExit (slot, child, code, signal) {
    if (slot.child !== child) return
    slot.alive = false
    slot.child = null
    slot.stats = null
    clearTimeout(slot.replayTimer)
    for (const [id, pending] of slot.pending) {
      clearTimeout(pending.timer)
      pending.resolve(null)
      slot.pending.delete(id)
    }
    if (this.shuttingDown) return
    const ranFor = Date.now() - slot.startedAt
    slot.crashes = ranFor > this.stableMs ? 1 : slot.crashes + 1
    const delay = backoffDelay(slot.crashes - 1, { baseMs: this.restartBaseMs, maxMs: this.restartMaxMs })
    this.logger.error({ worker: slot.index, code, signal, delay }, 'Processo filho caiu; religando')
    slot.restartTimer = setTimeout(() => {
      slot.restartTimer = null
      if (this.shuttingDown) return
      slot.restarts += 1
      this.spawn(slot)
    }, delay)
  }

  /** Processo (re)ligado: entrega os comandos guardados e reinicia as sessões dele, espaçadas. */
  replay (slot) {
    const queued = slot.queued.splice(0)
    for (const message of queued) this.send(slot, message)
    const ids = [...slot.active]
    let i = 0
    const next = () => {
      slot.replayTimer = null
      while (i < ids.length && !slot.active.has(ids[i])) i++
      if (i >= ids.length || !slot.alive) return
      this.send(slot, { type: 'cmd', cmd: 'start', sessionId: ids[i], ifIdle: true })
      i++
      if (i < ids.length) slot.replayTimer = setTimeout(next, this.restoreSpacingMs)
    }
    next()
  }

  send (slot, message) {
    try {
      slot.child.send(message)
      return true
    } catch (err) {
      this.logger.warn({ worker: slot.index, err: err?.message }, 'Não foi possível falar com o processo filho')
      return false
    }
  }

  slotFor (sessionId) {
    return this.slots[shardFor(sessionId, this.count)]
  }

  /** Encaminha um comando ao processo da sessão (ou guarda até ele voltar). */
  dispatch (cmd, sessionId, payload = {}) {
    const slot = this.slotFor(sessionId)
    if (!slot) return false
    if (cmd === 'start') slot.active.add(sessionId)
    if (cmd === 'stop') slot.active.delete(sessionId)
    const message = { type: 'cmd', cmd, sessionId, ...payload }
    if (slot.alive && slot.child) return this.send(slot, message)
    // Processo fora do ar: o start volta sozinho (lista de sessões ativas); stop fica guardado.
    if (cmd === 'stop') {
      slot.queued.push(message)
      if (slot.queued.length > MAX_QUEUED) slot.queued.shift()
    }
    return true
  }

  /** Ao ligar: pede à API as sessões com wanted=true (tentando até a API responder). */
  async restore ({ signal } = {}) {
    if (!this.api) return []
    let attempt = 0
    let ids
    while (!this.shuttingDown && !signal?.aborted) {
      try {
        ids = await this.api.getSessions()
        break
      } catch (err) {
        const delay = backoffDelay(attempt++, { baseMs: this.retryBaseMs, maxMs: this.retryMaxMs })
        this.logger.warn({ err: err?.message, delay }, 'API ainda não respondeu a lista de sessões; tentando de novo')
        await new Promise((resolve) => {
          this.restoreTimer = setTimeout(resolve, delay)
        })
      }
    }
    if (!ids) return []
    for (let i = 0; i < ids.length; i++) {
      if (this.shuttingDown) break
      this.dispatch('start', ids[i], { ifIdle: true })
      if (i < ids.length - 1) {
        await new Promise((resolve) => {
          this.restoreTimer = setTimeout(resolve, this.restoreSpacingMs)
        })
      }
    }
    return ids
  }

  health () {
    const alive = this.slots.filter((s) => s.alive)
    let rss = process.memoryUsage().rss
    let sessions = 0
    for (const slot of alive) {
      rss += slot.stats?.rss || 0
      sessions += slot.stats?.sessions || 0
    }
    return {
      ok: this.slots.length > 0 && alive.length === this.slots.length,
      workers: alive.length,
      sessions,
      rss_mb: Math.round(rss / MB)
    }
  }

  requestStats (slot) {
    if (!slot.alive || !slot.child) return Promise.resolve(null)
    const id = ++this.requestId
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        slot.pending.delete(id)
        resolve(null)
      }, this.statsTimeoutMs)
      slot.pending.set(id, { resolve, timer })
      if (!this.send(slot, { type: 'stats', id })) {
        clearTimeout(timer)
        slot.pending.delete(id)
        resolve(null)
      }
    })
  }

  async stats () {
    const memory = process.memoryUsage()
    const details = await Promise.all(this.slots.map((slot) => this.requestStats(slot)))
    return {
      supervisor: {
        pid: process.pid,
        uptime_s: Math.round(process.uptime()),
        rss_mb: Math.round(memory.rss / MB)
      },
      workers: this.slots.map((slot, i) => {
        const data = details[i] || slot.stats || {}
        return {
          index: slot.index,
          alive: slot.alive,
          pid: slot.child?.pid ?? null,
          restarts: slot.restarts,
          active_sessions: slot.active.size,
          sessions: data.sessions ?? 0,
          by_status: data.by_status ?? {},
          rss_mb: data.rss ? Math.round(data.rss / MB) : 0,
          heap_used_mb: data.heap_used ? Math.round(data.heap_used / MB) : 0,
          events_queued: data.events_queued ?? 0,
          events: data.events ?? {},
          outbox: data.outbox ?? {},
          gate: data.gate ?? null,
          list: data.list ?? undefined
        }
      })
    }
  }

  /** Desligamento: pede aos filhos para fechar os sockets (sem logout) e espera um pouco. */
  async shutdown (timeoutMs = 10000) {
    this.shuttingDown = true
    clearTimeout(this.restoreTimer)
    const exits = []
    for (const slot of this.slots) {
      clearTimeout(slot.restartTimer)
      clearTimeout(slot.replayTimer)
      const child = slot.child
      if (!child) continue
      exits.push(new Promise((resolve) => {
        if (child.exitCode !== null && child.exitCode !== undefined) return resolve()
        const timer = setTimeout(() => {
          try {
            child.kill('SIGKILL')
          } catch {
            // já saiu
          }
          resolve()
        }, timeoutMs)
        child.once('exit', () => {
          clearTimeout(timer)
          resolve()
        })
      }))
      this.send(slot, { type: 'shutdown' })
    }
    await Promise.all(exits)
  }
}
