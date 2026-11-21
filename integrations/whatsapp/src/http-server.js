// API HTTP interna do conector (só na rede do Docker). Tudo pede X-Connector-Token, menos /health.

import { createHash, timingSafeEqual } from 'node:crypto'
import http from 'node:http'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const ROUTE_RE = /^\/sessions\/([^/]+)\/(start|stop|flush|read)$/
const MAX_BODY = 64 * 1024

function digest (text) {
  return createHash('sha256').update(String(text)).digest()
}

/** Compara o token em tempo constante. Sem token configurado, nada passa. */
export function tokenMatches (expected, provided) {
  if (!expected || typeof provided !== 'string' || !provided) return false
  return timingSafeEqual(digest(expected), digest(provided))
}

function reply (res, status, body) {
  const text = JSON.stringify(body)
  const headers = { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' }
  if (status === 413) headers.connection = 'close'
  res.writeHead(status, headers)
  res.end(text)
}

function readBody (req) {
  return new Promise((resolve, reject) => {
    let size = 0
    let tooLarge = false
    const chunks = []
    req.on('data', (chunk) => {
      if (tooLarge) return // descarta o resto sem guardar
      size += chunk.length
      if (size > MAX_BODY) {
        tooLarge = true
        chunks.length = 0
        reject(Object.assign(new Error('Corpo grande demais'), { status: 413 }))
        return
      }
      chunks.push(chunk)
    })
    req.on('end', () => {
      if (tooLarge) return
      const text = Buffer.concat(chunks).toString('utf8').trim()
      if (!text) return resolve({})
      try {
        const data = JSON.parse(text)
        resolve(data && typeof data === 'object' && !Array.isArray(data) ? data : {})
      } catch {
        reject(Object.assign(new Error('JSON inválido'), { status: 400 }))
      }
    })
    req.on('error', reject)
  })
}

function validRead (body) {
  if (typeof body.remote_jid !== 'string' || !body.remote_jid.includes('@') || body.remote_jid.length > 64) return null
  if (!Array.isArray(body.external_ids) || body.external_ids.length > 100) return null
  const ids = body.external_ids.filter((id) => typeof id === 'string' && id.length > 0 && id.length <= 160)
  return { remote_jid: body.remote_jid, external_ids: ids }
}

/**
 * supervisor: { dispatch(cmd, sessionId, payload), health(), stats() }
 */
export function createHttpServer ({ token, supervisor, logger, configured = true }) {
  return http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url || '/', 'http://localhost')
      const path = url.pathname.replace(/\/+$/, '') || '/'

      if (req.method === 'GET' && path === '/health') {
        // Sem configuração continua "saudável" (o resto do sistema sobe), mas avisa que está desligado.
        if (!configured || !supervisor) return reply(res, 200, { ok: true, configured: false, workers: 0, sessions: 0, rss_mb: Math.round(process.memoryUsage().rss / 1048576) })
        const health = supervisor.health()
        return reply(res, health.ok ? 200 : 503, health)
      }

      if (!tokenMatches(token, req.headers['x-connector-token'])) {
        return reply(res, 401, { ok: false, error: 'unauthorized' })
      }

      // Token certo, mas falta HUB_API_URL ou DATABASE_URL: não há processos para receber o pedido.
      if (!configured || !supervisor) return reply(res, 503, { ok: false, error: 'not_configured' })

      if (req.method === 'GET' && path === '/stats') {
        return reply(res, 200, await supervisor.stats())
      }

      const match = req.method === 'POST' ? ROUTE_RE.exec(path) : null
      if (!match) return reply(res, 404, { ok: false, error: 'not_found' })

      const sessionId = match[1].toLowerCase()
      const action = match[2]
      if (!UUID_RE.test(sessionId)) return reply(res, 400, { ok: false, error: 'invalid_session_id' })

      const body = await readBody(req)
      let payload = {}
      if (action === 'stop') payload = { logout: body.logout === true }
      if (action === 'read') {
        payload = validRead(body)
        if (!payload) return reply(res, 400, { ok: false, error: 'invalid_request' })
      }
      supervisor.dispatch(action, sessionId, payload)
      return reply(res, 202, { ok: true })
    } catch (err) {
      if (err?.status === 400 || err?.status === 413) {
        return reply(res, err.status, { ok: false, error: err.status === 413 ? 'payload_too_large' : 'invalid_json' })
      }
      logger?.error({ err: err?.message }, 'Erro na API interna do conector')
      if (!res.headersSent) reply(res, 500, { ok: false, error: 'internal_error' })
    }
  })
}
