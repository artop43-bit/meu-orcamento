// Uma sessão do WhatsApp (um número conectado): abre o socket da Baileys, gera o QR,
// reconecta quando cai, importa o histórico do primeiro pareamento e converte tudo em eventos.

import makeWASocket, {
  Browsers,
  DEFAULT_CONNECTION_CONFIG,
  downloadMediaMessage,
  fetchLatestWaWebVersion,
  proto
} from 'baileys'
import { TtlCache } from './auth-store.js'
import {
  ERROR_TEXTS,
  MAX_MEDIA_BYTES,
  backoffDelay,
  buildMediaSendContent,
  buildQuotedMessage,
  cleanName,
  createHistoryBudget,
  disconnectAction,
  extractMediaMeta,
  isIndividualJid,
  mapContact,
  mapMessage,
  mapMessageUpdate,
  normalizeJid,
  phoneFromJid,
  selectHistory,
  shouldIgnoreJid,
  splitJids
} from './mapping.js'

// Tempo máximo que uma sessão segura a vaga de pareamento/sincronização inicial.
const GATE_HOLD_MAX_MS = 120000
const SEND_TIMEOUT_MS = 30000
const READ_TIMEOUT_MS = 15000
const LOGOUT_TIMEOUT_MS = 5000
const MEDIA_DOWNLOAD_TIMEOUT_MS = 15000
const AVATAR_TIMEOUT_MS = 8000
const AVATAR_TTL_MS = 24 * 60 * 60 * 1000
const AVATAR_SPACING_MS = 350
const MAX_AVATAR_BYTES = 2 * 1024 * 1024
const MAX_KNOWN_JIDS = 10000
const MAX_SENT_CACHE = 200
const MAX_MEDIA_QUEUE = 120
const MAX_MEDIA_CONCURRENT = 3
const MAX_AVATAR_QUEUE = 60
const NAME_RANK = { push: 1, chat: 2, contact: 2 }

// Tipos de histórico que não baixamos: o completo, o sob demanda e os status (stories).
// Os outros são necessários (inclusive para os mapeamentos LID ↔ número).
const SKIPPED_HISTORY = new Set([
  proto.HistorySync.HistorySyncType.FULL,
  proto.HistorySync.HistorySyncType.ON_DEMAND,
  proto.HistorySync.HistorySyncType.INITIAL_STATUS_V3
])

export function shouldSyncHistoryMessage ({ syncType } = {}) {
  return !SKIPPED_HISTORY.has(syncType)
}

export function withTimeout (promise, ms, message = 'Tempo esgotado') {
  let timer
  const timeout = new Promise((_resolve, reject) => {
    timer = setTimeout(() => reject(new Error(message)), ms)
  })
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer))
}

function isValidVersion (version) {
  return Array.isArray(version) && version.length === 3 && version.every((n) => Number.isInteger(n) && n >= 0)
}

/**
 * Versão do WhatsApp Web: a mais nova (fetchLatestWaWebVersion) a cada conexão; se falhar, a última
 * que funcionou (messaging_connector_kv.wa_version); só então a padrão da Baileys.
 * Chamadas simultâneas dividem a mesma busca, e o resultado vale por `cacheMs`.
 */
export function createVersionResolver ({ kv, logger, fetchLatest = fetchLatestWaWebVersion, cacheMs = 60000, timeoutMs = 8000, now = Date.now }) {
  let cached = null
  let inflight = null
  let lastSaved = null
  return {
    async resolve () {
      if (cached && now() - cached.at < cacheMs) return cached.version
      if (!inflight) {
        inflight = (async () => {
          try {
            const result = await fetchLatest({ signal: AbortSignal.timeout(timeoutMs) })
            if (result?.isLatest && isValidVersion(result.version)) {
              cached = { version: result.version, at: now() }
              return result.version
            }
          } catch (err) {
            logger?.warn({ err: err?.message }, 'Não foi possível buscar a versão do WhatsApp Web')
          }
          try {
            const saved = await kv.get('wa_version')
            const version = saved ? JSON.parse(saved) : null
            if (isValidVersion(version)) {
              lastSaved = saved
              cached = { version, at: now() }
              return version
            }
          } catch (err) {
            logger?.warn({ err: err?.message }, 'Não foi possível ler a última versão salva do WhatsApp Web')
          }
          return undefined
        })().finally(() => {
          inflight = null
        })
      }
      return inflight
    },

    async remember (version) {
      if (!isValidVersion(version)) return
      const text = JSON.stringify(version)
      if (text === lastSaved) return
      await kv.set('wa_version', text)
      lastSaved = text
    }
  }
}

function isSafeAvatarUrl (raw) {
  try {
    const parsed = new URL(raw)
    return parsed.protocol === 'https:'
  } catch {
    return false
  }
}

export class Session {
  /**
   * deps: { authStore, versions, emit(event), logger, baileysLogger, gate, onReady(session),
   *         onEnded(session), makeSocket?, uploadMedia?, downloadMedia?, uploadAvatar?,
   *         downloadBaileysMedia?, fetchAvatar? }
   */
  constructor (id, deps) {
    this.id = id
    this.deps = deps
    this.logger = deps.logger.child({ session: id })
    this.makeSocket = deps.makeSocket || makeWASocket
    this.downloadBaileysMedia = deps.downloadBaileysMedia || downloadMediaMessage
    this.fetchAvatar = deps.fetchAvatar || globalThis.fetch
    this.generation = 0
    this.wanted = false
    this.status = 'idle' // idle | connecting | qr | ready | stopped
    this.sock = null
    this.auth = null
    this.attempt = 0
    this.reconnectTimer = null
    this.releaseGate = null
    this.gateTimer = null
    this.keyCache = new TtlCache({ max: 2000 })
    this.historyBudget = createHistoryBudget()
    this.knownJids = new Set()
    this.altJids = new Map()
    this.pendingContacts = new Map()
    this.contactNames = new Map()
    this.contactRank = new Map()
    this.avatarChecked = new Map()
    this.avatarQueued = new Set()
    this.avatarQueue = []
    this.avatarRunning = false
    this.mediaQueue = []
    this.mediaActive = 0
    this.sentCache = new Map()
    this.chain = Promise.resolve()
    this.displayName = null
    this.versionUsed = undefined
    this.timings = { startedAt: null, firstQrAt: null, openAt: null }
  }

  get running () {
    return this.wanted && this.status !== 'idle' && this.status !== 'stopped'
  }

  get ready () {
    return this.status === 'ready' && Boolean(this.sock)
  }

  /** Executa os comandos da sessão um de cada vez (start/stop/logout não se atropelam). */
  run (fn) {
    const result = this.chain.then(fn)
    this.chain = result.catch((err) => {
      this.logger.error({ err: err?.message }, 'Erro num comando da sessão')
    })
    return result
  }

  emit (event) {
    this.deps.emit(event)
  }

  emitStatus (fields) {
    this.emit({ type: 'status', session_id: this.id, ...fields })
  }

  /** Inicia (ou reinicia: um QR novo, se ainda não pareado). Com ifIdle, não mexe se já estiver rodando. */
  start ({ ifIdle = false } = {}) {
    return this.run(async () => {
      if (ifIdle && this.running) return
      this.wanted = true
      await this.teardown()
      this.attempt = 0
      this.status = 'connecting'
      this.timings = { startedAt: Date.now(), firstQrAt: null, openAt: null }
      void this.connect(this.generation)
    })
  }

  /** Para a sessão. Com logout, desconecta o aparelho no WhatsApp e apaga as credenciais. */
  stop ({ logout = false } = {}) {
    return this.run(async () => {
      this.wanted = false
      const sock = this.sock
      if (logout && sock && this.status === 'ready') {
        try {
          await withTimeout(sock.logout(), LOGOUT_TIMEOUT_MS)
        } catch (err) {
          this.logger.warn({ err: err?.message }, 'Logout no WhatsApp falhou; apagando as credenciais mesmo assim')
        }
      }
      await this.teardown()
      if (logout) {
        await this.deps.authStore.removeAll(this.id)
        this.keyCache.flushAll()
      }
      this.status = 'stopped'
      this.deps.onEnded?.(this)
    })
  }

  /** Fecha o socket sem logout (desligamento do processo). */
  close () {
    return this.run(async () => {
      this.wanted = false
      await this.teardown()
      this.status = 'stopped'
    })
  }

  async teardown () {
    this.generation += 1
    clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    this.mediaQueue = []
    this.avatarQueue = []
    this.avatarQueued.clear()
    this.freeGate()
    const sock = this.sock
    const auth = this.auth
    this.sock = null
    this.auth = null
    if (sock) {
      try {
        await sock.end(undefined)
      } catch {
        // o socket já estava fechado
      }
    }
    auth?.release()
    this.status = 'idle'
  }

  holdGate (release) {
    this.freeGate()
    this.releaseGate = release
    this.gateTimer = setTimeout(() => this.freeGate(), GATE_HOLD_MAX_MS)
    this.gateTimer.unref?.()
  }

  freeGate () {
    clearTimeout(this.gateTimer)
    this.gateTimer = null
    const release = this.releaseGate
    this.releaseGate = null
    release?.()
  }

  async connect (gen) {
    try {
      const release = await this.deps.gate.acquire()
      if (gen !== this.generation || !this.wanted) {
        release()
        return
      }
      this.holdGate(release)
      if (!this.auth) {
        const auth = await this.deps.authStore.load(this.id, { cache: this.keyCache })
        if (gen !== this.generation) {
          auth.release()
          return
        }
        this.auth = auth
      }
      const auth = this.auth
      const version = await this.deps.versions.resolve()
      if (gen !== this.generation) return
      this.emitStatus({ status: 'connecting' })
      this.versionUsed = version || DEFAULT_CONNECTION_CONFIG.version
      const sock = this.makeSocket({
        ...(version ? { version } : {}),
        auth: auth.state,
        logger: this.deps.baileysLogger,
        browser: Browsers.macOS('Chrome'),
        syncFullHistory: false,
        markOnlineOnConnect: false,
        emitOwnEvents: false,
        countryCode: 'BR',
        generateHighQualityLinkPreview: false,
        shouldIgnoreJid,
        shouldSyncHistoryMessage,
        getMessage: async (key) => this.sentCache.get(key?.id)
      })
      this.sock = sock
      this.bind(sock, auth, gen)
    } catch (err) {
      this.logger.error({ err: err?.message }, 'Falha ao abrir a conexão com o WhatsApp')
      if (gen === this.generation) {
        this.freeGate()
        this.scheduleReconnect(gen)
      }
    }
  }

  bind (sock, auth, gen) {
    const live = () => gen === this.generation && this.sock === sock
    sock.ev.on('creds.update', (update) => {
      if (gen !== this.generation) return
      auth.saveCreds().catch((err) => this.onDbError(err))
      const name = cleanName(update?.me?.name)
      if (name && this.status === 'ready' && name !== this.displayName) {
        this.displayName = name
        this.emitStatus({ status: 'ready', display_name: name })
      }
    })
    // Correção da queda a cada ~50 min: o WhatsApp espera confirmação dos avisos "status".
    sock.ws.on('CB:status', (node) => {
      if (!live() || !node?.attrs?.id) return
      sock.sendNode({
        tag: 'ack',
        attrs: {
          id: node.attrs.id,
          to: node.attrs.from,
          class: 'status',
          ...(node.attrs.type && { type: node.attrs.type }),
          ...(node.attrs.participant && { participant: node.attrs.participant })
        }
      }).catch(() => {})
    })
    sock.ev.on('connection.update', (update) => {
      if (gen !== this.generation) return
      this.onConnectionUpdate(update, sock, auth, gen)
    })
    sock.ev.on('messages.upsert', (data) => {
      if (live()) this.onMessages(data?.messages || [])
    })
    sock.ev.on('messages.update', (updates) => {
      if (live()) this.onMessageUpdates(updates || [])
    })
    sock.ev.on('messaging-history.set', (data) => {
      if (live()) this.onHistory(data || {})
    })
    sock.ev.on('contacts.upsert', (contacts) => {
      if (live()) this.onContacts(contacts || [])
    })
    sock.ev.on('contacts.update', (contacts) => {
      if (live()) this.onContacts(contacts || [])
    })
    sock.ev.on('chats.upsert', (chats) => {
      if (live()) this.onChats(chats || [])
    })
    sock.ev.on('chats.update', (chats) => {
      if (live()) this.onChats(chats || [])
    })
    sock.ev.on('lid-mapping.update', (mapping) => {
      if (live()) this.onLidMapping(mapping)
    })
  }

  onConnectionUpdate (update, sock, auth, gen) {
    const { connection, lastDisconnect, qr, receivedPendingNotifications } = update
    if (qr) {
      this.status = 'qr'
      if (!this.timings.firstQrAt) this.timings.firstQrAt = Date.now()
      this.emitStatus({ status: 'qr', qr })
      // Esperar a leitura do QR não ocupa vaga de pareamento.
      this.freeGate()
    }
    if (connection === 'open') {
      this.attempt = 0
      this.status = 'ready'
      this.timings.openAt = Date.now()
      const me = auth.state.creds.me || sock.user || {}
      const event = { status: 'ready' }
      const phone = phoneFromJid(me.id)
      if (phone) event.phone = phone
      const name = cleanName(me.name) || cleanName(me.verifiedName)
      if (name) {
        event.display_name = name
        this.displayName = name
      }
      const waJid = normalizeJid(me.id)
      if (waJid) event.wa_jid = waJid
      this.emitStatus(event)
      this.deps.versions.remember(this.versionUsed).catch((err) => {
        this.logger.warn({ err: err?.message }, 'Não foi possível salvar a versão do WhatsApp Web')
      })
      this.deps.onReady?.(this)
    }
    if (receivedPendingNotifications === true) this.freeGate()
    if (connection === 'close') {
      this.freeGate()
      if (this.sock === sock) this.sock = null
      const error = lastDisconnect?.error
      const code = error?.output?.statusCode ?? error?.statusCode
      const registered = Boolean(auth.state.creds.me?.id)
      const decision = disconnectAction(code, { registered })
      this.logger.warn({ code, action: decision.action }, 'Conexão com o WhatsApp fechada')
      this.handleDisconnect(decision, gen)
    }
  }

  handleDisconnect (decision, gen) {
    switch (decision.action) {
      case 'restart':
        this.status = 'connecting'
        this.scheduleReconnect(gen, 0)
        break
      case 'wipe':
      case 'expired':
        void this.run(async () => {
          if (gen !== this.generation) return
          this.wanted = false
          await this.teardown()
          await this.deps.authStore.removeAll(this.id)
          this.keyCache.flushAll()
          this.status = 'stopped'
          this.emitStatus({ status: decision.status, wanted: false, error: decision.error })
          this.deps.onEnded?.(this)
        })
        break
      case 'stop':
        void this.run(async () => {
          if (gen !== this.generation) return
          this.wanted = false
          await this.teardown()
          this.status = 'stopped'
          this.emitStatus({ status: decision.status, error: decision.error })
          this.deps.onEnded?.(this)
        })
        break
      default:
        this.status = 'connecting'
        this.scheduleReconnect(gen)
    }
  }

  scheduleReconnect (gen, delay) {
    if (gen !== this.generation || !this.wanted) return
    const wait = delay ?? backoffDelay(this.attempt++, { jitter: 0.2 })
    clearTimeout(this.reconnectTimer)
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      if (gen === this.generation && this.wanted) void this.connect(gen)
    }, wait)
    this.reconnectTimer.unref?.()
  }

  onDbError (err) {
    // 23503 = a sessão foi apagada na API (chave estrangeira); não adianta continuar.
    if (err?.code === '23503') {
      this.logger.warn('A sessão não existe mais no banco; parando')
      void this.stop({ logout: false })
      return
    }
    this.logger.error({ err: err?.message }, 'Não foi possível salvar as credenciais no banco')
  }

  linkJids (...jids) {
    const { pn, lid } = splitJids(...jids)
    if (pn && lid) {
      this.altJids.set(pn, lid)
      this.altJids.set(lid, pn)
      if (this.altJids.size > MAX_KNOWN_JIDS) {
        this.altJids.delete(this.altJids.keys().next().value)
      }
    }
  }

  remember (...jids) {
    const added = []
    for (const jid of jids) {
      if (!jid || this.knownJids.has(jid)) continue
      this.knownJids.add(jid)
      added.push(jid)
      if (this.knownJids.size > MAX_KNOWN_JIDS) {
        this.knownJids.delete(this.knownJids.values().next().value)
      }
    }
    for (const jid of added) {
      const pending = this.pendingContacts.get(jid)
      if (pending) {
        this.pendingContacts.delete(jid)
        this.emitContact(pending)
      }
      this.queueAvatar(jid)
    }
  }

  onMessages (messages) {
    for (const msg of messages) {
      const event = mapMessage(this.id, msg)
      if (!event) continue
      if (!event.remote_jid_alt && this.altJids.has(event.remote_jid)) {
        event.remote_jid_alt = this.altJids.get(event.remote_jid)
      }
      this.linkJids(event.remote_jid, event.remote_jid_alt)
      this.remember(event.remote_jid, event.remote_jid_alt)
      if (event.push_name && !this.contactRank.has(event.remote_jid)) {
        this.contactNames.set(event.remote_jid, event.push_name)
        this.contactRank.set(event.remote_jid, NAME_RANK.push)
      }
      this.emit(event)
      const meta = extractMediaMeta(msg.message)
      if (meta) this.queueMediaDownload(event.external_id, msg, meta)
    }
  }

  onMessageUpdates (updates) {
    for (const item of updates) {
      const event = mapMessageUpdate(this.id, item)
      if (event) this.emit(event)
    }
  }

  onHistory (data) {
    const { messages, jids, chatContacts, mediaItems } = selectHistory(this.id, data, this.historyBudget)
    for (const ev of chatContacts) this.linkJids(ev.jid, ev.jid_alt)
    for (const ev of messages) {
      if (!ev.remote_jid_alt && this.altJids.has(ev.remote_jid)) {
        ev.remote_jid_alt = this.altJids.get(ev.remote_jid)
      }
      this.linkJids(ev.remote_jid, ev.remote_jid_alt)
    }
    this.remember(...jids)
    for (const event of messages) this.emit(event)
    for (const contactEv of chatContacts) this.emitContact(contactEv)
    // Nomes dos contatos das conversas importadas (ou já vistas); os outros ficam em cache caso entrem depois.
    this.onContacts(data.contacts || [])
    // Baixa mídias recentes em segundo plano (já ordenadas da mais nova para a mais antiga).
    for (const item of mediaItems.slice(0, 80)) {
      this.queueMediaDownload(item.externalId, item.rawMsg, item.meta)
    }
  }

  onChats (chats) {
    for (const chat of chats) {
      if (!chat || typeof chat !== 'object') continue
      const { pn, lid } = splitJids(chat.id, chat.pnJid, chat.lidJid, chat.accountLid)
      this.linkJids(pn, lid)
      const primary = pn || lid
      const secondary = pn && lid ? lid : null
      const name = cleanName(chat.name) || cleanName(chat.displayName)
      if (!primary || (!name && !secondary)) continue
      const ev = {
        type: 'contact',
        session_id: this.id,
        jid: primary,
        name: name || null,
        source: name ? 'chat' : 'push'
      }
      if (secondary) ev.jid_alt = secondary
      this.emitContact(ev)
    }
  }

  onLidMapping (mapping) {
    if (!mapping || typeof mapping !== 'object') return
    const items = Array.isArray(mapping) ? mapping : [mapping]
    for (const entry of items) {
      const { pn, lid } = splitJids(entry?.pn, entry?.pnJid, entry?.phoneNumber, entry?.lid, entry?.lidJid)
      if (!pn || !lid) continue
      this.linkJids(pn, lid)
      this.emitContact({ type: 'contact', session_id: this.id, jid: pn, jid_alt: lid, name: null, source: 'push' })
    }
  }

  onContacts (contacts) {
    for (const contact of contacts) {
      const event = mapContact(this.id, contact)
      if (event) this.emitContact(event)
    }
  }

  cachePendingContact (event) {
    const keys = [event.jid, event.jid_alt].filter(Boolean)
    for (const key of keys) {
      const prev = this.pendingContacts.get(key)
      const prevRank = prev?.name ? (NAME_RANK[prev.source] || 0) : 0
      const nextRank = event.name ? (NAME_RANK[event.source] || 0) : 0
      if (!prev || nextRank >= prevRank) {
        this.pendingContacts.set(key, event)
      }
      if (this.pendingContacts.size > MAX_KNOWN_JIDS) {
        this.pendingContacts.delete(this.pendingContacts.keys().next().value)
      }
    }
  }

  emitContact (event) {
    this.linkJids(event.jid, event.jid_alt)
    if (!event.jid_alt && this.altJids.has(event.jid)) {
      event = { ...event, jid_alt: this.altJids.get(event.jid) }
    }
    // Só conversas que já apareceram aqui; as demais ficam guardadas caso a mensagem chegue depois.
    const known = this.knownJids.has(event.jid) || (event.jid_alt && this.knownJids.has(event.jid_alt))
    if (!known) {
      this.cachePendingContact(event)
      return
    }
    const key = event.jid
    const nextRank = event.name ? (NAME_RANK[event.source] || 1) : 0
    const prevRank = this.contactRank.get(key) || 0
    const hasLink = Boolean(event.jid_alt)
    if (!event.name) {
      // Sem nome: só envia quando serve para vincular LID ↔ número.
      if (!hasLink) return
      const linkKey = `link:${key}:${event.jid_alt}`
      if (this.contactNames.get(linkKey)) return
      this.contactNames.set(linkKey, true)
      this.emit(event)
      return
    }
    if (this.contactNames.get(key) === event.name && prevRank >= nextRank) return
    if (prevRank > nextRank) return
    this.contactNames.set(key, event.name)
    this.contactRank.set(key, nextRank)
    if (event.jid_alt) {
      this.contactNames.set(event.jid_alt, event.name)
      this.contactRank.set(event.jid_alt, nextRank)
    }
    if (this.contactNames.size > MAX_KNOWN_JIDS) {
      this.contactNames.delete(this.contactNames.keys().next().value)
    }
    this.emit(event)
  }

  queueMediaDownload (externalId, rawMsg, meta) {
    if (!this.deps.uploadMedia || !externalId || !rawMsg || !meta) return
    if (meta.fileLength && meta.fileLength > MAX_MEDIA_BYTES) return
    if (this.mediaQueue.length >= MAX_MEDIA_QUEUE) return
    this.mediaQueue.push({ externalId, rawMsg, meta, gen: this.generation })
    this.drainMediaQueue()
  }

  drainMediaQueue () {
    while (this.mediaActive < MAX_MEDIA_CONCURRENT && this.mediaQueue.length) {
      const task = this.mediaQueue.shift()
      if (!task || task.gen !== this.generation) continue
      this.mediaActive += 1
      void this.downloadAndAttachMedia(task).finally(() => {
        this.mediaActive -= 1
        this.drainMediaQueue()
      })
    }
  }

  async downloadAndAttachMedia ({ externalId, rawMsg, meta, gen }) {
    const sock = this.sock
    if (gen !== this.generation || !sock || !this.deps.uploadMedia) return
    try {
      let buffer = null
      for (let attempt = 1; attempt <= 2; attempt += 1) {
        try {
          buffer = await withTimeout(
            this.downloadBaileysMedia(
              rawMsg,
              'buffer',
              {},
              { logger: this.deps.baileysLogger, reuploadRequest: sock.updateMediaMessage }
            ),
            MEDIA_DOWNLOAD_TIMEOUT_MS,
            'Tempo esgotado ao baixar mídia do WhatsApp'
          )
          if (Buffer.isBuffer(buffer) && buffer.length > 0) break
        } catch (err) {
          if (attempt >= 2) throw err
          await new Promise((resolve) => setTimeout(resolve, 600))
        }
      }
      if (gen !== this.generation || !Buffer.isBuffer(buffer) || !buffer.length || buffer.length > MAX_MEDIA_BYTES) return
      const uploaded = await this.deps.uploadMedia(this.id, {
        buffer,
        kind: meta.kind,
        mimeType: meta.mimeType,
        fileName: meta.fileName
      })
      if (gen !== this.generation || !uploaded?.media_id) return
      this.emit({
        type: 'media_attach',
        session_id: this.id,
        external_id: externalId,
        media_id: uploaded.media_id
      })
    } catch (err) {
      this.logger.debug({ err: err?.message, externalId }, 'Mídia não pôde ser baixada (mantido texto de prévia)')
    }
  }

  queueAvatar (jid) {
    if (!this.deps.uploadAvatar || !jid || !isIndividualJid(jid)) return
    const now = Date.now()
    const checked = this.avatarChecked.get(jid)
    if (checked && now - checked < AVATAR_TTL_MS) return
    if (this.avatarQueued.has(jid) || this.avatarQueue.length >= MAX_AVATAR_QUEUE) return
    this.avatarQueued.add(jid)
    this.avatarQueue.push({ jid, gen: this.generation })
    if (!this.avatarRunning) void this.drainAvatarQueue()
  }

  async drainAvatarQueue () {
    this.avatarRunning = true
    try {
      while (this.avatarQueue.length) {
        const task = this.avatarQueue.shift()
        if (!task) continue
        this.avatarQueued.delete(task.jid)
        if (task.gen !== this.generation || this.status !== 'ready' || !this.sock) continue
        await this.fetchAndUploadAvatar(task.jid, task.gen)
        if (this.avatarQueue.length) {
          await new Promise((resolve) => setTimeout(resolve, AVATAR_SPACING_MS))
        }
      }
    } finally {
      this.avatarRunning = false
    }
  }

  async fetchAndUploadAvatar (jid, gen) {
    const sock = this.sock
    if (gen !== this.generation || !sock || typeof sock.profilePictureUrl !== 'function') return
    this.avatarChecked.set(jid, Date.now())
    if (this.avatarChecked.size > 500) {
      this.avatarChecked.delete(this.avatarChecked.keys().next().value)
    }
    try {
      const url = await withTimeout(sock.profilePictureUrl(jid, 'image'), AVATAR_TIMEOUT_MS)
      if (!url || !isSafeAvatarUrl(url) || gen !== this.generation) return
      const res = await this.fetchAvatar(url, { signal: AbortSignal.timeout(AVATAR_TIMEOUT_MS) })
      if (!res?.ok || gen !== this.generation) return
      const buffer = Buffer.from(await res.arrayBuffer())
      if (!buffer.length || buffer.length > MAX_AVATAR_BYTES) return
      const mimeType = (res.headers?.get?.('content-type') || 'image/jpeg').split(';')[0].trim()
      await this.deps.uploadAvatar(this.id, {
        jid,
        jidAlt: this.altJids.get(jid) || null,
        buffer,
        mimeType
      })
    } catch {
      // Muitos contatos ocultam a foto de perfil; mantém as iniciais sem ruído no log.
    }
  }

  cacheSent (id, message) {
    this.sentCache.set(id, message)
    while (this.sentCache.size > MAX_SENT_CACHE) {
      this.sentCache.delete(this.sentCache.keys().next().value)
    }
  }

  /** Envia um item da fila (texto ou mídia). Devolve { skipped } se a sessão não estiver pronta. */
  async send (item) {
    const sock = this.sock
    if (this.status !== 'ready' || !sock) return { skipped: true }
    const jid = normalizeJid(item.remote_jid)
    if (!jid || !isIndividualJid(jid)) throw new Error('Destino inválido')
    const quoted = buildQuotedMessage(item.quoted, jid)
    let payload
    if (item.media?.media_id) {
      if (!this.deps.downloadMedia) throw new Error('Envio de mídia indisponível')
      const buffer = await this.deps.downloadMedia(this.id, item.media.media_id)
      payload = buildMediaSendContent(item, buffer)
    } else {
      payload = { text: String(item.body ?? ''), linkPreview: null }
    }
    const sent = await withTimeout(
      sock.sendMessage(jid, payload, quoted ? { quoted } : {}),
      SEND_TIMEOUT_MS,
      'O WhatsApp demorou demais para aceitar a mensagem'
    )
    const externalId = sent?.key?.id || null
    if (externalId && sent.message) this.cacheSent(externalId, sent.message)
    this.remember(jid)
    return { externalId }
  }

  /** Confirmação de leitura das mensagens recebidas. */
  async read (remoteJid, externalIds) {
    const sock = this.sock
    if (this.status !== 'ready' || !sock) return false
    const jid = normalizeJid(remoteJid)
    if (!jid || !isIndividualJid(jid)) return false
    const keys = (externalIds || [])
      .filter((id) => typeof id === 'string' && id)
      .slice(0, 100)
      .map((id) => ({ remoteJid: jid, id, fromMe: false }))
    if (!keys.length) return false
    await withTimeout(sock.readMessages(keys), READ_TIMEOUT_MS)
    return true
  }

  info () {
    return {
      id: this.id,
      status: this.status,
      attempt: this.attempt,
      first_qr_ms: this.timings.firstQrAt && this.timings.startedAt ? this.timings.firstQrAt - this.timings.startedAt : null
    }
  }
}

export { ERROR_TEXTS }
