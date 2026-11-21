// Funções puras (sem rede, sem banco): convertem o que a Baileys entrega para os eventos do
// contrato com a API e decidem o que fazer em cada desconexão. Todas têm teste em test/.

export const PN_SUFFIX = '@s.whatsapp.net'
export const LID_SUFFIX = '@lid'
export const MAX_MEDIA_BYTES = 8 * 1024 * 1024

// Textos de prévia/reserva quando a mídia não pôde ser baixada (ex.: expirada ou acima de 8 MB).
export const MEDIA_LABELS = Object.freeze({
  image: '📷 Foto',
  audio: '🎤 Áudio',
  video: '🎬 Vídeo',
  document: '📄 Documento',
  sticker: 'Figurinha',
  other: 'Mensagem não suportada'
})

export const ERROR_TEXTS = Object.freeze({
  loggedOut: 'O WhatsApp foi desconectado pelo celular.',
  replaced: 'Este número foi conectado em outro lugar.',
  qrExpired: 'O QR Code expirou. Gere um novo.',
  sendFailed: 'Não foi possível enviar a mensagem pelo WhatsApp.',
  notDelivered: 'O WhatsApp não entregou a mensagem.'
})

const MAX_NAME = 120
// Nomes mascarados que o WhatsApp manda quando esconde o número (ex.: "+55·······80") ou pontuação solta.
const MASKED_PHONE_RE = /^\+?\d{0,4}[\s-]?[·•*∙.]{3,}\d{0,4}$/
const ONLY_PUNCT_RE = /^[\p{P}\p{S}\s]+$/u

/** Tira o número do aparelho (":12") e troca o antigo "@c.us" por "@s.whatsapp.net". */
export function normalizeJid (jid) {
  if (typeof jid !== 'string' || !jid.includes('@')) return null
  const at = jid.indexOf('@')
  let user = jid.slice(0, at)
  let server = jid.slice(at + 1)
  if (server === 'c.us') server = 's.whatsapp.net'
  const colon = user.indexOf(':')
  if (colon >= 0) user = user.slice(0, colon)
  if (!user || !server) return null
  return `${user}@${server}`
}

/** Conversa individual (número ou LID). Grupos, listas, status e canais ficam de fora. */
export function isIndividualJid (jid) {
  return typeof jid === 'string' && (jid.endsWith(PN_SUFFIX) || jid.endsWith(LID_SUFFIX))
}

/** O mesmo filtro que a Baileys recebe em `shouldIgnoreJid`. */
export function shouldIgnoreJid (jid) {
  if (typeof jid !== 'string' || !jid) return false
  return jid.endsWith('@g.us') || jid.endsWith('@broadcast') || jid.endsWith('@newsletter')
}

/** Separa, entre os JIDs dados, o do número (pn) e o LID. */
export function splitJids (...jids) {
  const result = { pn: null, lid: null }
  for (const raw of jids) {
    const jid = normalizeJid(raw)
    if (!jid) continue
    if (jid.endsWith(PN_SUFFIX) && !result.pn) result.pn = jid
    else if (jid.endsWith(LID_SUFFIX) && !result.lid) result.lid = jid
  }
  return result
}

/** Só os dígitos do número de um JID "5511...@s.whatsapp.net" (ou null). */
export function phoneFromJid (jid) {
  const normalized = normalizeJid(jid)
  if (!normalized || !normalized.endsWith(PN_SUFFIX)) return null
  const digits = normalized.slice(0, -PN_SUFFIX.length)
  return /^\d{6,20}$/.test(digits) ? digits : null
}

// Embrulhos que só carregam a mensagem de verdade por dentro.
const WRAPPERS = [
  'ephemeralMessage',
  'viewOnceMessage',
  'viewOnceMessageV2',
  'viewOnceMessageV2Extension',
  'documentWithCaptionMessage',
  'editedMessage',
  'associatedChildMessage',
  'deviceSentMessage'
]

// Campos que acompanham a mensagem mas não são o conteúdo.
const META_KEYS = new Set(['messageContextInfo', 'senderKeyDistributionMessage'])

// Mensagens que não viram balão na conversa (reações, avisos internos, votos...).
const IGNORED_TYPES = new Set([
  'protocolMessage',
  'reactionMessage',
  'encReactionMessage',
  'pollUpdateMessage',
  'keepInChatMessage',
  'pinInChatMessage',
  'encEventResponseMessage',
  'secretEncryptedMessage',
  'call',
  'botInvokeMessage'
])

export function unwrapMessage (message) {
  let content = message
  for (let i = 0; i < 6 && content && typeof content === 'object'; i++) {
    const wrapper = WRAPPERS.find((key) => content[key]?.message)
    if (!wrapper) break
    content = content[wrapper].message
  }
  return content && typeof content === 'object' ? content : null
}

function contentKey (content) {
  for (const key of Object.keys(content)) {
    if (META_KEYS.has(key)) continue
    const value = content[key]
    if (value === null || value === undefined) continue
    if (key === 'conversation' || key.endsWith('Message') || key === 'call') return key
  }
  return null
}

function withCaption (label, caption) {
  const text = typeof caption === 'string' ? caption.trim() : ''
  return text ? `${label} · ${text}` : label
}

/**
 * Lê o conteúdo de uma mensagem da Baileys.
 * Devolve { body, messageType, quotedId } ou null quando a mensagem deve ser ignorada.
 */
export function extractContent (message) {
  const content = unwrapMessage(message)
  if (!content) return null
  const key = contentKey(content)
  if (!key || IGNORED_TYPES.has(key)) return null
  const inner = content[key]
  const quotedId = (inner && typeof inner === 'object' && inner.contextInfo?.stanzaId) || null
  let body
  let messageType
  switch (key) {
    case 'conversation':
      body = typeof inner === 'string' ? inner : ''
      messageType = 'chat'
      break
    case 'extendedTextMessage':
      body = typeof inner.text === 'string' ? inner.text : ''
      messageType = 'chat'
      break
    case 'imageMessage':
      body = withCaption(MEDIA_LABELS.image, inner.caption)
      messageType = 'image'
      break
    case 'audioMessage':
      body = MEDIA_LABELS.audio
      messageType = 'audio'
      break
    case 'videoMessage':
    case 'ptvMessage':
      body = withCaption(MEDIA_LABELS.video, inner.caption)
      messageType = 'video'
      break
    case 'documentMessage': {
      const name = typeof inner.fileName === 'string' && inner.fileName.trim()
        ? inner.fileName.trim()
        : (typeof inner.title === 'string' ? inner.title.trim() : '')
      body = withCaption(MEDIA_LABELS.document, name)
      messageType = 'document'
      break
    }
    case 'stickerMessage':
      body = MEDIA_LABELS.sticker
      messageType = 'sticker'
      break
    default:
      body = MEDIA_LABELS.other
      messageType = 'other'
  }
  if (messageType === 'chat' && !body.trim()) {
    body = MEDIA_LABELS.other
    messageType = 'other'
  }
  return { body, messageType, quotedId }
}

function numericLength (value) {
  if (typeof value === 'number') return value
  if (typeof value === 'bigint') return Number(value)
  if (typeof value === 'string' && /^\d+$/.test(value)) return Number(value)
  if (value && typeof value === 'object') {
    if (typeof value.toNumber === 'function') return value.toNumber()
    if (typeof value.low === 'number') return (value.low >>> 0) + (value.high >>> 0) * 2 ** 32
  }
  return null
}

/** Metadados da mídia baixável de uma mensagem da Baileys (ou null quando é só texto). */
export function extractMediaMeta (message) {
  const content = unwrapMessage(message)
  if (!content) return null
  const key = contentKey(content)
  if (!key || IGNORED_TYPES.has(key)) return null
  const inner = content[key]
  if (!inner || typeof inner !== 'object') return null
  const fileLength = numericLength(inner.fileLength)
  switch (key) {
    case 'imageMessage':
      return { kind: 'image', mimeType: inner.mimetype || 'image/jpeg', fileName: null, fileLength, ptt: false }
    case 'audioMessage':
      return { kind: 'audio', mimeType: inner.mimetype || 'audio/ogg', fileName: null, fileLength, ptt: Boolean(inner.ptt) }
    case 'videoMessage':
    case 'ptvMessage':
      return { kind: 'video', mimeType: inner.mimetype || 'video/mp4', fileName: null, fileLength, ptt: false }
    case 'documentMessage':
      return {
        kind: 'document',
        mimeType: inner.mimetype || 'application/octet-stream',
        fileName: (typeof inner.fileName === 'string' && inner.fileName.trim()) || (typeof inner.title === 'string' && inner.title.trim()) || null,
        fileLength,
        ptt: false
      }
    case 'stickerMessage':
      return { kind: 'sticker', mimeType: inner.mimetype || 'image/webp', fileName: null, fileLength, ptt: false }
    default:
      return null
  }
}

/** Monta o conteúdo de mídia para `sock.sendMessage` a partir de um item da fila. */
export function buildMediaSendContent (item, buffer) {
  const media = item?.media || {}
  const kind = media.kind || item?.message_type || 'document'
  const mimetype = media.mime_type || 'application/octet-stream'
  const caption = typeof item?.caption === 'string' ? item.caption.trim() : ''
  switch (kind) {
    case 'image':
      return { image: buffer, mimetype, ...(caption ? { caption } : {}) }
    case 'audio':
      return {
        audio: buffer,
        mimetype,
        ptt: /ogg|opus|webm/i.test(mimetype)
      }
    case 'video':
      return { video: buffer, mimetype, ...(caption ? { caption } : {}) }
    case 'sticker':
      return { sticker: buffer }
    default:
      return {
        document: buffer,
        mimetype,
        fileName: media.file_name || 'arquivo',
        ...(caption ? { caption } : {})
      }
  }
}

/** Converte o horário da Baileys (segundos, número, texto ou Long do protobuf) para ISO. */
export function toIsoTimestamp (value, now = Date.now()) {
  let seconds = null
  if (typeof value === 'number') seconds = value
  else if (typeof value === 'bigint') seconds = Number(value)
  else if (typeof value === 'string' && /^\d+$/.test(value)) seconds = Number(value)
  else if (value && typeof value === 'object') {
    if (typeof value.toNumber === 'function') seconds = value.toNumber()
    else if (typeof value.low === 'number') seconds = (value.low >>> 0) + (value.high >>> 0) * 2 ** 32
  }
  if (!Number.isFinite(seconds) || seconds <= 0) return new Date(now).toISOString()
  return new Date(seconds * 1000).toISOString()
}

export function cleanName (name) {
  if (typeof name !== 'string') return null
  const text = name.trim()
  if (!text || text === '~') return null
  if (MASKED_PHONE_RE.test(text) || ONLY_PUNCT_RE.test(text)) return null
  return text.slice(0, MAX_NAME)
}

/** Mensagem da Baileys → evento `message` do contrato (ou null se for para ignorar). */
export function mapMessage (sessionId, msg, { history = false } = {}) {
  const key = msg?.key
  if (!key?.id || !key.remoteJid) return null
  const remoteJid = normalizeJid(key.remoteJid)
  if (!isIndividualJid(remoteJid)) return null
  const content = extractContent(msg.message)
  if (!content) return null
  const event = {
    type: 'message',
    session_id: sessionId,
    external_id: key.id,
    remote_jid: remoteJid,
    from_me: Boolean(key.fromMe),
    body: content.body,
    message_type: content.messageType,
    timestamp: toIsoTimestamp(msg.messageTimestamp)
  }
  const alt = normalizeJid(key.remoteJidAlt)
  if (alt && alt !== remoteJid && isIndividualJid(alt)) event.remote_jid_alt = alt
  const pushName = key.fromMe ? null : cleanName(msg.pushName)
  if (pushName) event.push_name = pushName
  if (content.quotedId) event.quoted_external_id = content.quotedId
  if (key.fromMe && Number.isInteger(msg.status)) {
    const st = statusName(msg.status)
    if (st) event.status = st
  }
  if (history) event.history = true
  return event
}

// WAMessageStatus: ERROR=0 PENDING=1 SERVER_ACK=2 DELIVERY_ACK=3 READ=4 PLAYED=5
const STATUS_NAMES = ['failed', null, 'sent', 'delivered', 'read', 'played']

export function statusName (status) {
  return Number.isInteger(status) ? (STATUS_NAMES[status] ?? null) : null
}

/** Item de `messages.update` → evento `receipt` (mensagem nossa) ou `read_self` (lida no celular). */
export function mapMessageUpdate (sessionId, { key, update } = {}) {
  const status = update?.status
  if (!key?.id || !Number.isInteger(status)) return null
  const remoteJid = normalizeJid(key.remoteJid)
  if (!isIndividualJid(remoteJid)) return null
  if (key.fromMe) {
    const name = statusName(status)
    if (!name) return null
    const event = { type: 'receipt', session_id: sessionId, external_id: key.id, status: name }
    if (name === 'failed') event.error = ERROR_TEXTS.notDelivered
    return event
  }
  if (status >= 4) {
    const event = { type: 'read_self', session_id: sessionId, remote_jid: remoteJid }
    const alt = normalizeJid(key.remoteJidAlt)
    if (alt && alt !== remoteJid && isIndividualJid(alt)) event.remote_jid_alt = alt
    return event
  }
  return null
}

/** Contato da Baileys → evento `contact` (com origem: agenda vs apelido; aceita vínculo LID↔PN sem nome). */
export function mapContact (sessionId, contact) {
  if (!contact || typeof contact !== 'object') return null
  const bookName = cleanName(contact.name)
  const pushName = cleanName(contact.notify) || cleanName(contact.verifiedName)
  const name = bookName || pushName
  const ids = [contact.id, contact.phoneNumber, contact.lid, contact.pnJid, contact.lidJid]
    .map(normalizeJid)
    .filter((jid) => isIndividualJid(jid))
  const unique = [...new Set(ids)]
  if (!unique.length) return null
  if (!name && unique.length < 2) return null
  const event = {
    type: 'contact',
    session_id: sessionId,
    jid: unique[0],
    name: name || null,
    source: bookName ? 'contact' : 'push'
  }
  if (unique[1]) event.jid_alt = unique[1]
  return event
}

/** Mensagem citada mínima para `sock.sendMessage(..., { quoted })`. */
export function buildQuotedMessage (quoted, remoteJid) {
  if (!quoted || typeof quoted !== 'object' || !quoted.external_id) return null
  return {
    key: { remoteJid, fromMe: Boolean(quoted.from_me), id: String(quoted.external_id) },
    message: { conversation: typeof quoted.body === 'string' ? quoted.body : '' }
  }
}

/**
 * O que fazer quando a conexão cai, conforme o código da Baileys (DisconnectReason).
 * - restart: reconecta na hora (515, pedido do próprio WhatsApp depois do pareamento)
 * - wipe: apaga as credenciais e desliga (401, saiu pelo celular)
 * - stop: desliga e mantém as credenciais (440, conectado em outro lugar)
 * - expired: QR Code esgotado (408 antes de parear)
 * - reconnect: tenta de novo com espera crescente
 */
export function disconnectAction (code, { registered = false } = {}) {
  switch (code) {
    case 515:
      return { action: 'restart' }
    case 401:
      return { action: 'wipe', status: 'disconnected', wanted: false, error: ERROR_TEXTS.loggedOut }
    case 440:
      return { action: 'stop', status: 'error', error: ERROR_TEXTS.replaced }
    case 408:
      if (!registered) {
        return { action: 'expired', status: 'disconnected', wanted: false, error: ERROR_TEXTS.qrExpired }
      }
      return { action: 'reconnect' }
    default:
      return { action: 'reconnect' }
  }
}

/** Espera antes da tentativa `attempt` (0, 1, 2...): 2 s, 4 s, 8 s... até 60 s. */
export function backoffDelay (attempt, { baseMs = 2000, maxMs = 60000, jitter = 0, random = Math.random } = {}) {
  const n = Math.max(0, Math.floor(Number(attempt) || 0))
  const raw = Math.min(maxMs, baseMs * 2 ** Math.min(n, 30))
  if (!jitter) return raw
  const spread = raw * jitter
  return Math.max(0, Math.min(maxMs, Math.round(raw - spread + random() * spread * 2)))
}

/** Hash FNV-1a de 32 bits (estável entre processos e versões do Node). */
export function fnv1a (text) {
  let hash = 0x811c9dc5
  const str = String(text)
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193)
  }
  return hash >>> 0
}

/** Em qual processo filho a sessão roda. */
export function shardFor (sessionId, workers) {
  const n = Math.max(1, Math.floor(Number(workers) || 1))
  return fnv1a(String(sessionId).toLowerCase()) % n
}

/** Orçamento do histórico de uma sessão: no máximo `maxChats` conversas e `maxPerChat` mensagens cada. */
export function createHistoryBudget ({ maxChats = 50, maxPerChat = 20 } = {}) {
  return { maxChats, maxPerChat, chats: new Map(), altOf: new Map() }
}

function tsSeconds (msg) {
  const iso = toIsoTimestamp(msg?.messageTimestamp, 0)
  return Date.parse(iso) / 1000
}

/**
 * Escolhe, de um lote de `messaging-history.set`, as conversas individuais mais recentes e as
 * mensagens mais novas de cada uma, respeitando o orçamento (que é atualizado aqui).
 * Devolve { messages, jids, chatContacts, mediaItems }.
 */
export function selectHistory (sessionId, { messages = [], chats = [] } = {}, budget) {
  const altOf = budget.altOf || (budget.altOf = new Map())
  const chatContacts = []
  for (const chat of chats || []) {
    if (!chat || typeof chat !== 'object') continue
    const { pn, lid } = splitJids(chat.id, chat.pnJid, chat.lidJid, chat.accountLid)
    if (pn && lid) {
      altOf.set(pn, lid)
      altOf.set(lid, pn)
    }
    const primary = pn || lid
    const secondary = pn && lid ? lid : null
    const chatName = cleanName(chat.name) || cleanName(chat.displayName)
    if (primary && (chatName || secondary)) {
      const ev = {
        type: 'contact',
        session_id: sessionId,
        jid: primary,
        name: chatName || null,
        source: chatName ? 'chat' : 'push'
      }
      if (secondary) ev.jid_alt = secondary
      chatContacts.push(ev)
    }
  }
  const byChat = new Map()
  for (const msg of messages || []) {
    const event = mapMessage(sessionId, msg, { history: true })
    if (!event) continue
    if (!event.remote_jid_alt && altOf.has(event.remote_jid)) {
      event.remote_jid_alt = altOf.get(event.remote_jid)
    }
    // Agrupa pelo número quando conhecido, evitando separar mensagens LID e PN da mesma conversa.
    const { pn, lid } = splitJids(event.remote_jid, event.remote_jid_alt)
    const key = pn || lid || event.remote_jid
    const list = byChat.get(key) || []
    list.push({ event, rawMsg: msg, ts: tsSeconds(msg) })
    byChat.set(key, list)
  }
  const ordered = [...byChat.entries()]
    .map(([jid, list]) => ({ jid, list, newest: Math.max(...list.map((item) => item.ts)) }))
    .sort((a, b) => b.newest - a.newest)
  const selected = []
  const mediaItems = []
  const jids = []
  for (const { jid, list } of ordered) {
    const used = budget.chats.get(jid)
    if (used === undefined && budget.chats.size >= budget.maxChats) continue
    const room = budget.maxPerChat - (used || 0)
    if (room <= 0) continue
    const newest = list.sort((a, b) => b.ts - a.ts).slice(0, room)
    budget.chats.set(jid, (used || 0) + newest.length)
    if (!jids.includes(jid)) jids.push(jid)
    for (const item of newest.reverse()) {
      if (item.event.remote_jid && !jids.includes(item.event.remote_jid)) jids.push(item.event.remote_jid)
      if (item.event.remote_jid_alt && !jids.includes(item.event.remote_jid_alt)) jids.push(item.event.remote_jid_alt)
      selected.push(item.event)
      const meta = extractMediaMeta(item.rawMsg?.message)
      if (meta) mediaItems.push({ externalId: item.event.external_id, rawMsg: item.rawMsg, meta, ts: item.ts })
    }
  }
  mediaItems.sort((a, b) => b.ts - a.ts)
  return { messages: selected, jids, chatContacts, mediaItems }
}
