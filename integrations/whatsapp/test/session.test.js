import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { describe, it } from 'node:test'
import { proto } from 'baileys'
import { Gate } from '../src/gate.js'
import { ERROR_TEXTS } from '../src/mapping.js'
import { Session, createVersionResolver, shouldSyncHistoryMessage } from '../src/session.js'

const SID = '11111111-2222-3333-4444-555555555555'
const ME = '5511999999999:12@s.whatsapp.net'

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

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const silent = { warn () {}, error () {}, info () {}, debug () {}, trace () {} }
silent.child = () => silent

/** Monta uma sessão com socket, credenciais, versão e vaga de pareamento de mentira. */
function setup ({ registered = false, gateLimit = 1 } = {}) {
  const sockets = []
  const events = []
  const removed = []
  const remembered = []
  const hooks = { ready: 0, ended: 0 }
  let loads = 0
  const creds = registered ? { me: { id: ME, name: 'Fulano' } } : {}

  const makeSocket = (config) => {
    const sock = {
      config,
      ev: new EventEmitter(),
      ws: new EventEmitter(),
      nodes: [],
      messages: [],
      reads: [],
      ended: false,
      loggedOut: false,
      user: null,
      async sendNode (node) { sock.nodes.push(node) },
      async end () { sock.ended = true },
      async logout () { sock.loggedOut = true },
      async sendMessage (jid, content, options) {
        sock.messages.push({ jid, content, options })
        return { key: { id: `WA${sock.messages.length}`, remoteJid: jid, fromMe: true }, message: { conversation: content.text } }
      },
      async readMessages (keys) { sock.reads.push(keys) }
    }
    sockets.push(sock)
    return sock
  }

  const authStore = {
    async load () {
      loads += 1
      return { state: { creds, keys: {} }, saveCreds: async () => {}, release () {} }
    },
    async removeAll (id) { removed.push(id) }
  }
  const gate = new Gate(gateLimit)
  const baileysLogger = { ...silent, lib: 'baileys' }
  const session = new Session(SID, {
    authStore,
    versions: { resolve: async () => [2, 3000, 5], remember: async (v) => { remembered.push(v) } },
    emit: (event) => events.push(event),
    logger: silent,
    baileysLogger,
    gate,
    makeSocket,
    onReady: () => { hooks.ready += 1 },
    onEnded: () => { hooks.ended += 1 }
  })
  const last = () => sockets.at(-1)
  const update = (data) => last().ev.emit('connection.update', data)
  const close = (statusCode) => update({ connection: 'close', lastDisconnect: { error: { output: { statusCode } } } })
  const statuses = () => events.filter((e) => e.type === 'status')
  return { session, sockets, events, removed, remembered, hooks, gate, creds, last, update, close, statuses, baileysLogger, loads: () => loads }
}

async function started (opts) {
  const ctx = setup(opts)
  await ctx.session.start()
  await waitFor(() => ctx.sockets.length === 1)
  return ctx
}

async function opened (opts = {}) {
  const ctx = await started({ registered: true, ...opts })
  ctx.update({ connection: 'open' })
  return ctx
}

describe('Session: abertura do socket', () => {
  it('usa as opções do contrato', async () => {
    const { last, baileysLogger, statuses, session } = await started()
    const config = last().config
    assert.deepEqual(config.version, [2, 3000, 5])
    assert.equal(config.browser[0], 'Mac OS')
    assert.equal(config.browser[1], 'Chrome')
    assert.ok(!config.browser.includes('Desktop'))
    assert.equal(config.syncFullHistory, false)
    assert.equal(config.markOnlineOnConnect, false)
    assert.equal(config.emitOwnEvents, false)
    assert.equal(config.countryCode, 'BR')
    assert.equal(config.generateHighQualityLinkPreview, false)
    assert.equal(config.logger, baileysLogger)
    assert.equal(config.shouldIgnoreJid('123@g.us'), true)
    assert.equal(config.shouldIgnoreJid('status@broadcast'), true)
    assert.equal(config.shouldIgnoreJid('1@newsletter'), true)
    assert.equal(config.shouldIgnoreJid('5511999999999@s.whatsapp.net'), false)
    assert.equal(config.shouldSyncHistoryMessage, shouldSyncHistoryMessage)
    assert.deepEqual(statuses(), [{ type: 'status', session_id: SID, status: 'connecting' }])
    assert.equal(session.status, 'connecting')
    await session.close()
  })

  it('histórico: baixa o recente e os mapeamentos, nunca o completo (nem desliga tudo)', () => {
    const T = proto.HistorySync.HistorySyncType
    assert.equal(shouldSyncHistoryMessage({ syncType: T.RECENT }), true)
    assert.equal(shouldSyncHistoryMessage({ syncType: T.INITIAL_BOOTSTRAP }), true)
    assert.equal(shouldSyncHistoryMessage({ syncType: T.PUSH_NAME }), true)
    assert.equal(shouldSyncHistoryMessage({ syncType: T.NON_BLOCKING_DATA }), true)
    assert.equal(shouldSyncHistoryMessage({ syncType: T.FULL }), false)
    assert.equal(shouldSyncHistoryMessage({ syncType: T.ON_DEMAND }), false)
  })

  it('QR: manda o status qr e libera a vaga de pareamento', async () => {
    const { update, statuses, gate, session } = await started()
    assert.equal(gate.active, 1)
    update({ qr: 'codigo-qr' })
    assert.deepEqual(statuses().at(-1), { type: 'status', session_id: SID, status: 'qr', qr: 'codigo-qr' })
    assert.equal(session.status, 'qr')
    assert.equal(gate.active, 0)
    assert.ok(session.info().first_qr_ms >= 0)
    await session.close()
  })

  it('a vaga de pareamento limita quantas sessões abrem ao mesmo tempo', async () => {
    const gate = new Gate(1)
    const a = setup()
    const b = setup()
    a.session.deps.gate = gate
    b.session.deps.gate = gate
    await a.session.start()
    await b.session.start()
    await waitFor(() => a.sockets.length === 1)
    await sleep(20)
    assert.equal(b.sockets.length, 0, 'a segunda espera a vaga')
    a.update({ qr: 'x' })
    await waitFor(() => b.sockets.length === 1)
    await a.session.close()
    await b.session.close()
  })

  it('open: status ready com número, nome e JID; salva a versão e avisa o processo', async () => {
    const { statuses, remembered, hooks, session } = await opened()
    assert.deepEqual(statuses().at(-1), {
      type: 'status',
      session_id: SID,
      status: 'ready',
      phone: '5511999999999',
      display_name: 'Fulano',
      wa_jid: '5511999999999@s.whatsapp.net'
    })
    assert.equal(session.ready, true)
    await waitFor(() => remembered.length === 1)
    assert.deepEqual(remembered[0], [2, 3000, 5])
    assert.equal(hooks.ready, 1)
    await session.close()
  })

  it('confirma os avisos "status" do WhatsApp (correção da queda a cada ~50 min)', async () => {
    const { last, session } = await opened()
    last().ws.emit('CB:status', { tag: 'status', attrs: { id: 'N1', from: 's.whatsapp.net', type: 'set' } })
    last().ws.emit('CB:status', { tag: 'status', attrs: { id: 'N2', from: 'x@s.whatsapp.net', participant: 'y@lid' } })
    last().ws.emit('CB:status', { tag: 'status', attrs: {} })
    assert.deepEqual(last().nodes, [
      { tag: 'ack', attrs: { id: 'N1', to: 's.whatsapp.net', class: 'status', type: 'set' } },
      { tag: 'ack', attrs: { id: 'N2', to: 'x@s.whatsapp.net', class: 'status', participant: 'y@lid' } }
    ])
    await session.close()
  })
})

describe('Session: quedas (DisconnectReason)', () => {
  it('515 (restartRequired) reconecta na hora com as mesmas credenciais', async () => {
    const ctx = await started()
    ctx.update({ qr: 'x' })
    ctx.close(515)
    await waitFor(() => ctx.sockets.length === 2)
    assert.equal(ctx.loads(), 1, 'não recarrega as credenciais')
    assert.deepEqual(ctx.removed, [])
    await ctx.session.close()
  })

  it('401 (saiu pelo celular) apaga as credenciais, desliga e manda wanted:false', async () => {
    const ctx = await opened()
    ctx.close(401)
    await waitFor(() => ctx.hooks.ended === 1)
    assert.deepEqual(ctx.removed, [SID])
    assert.deepEqual(ctx.statuses().at(-1), {
      type: 'status', session_id: SID, status: 'disconnected', wanted: false, error: ERROR_TEXTS.loggedOut
    })
    assert.equal(ctx.session.status, 'stopped')
    await sleep(30)
    assert.equal(ctx.sockets.length, 1, 'não tenta reconectar')
  })

  it('408 antes de parear = QR expirou: desliga com wanted:false', async () => {
    const ctx = await started()
    ctx.update({ qr: 'x' })
    ctx.close(408)
    await waitFor(() => ctx.hooks.ended === 1)
    assert.deepEqual(ctx.statuses().at(-1), {
      type: 'status', session_id: SID, status: 'disconnected', wanted: false, error: ERROR_TEXTS.qrExpired
    })
    await sleep(30)
    assert.equal(ctx.sockets.length, 1)
  })

  it('440 (conectado em outro lugar) para com erro e mantém as credenciais', async () => {
    const ctx = await opened()
    ctx.close(440)
    await waitFor(() => ctx.hooks.ended === 1)
    assert.deepEqual(ctx.statuses().at(-1), { type: 'status', session_id: SID, status: 'error', error: ERROR_TEXTS.replaced })
    assert.deepEqual(ctx.removed, [])
  })

  it('demais códigos reconectam com espera crescente', async () => {
    const ctx = await opened()
    ctx.close(428)
    assert.equal(ctx.session.status, 'connecting')
    assert.ok(ctx.session.reconnectTimer, 'reconexão agendada')
    assert.equal(ctx.session.attempt, 1)
    assert.equal(ctx.sockets.length, 1, 'não reconecta na hora')
    assert.deepEqual(ctx.removed, [])
    await ctx.session.close()
    assert.equal(ctx.session.reconnectTimer, null)
  })

  it('eventos do socket antigo são ignorados depois de parar', async () => {
    const ctx = await opened()
    const old = ctx.last()
    await ctx.session.stop({ logout: false })
    assert.equal(old.ended, true)
    const before = ctx.events.length
    old.ev.emit('connection.update', { connection: 'close', lastDisconnect: { error: { output: { statusCode: 401 } } } })
    old.ev.emit('messages.upsert', { messages: [{ key: { id: 'A', remoteJid: '5511888888888@s.whatsapp.net' }, message: { conversation: 'oi' } }] })
    await sleep(20)
    assert.equal(ctx.events.length, before)
    assert.deepEqual(ctx.removed, [])
  })

  it('stop com logout desconecta o aparelho e apaga as credenciais', async () => {
    const ctx = await opened()
    await ctx.session.stop({ logout: true })
    assert.equal(ctx.last().loggedOut, true)
    assert.equal(ctx.last().ended, true)
    assert.deepEqual(ctx.removed, [SID])
    assert.equal(ctx.session.status, 'stopped')
    assert.equal(ctx.hooks.ended, 1)
  })
})

describe('Session: mensagens', () => {
  it('messages.upsert vira evento message (grupos ficam de fora)', async () => {
    const ctx = await opened()
    ctx.last().ev.emit('messages.upsert', {
      type: 'notify',
      messages: [
        { key: { id: 'A1', remoteJid: '123@lid', remoteJidAlt: '5511888888888@s.whatsapp.net', fromMe: false }, pushName: 'Maria', messageTimestamp: 1700000000, message: { conversation: 'oi' } },
        { key: { id: 'G1', remoteJid: '123-456@g.us', fromMe: false }, message: { conversation: 'grupo' } }
      ]
    })
    const messages = ctx.events.filter((e) => e.type === 'message')
    assert.equal(messages.length, 1)
    assert.deepEqual(messages[0], {
      type: 'message',
      session_id: SID,
      external_id: 'A1',
      remote_jid: '123@lid',
      remote_jid_alt: '5511888888888@s.whatsapp.net',
      from_me: false,
      push_name: 'Maria',
      body: 'oi',
      message_type: 'chat',
      timestamp: new Date(1700000000 * 1000).toISOString()
    })
    await ctx.session.close()
  })

  it('messages.update vira recibo (minha) ou read_self (lida no celular)', async () => {
    const ctx = await opened()
    ctx.last().ev.emit('messages.update', [
      { key: { id: 'M1', remoteJid: '5511888888888@s.whatsapp.net', fromMe: true }, update: { status: 3 } },
      { key: { id: 'M2', remoteJid: '5511888888888@s.whatsapp.net', fromMe: false }, update: { status: 4 } }
    ])
    assert.deepEqual(ctx.events.filter((e) => e.type !== 'status'), [
      { type: 'receipt', session_id: SID, external_id: 'M1', status: 'delivered' },
      { type: 'read_self', session_id: SID, remote_jid: '5511888888888@s.whatsapp.net' }
    ])
    await ctx.session.close()
  })

  it('histórico do pareamento vem marcado e o nome do contato só sai para conversas conhecidas', async () => {
    const ctx = await opened()
    ctx.last().ev.emit('messaging-history.set', {
      messages: [{ key: { id: 'H1', remoteJid: '5511777777777@s.whatsapp.net', fromMe: true }, messageTimestamp: 1700000000, message: { conversation: 'antiga' } }],
      chats: [],
      contacts: [
        { id: '5511777777777@s.whatsapp.net', name: 'Pedro' },
        { id: '5511666666666@s.whatsapp.net', name: 'Desconhecido' }
      ]
    })
    const others = ctx.events.filter((e) => e.type !== 'status')
    assert.equal(others.length, 2)
    assert.equal(others[0].history, true)
    assert.deepEqual(others[1], { type: 'contact', session_id: SID, jid: '5511777777777@s.whatsapp.net', name: 'Pedro', source: 'contact' })
    // Mesmo nome de novo não gera outro evento.
    ctx.last().ev.emit('contacts.update', [{ id: '5511777777777@s.whatsapp.net', name: 'Pedro' }])
    assert.equal(ctx.events.filter((e) => e.type === 'contact').length, 1)
    await ctx.session.close()
  })

  it('contato que chega antes da mensagem fica em cache e agenda substitui apelido', async () => {
    const ctx = await opened()
    const jid = '5511944443333@s.whatsapp.net'
    ctx.last().ev.emit('contacts.upsert', [{ id: jid, name: 'Carlos Agenda' }])
    assert.equal(ctx.events.filter((e) => e.type === 'contact').length, 0)
    ctx.last().ev.emit('messages.upsert', {
      messages: [{ key: { id: 'C1', remoteJid: jid, fromMe: false }, pushName: 'carlos', messageTimestamp: 1700000000, message: { conversation: 'oi' } }]
    })
    const contacts = ctx.events.filter((e) => e.type === 'contact')
    assert.equal(contacts.length, 1)
    assert.equal(contacts[0].name, 'Carlos Agenda')
    assert.equal(contacts[0].source, 'contact')
    await ctx.session.close()
  })

  it('baixa mídia recebida em segundo plano e envia mídia da fila', async () => {
    const uploadedMedia = []
    const uploadedAvatars = []
    const ctx = await opened()
    ctx.session.deps.uploadMedia = async (_sid, payload) => {
      uploadedMedia.push(payload)
      return { media_id: '22222222-3333-4444-5555-666666666666' }
    }
    ctx.session.deps.downloadMedia = async () => Buffer.from('img-out')
    ctx.session.deps.uploadAvatar = async (_sid, payload) => { uploadedAvatars.push(payload) }
    ctx.session.downloadBaileysMedia = async () => Buffer.from('img-in')
    ctx.session.fetchAvatar = async () => ({
      ok: true,
      headers: { get: () => 'image/jpeg' },
      arrayBuffer: async () => Uint8Array.from([1, 2, 3]).buffer
    })
    ctx.last().profilePictureUrl = async () => 'https://pps.whatsapp.net/foto.jpg'

    ctx.last().ev.emit('messages.upsert', {
      messages: [{
        key: { id: 'PIC1', remoteJid: '5511933332222@s.whatsapp.net', fromMe: false },
        messageTimestamp: 1700000000,
        message: { imageMessage: { mimetype: 'image/jpeg', caption: 'olá' } }
      }]
    })
    await waitFor(() => ctx.events.some((e) => e.type === 'media_attach'))
    await waitFor(() => uploadedAvatars.length === 1)
    assert.equal(uploadedMedia.length, 1)
    assert.equal(uploadedMedia[0].kind, 'image')
    assert.equal(uploadedAvatars[0].jid, '5511933332222@s.whatsapp.net')

    const res = await ctx.session.send({
      message_id: 'out-img',
      remote_jid: '5511933332222@s.whatsapp.net',
      body: '📷 Foto · envio',
      caption: 'envio',
      media: { media_id: '22222222-3333-4444-5555-666666666666', kind: 'image', mime_type: 'image/png' }
    })
    assert.equal(res.externalId, 'WA1')
    assert.ok(Buffer.isBuffer(ctx.last().messages[0].content.image))
    assert.equal(ctx.last().messages[0].content.caption, 'envio')
    await ctx.session.close()
  })

  it('envia texto com mensagem citada e devolve o id do WhatsApp', async () => {
    const ctx = await opened()
    const result = await ctx.session.send({
      message_id: 'm1',
      remote_jid: '5511888888888@c.us',
      body: 'resposta',
      quoted: { external_id: 'Q1', from_me: false, remote_jid: '5511888888888@s.whatsapp.net', body: 'pergunta' }
    })
    assert.deepEqual(result, { externalId: 'WA1' })
    const sent = ctx.last().messages[0]
    assert.equal(sent.jid, '5511888888888@s.whatsapp.net')
    assert.deepEqual(sent.content, { text: 'resposta', linkPreview: null })
    assert.deepEqual(sent.options.quoted, {
      key: { remoteJid: '5511888888888@s.whatsapp.net', fromMe: false, id: 'Q1' },
      message: { conversation: 'pergunta' }
    })
    // Sem citação: sem opções extras.
    await ctx.session.send({ message_id: 'm2', remote_jid: '5511888888888@s.whatsapp.net', body: 'oi', quoted: null })
    assert.deepEqual(ctx.last().messages[1].options, {})
    await assert.rejects(ctx.session.send({ message_id: 'm3', remote_jid: '123@g.us', body: 'x' }), /Destino inválido/)
    await ctx.session.close()
  })

  it('sem conexão pronta, o envio é adiado (skipped) e a leitura não acontece', async () => {
    const ctx = await started()
    assert.deepEqual(await ctx.session.send({ message_id: 'm1', remote_jid: '5511888888888@s.whatsapp.net', body: 'x' }), { skipped: true })
    assert.equal(await ctx.session.read('5511888888888@s.whatsapp.net', ['A']), false)
    await ctx.session.close()
  })

  it('confirmação de leitura manda as chaves das mensagens recebidas', async () => {
    const ctx = await opened()
    assert.equal(await ctx.session.read('123@lid', ['A', '', 'B']), true)
    assert.deepEqual(ctx.last().reads[0], [
      { remoteJid: '123@lid', id: 'A', fromMe: false },
      { remoteJid: '123@lid', id: 'B', fromMe: false }
    ])
    await ctx.session.close()
  })
})

describe('createVersionResolver', () => {
  function kvStore (initial) {
    const data = new Map(initial ? [['wa_version', initial]] : [])
    return { data, async get (k) { return data.get(k) ?? null }, async set (k, v) { data.set(k, v) } }
  }

  it('usa a versão mais nova quando a busca funciona', async () => {
    const kv = kvStore('[2,3000,1]')
    const resolver = createVersionResolver({ kv, fetchLatest: async () => ({ version: [2, 3000, 9], isLatest: true }) })
    assert.deepEqual(await resolver.resolve(), [2, 3000, 9])
  })

  it('se a busca falhar, usa a última versão boa salva; sem ela, a padrão da lib (undefined)', async () => {
    const failing = async () => ({ version: [2, 3000, 0], isLatest: false, error: new Error('rede') })
    assert.deepEqual(await createVersionResolver({ kv: kvStore('[2,3000,7]'), fetchLatest: failing }).resolve(), [2, 3000, 7])
    const throwing = async () => { throw new Error('fora do ar') }
    assert.deepEqual(await createVersionResolver({ kv: kvStore('[2,3000,7]'), fetchLatest: throwing }).resolve(), [2, 3000, 7])
    assert.equal(await createVersionResolver({ kv: kvStore('lixo'), fetchLatest: failing }).resolve(), undefined)
    assert.equal(await createVersionResolver({ kv: kvStore(null), fetchLatest: failing }).resolve(), undefined)
    const brokenKv = { async get () { throw new Error('banco fora') }, async set () {} }
    assert.equal(await createVersionResolver({ kv: brokenKv, fetchLatest: failing }).resolve(), undefined)
  })

  it('chamadas juntas dividem a mesma busca e o resultado fica guardado por um tempo', async () => {
    let calls = 0
    let now = 0
    const fetchLatest = async () => {
      calls += 1
      await sleep(10)
      return { version: [2, 3000, calls], isLatest: true }
    }
    const resolver = createVersionResolver({ kv: kvStore(), fetchLatest, cacheMs: 1000, now: () => now })
    const [a, b] = await Promise.all([resolver.resolve(), resolver.resolve()])
    assert.deepEqual(a, b)
    assert.equal(calls, 1)
    await resolver.resolve()
    assert.equal(calls, 1)
    now = 5000
    assert.deepEqual(await resolver.resolve(), [2, 3000, 2])
  })

  it('remember grava em wa_version só quando muda e ignora versão inválida', async () => {
    const kv = kvStore()
    let writes = 0
    const counting = { get: kv.get, async set (k, v) { writes += 1; return kv.set(k, v) } }
    const resolver = createVersionResolver({ kv: counting, fetchLatest: async () => ({ isLatest: false }) })
    await resolver.remember([2, 3000, 4])
    await resolver.remember([2, 3000, 4])
    await resolver.remember('lixo')
    assert.equal(writes, 1)
    assert.equal(kv.data.get('wa_version'), '[2,3000,4]')
  })
})
