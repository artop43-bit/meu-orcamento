// Processo filho: cuida das sessões do seu "pedaço" (hash(session_id) % WORKERS).
// Recebe comandos do supervisor por IPC, varre a fila de envio e manda os eventos para a API.

import { pathToFileURL } from 'node:url'
import pg from 'pg'
import { ApiClient } from './api-client.js'
import { AuthStore, createPgAuthRepository, createPgKvRepository } from './auth-store.js'
import { baileysLevel, createLogger, loadConfig } from './config.js'
import { Gate } from './gate.js'
import { ERROR_TEXTS } from './mapping.js'
import { Session, createVersionResolver, withTimeout } from './session.js'

const MAX_SENT_IDS = 5000

export class Worker {
  /**
   * deps: { api, authStore, logger, createSession(id, hooks), sweepMs?, notify?(msg) }
   * `createSession` devolve um objeto com a interface de Session (start/stop/close/send/read/ready/status/info).
   */
  constructor ({ api, authStore, logger, createSession, sweepMs = 15000, notify = () => {} }) {
    this.api = api
    this.authStore = authStore
    this.logger = logger
    this.createSession = createSession
    this.sweepMs = sweepMs
    this.notify = notify
    this.sessions = new Map()
    this.chains = new Map()
    this.sendChains = new Map()
    this.inFlight = new Set()
    this.sentIds = new Map()
    this.sweeping = null
    this.sweepTimer = null
    this.stopped = false
    this.counters = { sent: 0, failed: 0, skipped: 0, resent_acks: 0 }
  }

  startSweeps () {
    this.sweepTimer = setInterval(() => {
      this.sweep().catch((err) => this.logger.warn({ err: err?.message }, 'Varredura da fila falhou'))
    }, this.sweepMs)
    this.sweepTimer.unref?.()
  }

  /** Comandos de uma mesma sessão rodam em ordem (start depois de stop não se perde). */
  enqueue (sessionId, fn) {
    const previous = this.chains.get(sessionId) || Promise.resolve()
    const result = previous.then(fn)
    const tail = result.catch((err) => {
      this.logger.error({ session: sessionId, err: err?.message }, 'Erro num comando da sessão')
    })
    this.chains.set(sessionId, tail)
    tail.then(() => {
      if (this.chains.get(sessionId) === tail) this.chains.delete(sessionId)
    })
    return result
  }

  getOrCreate (sessionId) {
    let session = this.sessions.get(sessionId)
    if (!session) {
      session = this.createSession(sessionId, {
        onReady: (s) => this.onReady(s),
        onEnded: (s) => this.onEnded(s)
      })
      this.sessions.set(sessionId, session)
    }
    return session
  }

  handle (message) {
    const { cmd, sessionId } = message
    if (!sessionId) return Promise.resolve()
    switch (cmd) {
      case 'start':
        return this.enqueue(sessionId, () => this.getOrCreate(sessionId).start({ ifIdle: Boolean(message.ifIdle) }))
      case 'stop':
        return this.enqueue(sessionId, async () => {
          const session = this.sessions.get(sessionId)
          if (session) {
            await session.stop({ logout: Boolean(message.logout) })
            if (this.sessions.get(sessionId) === session) this.sessions.delete(sessionId)
          } else if (message.logout) {
            await this.authStore.removeAll(sessionId)
          }
        })
      case 'flush':
        return this.flush([sessionId])
      case 'read': {
        const session = this.sessions.get(sessionId)
        if (!session) return Promise.resolve()
        return session.read(message.remote_jid, message.external_ids).catch((err) => {
          this.logger.warn({ session: sessionId, err: err?.message }, 'Confirmação de leitura falhou')
        })
      }
      default:
        this.logger.warn({ cmd }, 'Comando desconhecido')
        return Promise.resolve()
    }
  }

  onReady (session) {
    this.flush([session.id]).catch((err) => this.logger.warn({ err: err?.message }, 'Fila de envio não pôde ser lida'))
  }

  onEnded (session) {
    this.notify({ type: 'session-ended', sessionId: session.id })
    // Tira do mapa depois dos comandos já na fila (se alguém pediu start, a sessão continua).
    void this.enqueue(session.id, () => {
      if (this.sessions.get(session.id) === session && !session.running && session.status === 'stopped') {
        this.sessions.delete(session.id)
      }
    })
  }

  readyIds () {
    return [...this.sessions.values()].filter((s) => s.ready).map((s) => s.id)
  }

  /** Varredura periódica: uma chamada só com todas as sessões prontas deste processo. */
  async sweep () {
    if (this.stopped || this.sweeping) return this.sweeping
    const ids = this.readyIds()
    if (!ids.length) return
    this.sweeping = this.flush(ids).finally(() => {
      this.sweeping = null
    })
    return this.sweeping
  }

  async flush (sessionIds) {
    const ids = sessionIds.filter((id) => this.sessions.get(id)?.ready)
    if (!ids.length || this.stopped) return
    const items = await this.api.getOutbox(ids)
    const tasks = []
    for (const item of items) tasks.push(this.queueSend(item))
    await Promise.allSettled(tasks)
  }

  /** Envia os itens de uma sessão em ordem, um de cada vez. */
  queueSend (item) {
    const sessionId = item.session_id
    if (this.inFlight.has(item.message_id)) return Promise.resolve()
    this.inFlight.add(item.message_id)
    const previous = this.sendChains.get(sessionId) || Promise.resolve()
    const result = previous.then(() => this.sendItem(item)).finally(() => this.inFlight.delete(item.message_id))
    const tail = result.catch(() => {})
    this.sendChains.set(sessionId, tail)
    tail.then(() => {
      if (this.sendChains.get(sessionId) === tail) this.sendChains.delete(sessionId)
    })
    return result
  }

  rememberSent (messageId, externalId) {
    this.sentIds.set(messageId, externalId)
    while (this.sentIds.size > MAX_SENT_IDS) this.sentIds.delete(this.sentIds.keys().next().value)
  }

  async sendItem (item) {
    const session = this.sessions.get(item.session_id)
    const base = { type: 'ack', session_id: item.session_id, message_id: item.message_id }
    // Já foi enviada (a confirmação anterior se perdeu): confirma de novo, sem mandar duas vezes.
    if (this.sentIds.has(item.message_id)) {
      const externalId = this.sentIds.get(item.message_id)
      this.api.push({ ...base, status: 'sent', ...(externalId ? { external_id: externalId } : {}) })
      this.counters.resent_acks += 1
      return
    }
    if (!session) {
      this.counters.skipped += 1
      return
    }
    try {
      const result = await session.send(item)
      if (result?.skipped) {
        // A sessão caiu entre a reserva e o envio: o item volta para a fila depois de 60 s.
        this.counters.skipped += 1
        return
      }
      const externalId = result?.externalId || null
      this.rememberSent(item.message_id, externalId)
      this.api.push({ ...base, status: 'sent', ...(externalId ? { external_id: externalId } : {}) })
      this.counters.sent += 1
    } catch (err) {
      this.logger.warn({ session: item.session_id, err: err?.message }, 'Envio de mensagem falhou')
      this.api.push({ ...base, status: 'failed', error: ERROR_TEXTS.sendFailed })
      this.counters.failed += 1
    }
  }

  stats ({ detail = false } = {}) {
    const memory = process.memoryUsage()
    const byStatus = {}
    for (const s of this.sessions.values()) byStatus[s.status] = (byStatus[s.status] || 0) + 1
    const data = {
      pid: process.pid,
      sessions: this.sessions.size,
      by_status: byStatus,
      rss: memory.rss,
      heap_used: memory.heapUsed,
      events_queued: this.api.queued ?? 0,
      events: this.api.stats ?? {},
      outbox: { ...this.counters }
    }
    if (detail) data.list = [...this.sessions.values()].map((s) => s.info())
    return data
  }

  async shutdown () {
    this.stopped = true
    clearInterval(this.sweepTimer)
    const closing = [...this.sessions.values()].map((s) => s.close())
    await withTimeout(Promise.allSettled(closing), 5000).catch(() => {})
    await this.api.drain?.(3000)
  }
}

async function main () {
  const config = loadConfig()
  const index = Number(process.env.WORKER_INDEX || 0)
  const logger = createLogger(config.logLevel, { proc: `worker-${index}` })
  const baileysLogger = createLogger(baileysLevel(config.logLevel), { proc: `worker-${index}`, lib: 'baileys' })
  const pool = new pg.Pool({ connectionString: config.databaseUrl, max: 4, idleTimeoutMillis: 30000 })
  pool.on('error', (err) => logger.error({ err: err?.message }, 'Erro no pool do Postgres'))
  const api = new ApiClient({ baseUrl: config.apiUrl, token: config.token, logger })
  const authStore = new AuthStore(createPgAuthRepository(pool), { logger: baileysLogger })
  const kv = createPgKvRepository(pool)
  const versions = createVersionResolver({ kv, logger })
  const gate = new Gate(config.maxConcurrentPairings)
  const send = (msg) => {
    if (process.connected) process.send(msg)
  }

  const worker = new Worker({
    api,
    authStore,
    logger,
    notify: send,
    createSession: (id, hooks) => new Session(id, {
      authStore,
      versions,
      emit: (event) => api.push(event),
      uploadMedia: (sid, payload) => api.uploadMedia(sid, payload),
      downloadMedia: (sid, mediaId) => api.downloadMedia(sid, mediaId),
      uploadAvatar: (sid, payload) => api.uploadAvatar(sid, payload),
      logger,
      baileysLogger,
      gate,
      ...hooks
    })
  })
  worker.startSweeps()

  const statsTimer = setInterval(() => send({ type: 'stats', ...worker.stats(), gate: { active: gate.active, waiting: gate.pending } }), 5000)
  statsTimer.unref()

  let shuttingDown = false
  const shutdown = async () => {
    if (shuttingDown) return
    shuttingDown = true
    clearInterval(statsTimer)
    await worker.shutdown()
    await pool.end().catch(() => {})
    process.exit(0)
  }

  process.on('message', (message) => {
    if (!message || typeof message !== 'object') return
    if (message.type === 'cmd') {
      worker.handle(message).catch((err) => logger.error({ err: err?.message }, 'Comando falhou'))
    } else if (message.type === 'stats') {
      send({ type: 'reply', id: message.id, result: { ...worker.stats({ detail: true }), gate: { active: gate.active, waiting: gate.pending } } })
    } else if (message.type === 'shutdown') {
      void shutdown()
    }
  })
  // Supervisor morreu: fecha tudo (sem logout).
  process.on('disconnect', () => void shutdown())
  process.on('SIGTERM', () => void shutdown())
  process.on('SIGINT', () => void shutdown())
  process.on('unhandledRejection', (err) => logger.error({ err: err?.message || String(err) }, 'Promessa rejeitada sem tratamento'))

  send({ type: 'ready', pid: process.pid })
  send({ type: 'stats', ...worker.stats(), gate: { active: gate.active, waiting: gate.pending } })
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((err) => {
    console.error('Falha ao iniciar o processo do conector:', err)
    process.exit(1)
  })
}
