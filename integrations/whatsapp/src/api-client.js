// Conversa com a API do Hub (prefixo /api/messaging/connector), sempre com X-Connector-Token.
// Os eventos vão em lote (até 500 ms ou 100 eventos) e são reenviados com espera se a API falhar.

import { backoffDelay } from './mapping.js'

const PREFIX = '/api/messaging/connector'
// Erros em que reenviar o mesmo lote não adianta (o lote é descartado e fica no log).
const DROP_STATUSES = new Set([400, 404, 413, 422])

export class ApiError extends Error {
  constructor (message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export class ApiClient {
  constructor ({
    baseUrl,
    token,
    logger,
    fetchImpl = globalThis.fetch,
    batchMs = 500,
    batchSize = 100,
    maxQueue = 10000,
    timeoutMs = 10000,
    retryBaseMs = 1000,
    retryMaxMs = 30000
  }) {
    this.baseUrl = String(baseUrl || '').replace(/\/+$/, '')
    this.token = token
    this.logger = logger
    this.fetch = fetchImpl
    this.batchMs = batchMs
    this.batchSize = batchSize
    this.maxQueue = maxQueue
    this.timeoutMs = timeoutMs
    this.retryBaseMs = retryBaseMs
    this.retryMaxMs = retryMaxMs
    this.queue = []
    this.timer = null
    this.sending = null
    this.failures = 0
    this.closed = false
    this.stats = { sent: 0, dropped: 0, discarded: 0, failedPosts: 0 }
    this.lastDropLog = 0
  }

  async request (method, path, body) {
    const headers = { 'x-connector-token': this.token, accept: 'application/json' }
    const init = { method, headers, signal: AbortSignal.timeout(this.timeoutMs) }
    if (body !== undefined) {
      headers['content-type'] = 'application/json'
      init.body = JSON.stringify(body)
    }
    let res
    try {
      res = await this.fetch(this.baseUrl + path, init)
    } catch (err) {
      throw new ApiError(`Falha de rede ao chamar a API (${method} ${path}): ${err?.message || err}`, 0)
    }
    if (!res.ok) {
      throw new ApiError(`A API respondeu ${res.status} em ${method} ${path}`, res.status)
    }
    const text = await res.text()
    return text ? JSON.parse(text) : {}
  }

  /** Sessões que a API quer manter conectadas (wanted=true). */
  async getSessions () {
    const data = await this.request('GET', `${PREFIX}/sessions`)
    return (data.sessions || []).map((s) => s.session_id).filter(Boolean)
  }

  /** Fila de envio das sessões dadas (até 200 ids por chamada). */
  async getOutbox (sessionIds, limit = 50) {
    const items = []
    for (let i = 0; i < sessionIds.length; i += 200) {
      const ids = sessionIds.slice(i, i + 200)
      const query = new URLSearchParams({ session_ids: ids.join(','), limit: String(limit) })
      const data = await this.request('GET', `${PREFIX}/outbox?${query}`)
      items.push(...(data.items || []))
    }
    return items
  }

  /** Envia uma mídia baixada do WhatsApp para a API guardar e devolver o `media_id`. */
  async uploadMedia (sessionId, { buffer, kind = 'document', mimeType = 'application/octet-stream', fileName = null }) {
    const query = new URLSearchParams({ kind, mime_type: mimeType })
    if (fileName) query.set('file_name', fileName)
    const path = `${PREFIX}/sessions/${sessionId}/media?${query}`
    let res
    try {
      res = await this.fetch(this.baseUrl + path, {
        method: 'POST',
        headers: {
          'x-connector-token': this.token,
          'content-type': mimeType,
          accept: 'application/json'
        },
        body: buffer,
        signal: AbortSignal.timeout(Math.max(this.timeoutMs, 25000))
      })
    } catch (err) {
      throw new ApiError(`Falha de rede ao enviar mídia (${path}): ${err?.message || err}`, 0)
    }
    if (!res.ok) throw new ApiError(`A API respondeu ${res.status} ao enviar mídia`, res.status)
    const text = await res.text()
    return text ? JSON.parse(text) : {}
  }

  /** Baixa o binário de uma mídia da fila de envio criada pela pessoa no Hub. */
  async downloadMedia (sessionId, mediaId) {
    const path = `${PREFIX}/sessions/${sessionId}/media/${mediaId}`
    let res
    try {
      res = await this.fetch(this.baseUrl + path, {
        method: 'GET',
        headers: { 'x-connector-token': this.token },
        signal: AbortSignal.timeout(Math.max(this.timeoutMs, 25000))
      })
    } catch (err) {
      throw new ApiError(`Falha de rede ao baixar mídia (${path}): ${err?.message || err}`, 0)
    }
    if (!res.ok) throw new ApiError(`A API respondeu ${res.status} ao baixar mídia`, res.status)
    return Buffer.from(await res.arrayBuffer())
  }

  /** Envia a foto de perfil de um contato para a API. */
  async uploadAvatar (sessionId, { jid, jidAlt = null, buffer, mimeType = 'image/jpeg' }) {
    const query = new URLSearchParams({ jid, mime_type: mimeType })
    if (jidAlt) query.set('jid_alt', jidAlt)
    const path = `${PREFIX}/sessions/${sessionId}/avatar?${query}`
    let res
    try {
      res = await this.fetch(this.baseUrl + path, {
        method: 'POST',
        headers: {
          'x-connector-token': this.token,
          'content-type': mimeType,
          accept: 'application/json'
        },
        body: buffer,
        signal: AbortSignal.timeout(Math.max(this.timeoutMs, 15000))
      })
    } catch (err) {
      throw new ApiError(`Falha de rede ao enviar foto de perfil (${path}): ${err?.message || err}`, 0)
    }
    if (!res.ok) throw new ApiError(`A API respondeu ${res.status} ao enviar foto de perfil`, res.status)
    const text = await res.text()
    return text ? JSON.parse(text) : {}
  }

  /** Põe um evento na fila. Se a fila passar do limite, descarta o mais antigo. */
  push (event) {
    if (this.closed) return
    this.queue.push(event)
    if (this.queue.length > this.maxQueue) {
      const extra = this.queue.length - this.maxQueue
      this.queue.splice(0, extra)
      this.stats.dropped += extra
      const now = Date.now()
      if (now - this.lastDropLog > 10000) {
        this.lastDropLog = now
        this.logger?.error({ dropped: this.stats.dropped }, 'Fila de eventos cheia: eventos antigos descartados')
      }
    }
    this.schedule()
  }

  schedule (delay) {
    if (this.sending || !this.queue.length) return
    let wait = delay
    if (wait === undefined) {
      if (this.failures) {
        // A API está falhando: espera crescente, sem atalho mesmo com a fila cheia.
        if (this.timer) return
        wait = backoffDelay(this.failures - 1, { baseMs: this.retryBaseMs, maxMs: this.retryMaxMs })
      } else {
        wait = this.queue.length >= this.batchSize ? 0 : this.batchMs
      }
    }
    if (this.timer) {
      if (wait > 0) return
      clearTimeout(this.timer)
    }
    this.timer = setTimeout(() => {
      this.timer = null
      this.sending = this.sendBatch().finally(() => {
        this.sending = null
        if (this.queue.length && !this.timer) this.schedule()
      })
    }, wait)
    this.timer.unref?.()
  }

  /** Tira da frente da fila os eventos do lote (alguns podem já ter sido descartados). */
  removeBatch (batch) {
    const inBatch = new Set(batch)
    let n = 0
    while (n < this.queue.length && inBatch.has(this.queue[n])) n++
    this.queue.splice(0, n)
  }

  async sendBatch () {
    const batch = this.queue.slice(0, this.batchSize)
    if (!batch.length) return
    try {
      await this.request('POST', `${PREFIX}/events`, { events: batch })
      this.removeBatch(batch)
      this.stats.sent += batch.length
      this.failures = 0
    } catch (err) {
      this.stats.failedPosts += 1
      if (DROP_STATUSES.has(err.status)) {
        this.removeBatch(batch)
        this.stats.discarded += batch.length
        this.failures = 0
        this.logger?.error({ status: err.status, events: batch.length }, 'A API recusou um lote de eventos; lote descartado')
      } else {
        this.failures += 1
        this.logger?.warn({ status: err.status, attempt: this.failures, queued: this.queue.length }, 'Não foi possível enviar eventos para a API; tentando de novo')
      }
    }
  }

  /** Envia o que der da fila (usado no desligamento). */
  async drain (timeoutMs = 3000) {
    const deadline = Date.now() + timeoutMs
    if (this.timer) {
      clearTimeout(this.timer)
      this.timer = null
    }
    while (this.queue.length && Date.now() < deadline) {
      if (this.sending) await this.sending
      else {
        const before = this.queue.length
        await this.sendBatch()
        if (this.queue.length >= before) break
      }
    }
    this.closed = true
  }

  get queued () {
    return this.queue.length
  }
}
