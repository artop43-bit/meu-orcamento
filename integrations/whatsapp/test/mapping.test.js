import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { isJidBroadcast, isJidGroup, isJidNewsletter, isJidStatusBroadcast } from 'baileys'
import {
  ERROR_TEXTS,
  backoffDelay,
  buildMediaSendContent,
  buildQuotedMessage,
  cleanName,
  createHistoryBudget,
  disconnectAction,
  extractContent,
  extractMediaMeta,
  fnv1a,
  mapContact,
  mapMessage,
  mapMessageUpdate,
  normalizeJid,
  phoneFromJid,
  selectHistory,
  shardFor,
  shouldIgnoreJid,
  splitJids,
  statusName,
  toIsoTimestamp
} from '../src/mapping.js'

const SID = '11111111-2222-3333-4444-555555555555'
const PN = '5511999998888@s.whatsapp.net'
const LID = '123456789012345@lid'

function msg ({ id = 'ABC', remoteJid = PN, remoteJidAlt, fromMe = false, message, ts = 1763550000, pushName } = {}) {
  return { key: { id, remoteJid, remoteJidAlt, fromMe }, message, messageTimestamp: ts, pushName }
}

describe('JIDs', () => {
  it('normaliza aparelho e o antigo @c.us', () => {
    assert.equal(normalizeJid('5511999998888:12@s.whatsapp.net'), PN)
    assert.equal(normalizeJid('5511999998888@c.us'), PN)
    assert.equal(normalizeJid(LID), LID)
    assert.equal(normalizeJid('sem-arroba'), null)
    assert.equal(normalizeJid(undefined), null)
  })

  it('separa número e LID de remoteJid/remoteJidAlt', () => {
    assert.deepEqual(splitJids(LID, PN), { pn: PN, lid: LID })
    assert.deepEqual(splitJids(PN, undefined), { pn: PN, lid: null })
    assert.deepEqual(splitJids(null, LID), { pn: null, lid: LID })
  })

  it('extrai só os dígitos do número', () => {
    assert.equal(phoneFromJid('5511999998888:3@s.whatsapp.net'), '5511999998888')
    assert.equal(phoneFromJid(LID), null)
  })

  it('ignora grupos, listas, status e canais como a própria Baileys', () => {
    const cases = ['123-456@g.us', 'status@broadcast', '999@broadcast', '120363@newsletter', PN, LID]
    for (const jid of cases) {
      const expected = Boolean(isJidGroup(jid) || isJidBroadcast(jid) || isJidNewsletter(jid) || isJidStatusBroadcast(jid))
      assert.equal(shouldIgnoreJid(jid), expected, jid)
    }
    assert.equal(shouldIgnoreJid(PN), false)
    assert.equal(shouldIgnoreJid('123-456@g.us'), true)
  })
})

describe('conteúdo das mensagens', () => {
  it('lê texto simples e texto estendido', () => {
    assert.deepEqual(extractContent({ conversation: 'Oi!' }), { body: 'Oi!', messageType: 'chat', quotedId: null })
    assert.deepEqual(
      extractContent({ extendedTextMessage: { text: 'Respondendo', contextInfo: { stanzaId: 'Q1' } } }),
      { body: 'Respondendo', messageType: 'chat', quotedId: 'Q1' }
    )
  })

  it('usa os textos combinados para mídia', () => {
    assert.equal(extractContent({ imageMessage: {} }).body, '📷 Foto')
    assert.equal(extractContent({ imageMessage: { caption: 'Praia' } }).body, '📷 Foto · Praia')
    assert.equal(extractContent({ audioMessage: { ptt: true } }).body, '🎤 Áudio')
    assert.equal(extractContent({ videoMessage: {} }).body, '🎬 Vídeo')
    assert.equal(extractContent({ documentMessage: { fileName: 'boleto.pdf' } }).body, '📄 Documento · boleto.pdf')
    assert.equal(extractContent({ documentMessage: {} }).body, '📄 Documento')
    assert.equal(extractContent({ stickerMessage: {} }).body, 'Figurinha')
    assert.deepEqual(extractContent({ locationMessage: { degreesLatitude: 1 } }), { body: 'Mensagem não suportada', messageType: 'other', quotedId: null })
    assert.equal(extractContent({ imageMessage: {} }).messageType, 'image')
    assert.equal(extractContent({ audioMessage: {} }).messageType, 'audio')
    assert.equal(extractContent({ videoMessage: {} }).messageType, 'video')
    assert.equal(extractContent({ documentMessage: {} }).messageType, 'document')
    assert.equal(extractContent({ stickerMessage: {} }).messageType, 'sticker')
  })

  it('abre os embrulhos (temporária, visualização única, documento com legenda)', () => {
    assert.equal(extractContent({ ephemeralMessage: { message: { conversation: 'some em 7 dias' } } }).body, 'some em 7 dias')
    assert.equal(extractContent({ viewOnceMessageV2: { message: { imageMessage: { caption: 'x' } } } }).body, '📷 Foto · x')
    assert.equal(
      extractContent({ documentWithCaptionMessage: { message: { documentMessage: { fileName: 'nota.pdf', caption: 'segue' } } } }).body,
      '📄 Documento · nota.pdf'
    )
    assert.equal(
      extractContent({ ephemeralMessage: { message: { viewOnceMessage: { message: { videoMessage: {} } } } } }).messageType,
      'video'
    )
  })

  it('ignora mensagens de protocolo, reações e avisos de mensagens temporárias', () => {
    assert.equal(extractContent({ protocolMessage: { type: 0 } }), null)
    assert.equal(extractContent({ reactionMessage: { text: '👍' } }), null)
    assert.equal(extractContent({ ephemeralMessage: { message: { protocolMessage: { type: 3, ephemeralExpiration: 604800 } } } }), null)
    assert.equal(extractContent({ senderKeyDistributionMessage: {}, messageContextInfo: {} }), null)
    assert.equal(extractContent(null), null)
  })

  it('não deixa os campos de contexto esconderem o texto', () => {
    assert.equal(extractContent({ messageContextInfo: { deviceListMetadata: {} }, conversation: 'olá' }).body, 'olá')
  })
})

describe('mapMessage', () => {
  it('gera o evento message do contrato', () => {
    const event = mapMessage(SID, msg({ remoteJid: LID, remoteJidAlt: PN, message: { conversation: 'Oi' }, pushName: 'Maria' }))
    assert.deepEqual(event, {
      type: 'message',
      session_id: SID,
      external_id: 'ABC',
      remote_jid: LID,
      remote_jid_alt: PN,
      from_me: false,
      body: 'Oi',
      message_type: 'chat',
      timestamp: new Date(1763550000 * 1000).toISOString(),
      push_name: 'Maria'
    })
  })

  it('mensagem minha não leva push_name e histórico vem marcado', () => {
    const event = mapMessage(SID, msg({ fromMe: true, message: { conversation: 'Eu' }, pushName: 'Eu mesmo' }), { history: true })
    assert.equal(event.from_me, true)
    assert.equal(event.push_name, undefined)
    assert.equal(event.history, true)
  })

  it('leva o id da mensagem citada', () => {
    const event = mapMessage(SID, msg({ message: { extendedTextMessage: { text: 'sim', contextInfo: { stanzaId: 'ORIG' } } } }))
    assert.equal(event.quoted_external_id, 'ORIG')
  })

  it('ignora grupos, status, mensagens sem conteúdo e sem id', () => {
    assert.equal(mapMessage(SID, msg({ remoteJid: '123-456@g.us', message: { conversation: 'x' } })), null)
    assert.equal(mapMessage(SID, msg({ remoteJid: 'status@broadcast', message: { conversation: 'x' } })), null)
    assert.equal(mapMessage(SID, msg({ message: undefined })), null)
    assert.equal(mapMessage(SID, { key: { remoteJid: PN }, message: { conversation: 'x' } }), null)
  })

  it('converte horários em vários formatos', () => {
    assert.equal(toIsoTimestamp(1763550000), '2025-11-19T11:00:00.000Z')
    assert.equal(toIsoTimestamp('1763550000'), '2025-11-19T11:00:00.000Z')
    assert.equal(toIsoTimestamp({ low: 1763550000, high: 0, unsigned: true }), '2025-11-19T11:00:00.000Z')
    assert.equal(toIsoTimestamp({ toNumber: () => 1763550000 }), '2025-11-19T11:00:00.000Z')
    assert.equal(toIsoTimestamp(undefined, Date.UTC(2026, 0, 1)), '2026-01-01T00:00:00.000Z')
  })
})

describe('recibos e leitura', () => {
  it('converte o número do status para o texto do contrato', () => {
    assert.deepEqual([0, 1, 2, 3, 4, 5].map(statusName), ['failed', null, 'sent', 'delivered', 'read', 'played'])
    assert.equal(statusName(undefined), null)
  })

  it('status de mensagem minha vira receipt', () => {
    assert.deepEqual(mapMessageUpdate(SID, { key: { id: 'M1', remoteJid: PN, fromMe: true }, update: { status: 3 } }), {
      type: 'receipt', session_id: SID, external_id: 'M1', status: 'delivered'
    })
    const failed = mapMessageUpdate(SID, { key: { id: 'M1', remoteJid: PN, fromMe: true }, update: { status: 0 } })
    assert.equal(failed.status, 'failed')
    assert.equal(failed.error, ERROR_TEXTS.notDelivered)
    assert.equal(mapMessageUpdate(SID, { key: { id: 'M1', remoteJid: PN, fromMe: true }, update: { status: 1 } }), null)
  })

  it('READ numa mensagem recebida = a pessoa leu no celular (read_self)', () => {
    assert.deepEqual(mapMessageUpdate(SID, { key: { id: 'M2', remoteJid: LID, remoteJidAlt: PN, fromMe: false }, update: { status: 4 } }), {
      type: 'read_self', session_id: SID, remote_jid: LID, remote_jid_alt: PN
    })
    assert.equal(mapMessageUpdate(SID, { key: { id: 'M2', remoteJid: PN, fromMe: false }, update: { status: 3 } }), null)
  })

  it('ignora atualização sem status e de grupos', () => {
    assert.equal(mapMessageUpdate(SID, { key: { id: 'M3', remoteJid: PN, fromMe: true }, update: { message: {} } }), null)
    assert.equal(mapMessageUpdate(SID, { key: { id: 'M3', remoteJid: '1-2@g.us', fromMe: true }, update: { status: 4 } }), null)
  })
})

describe('contatos e mensagem citada', () => {
  it('contato com nome vira evento contact com origem e os dois JIDs', () => {
    assert.deepEqual(mapContact(SID, { id: LID, phoneNumber: PN, notify: 'Zé' }), {
      type: 'contact', session_id: SID, jid: LID, jid_alt: PN, name: 'Zé', source: 'push'
    })
    assert.deepEqual(mapContact(SID, { id: PN, name: 'Agenda', notify: 'Push' }), {
      type: 'contact', session_id: SID, jid: PN, name: 'Agenda', source: 'contact'
    })
    // Sem nome mas com os dois JIDs: ainda serve para juntar LID ↔ número.
    assert.deepEqual(mapContact(SID, { id: LID, phoneNumber: PN }), {
      type: 'contact', session_id: SID, jid: LID, jid_alt: PN, name: null, source: 'push'
    })
    assert.equal(mapContact(SID, { id: PN }), null)
    assert.equal(mapContact(SID, { id: '1-2@g.us', name: 'Grupo' }), null)
    // Nomes mascarados do WhatsApp e pontuação solta são rejeitados.
    assert.equal(cleanName('+55·······80'), null)
    assert.equal(cleanName('.'), null)
    assert.equal(cleanName('Luana'), 'Luana')
  })

  it('extrai metadados de mídia e monta conteúdo para envio', () => {
    const meta = extractMediaMeta({ imageMessage: { mimetype: 'image/jpeg', fileLength: 1024 } })
    assert.deepEqual(meta, { kind: 'image', mimeType: 'image/jpeg', fileName: null, fileLength: 1024, ptt: false })
    assert.equal(extractMediaMeta({ conversation: 'só texto' }), null)

    const buf = Buffer.from('abc')
    assert.deepEqual(
      buildMediaSendContent({ media: { kind: 'image', mime_type: 'image/png' }, caption: 'Foto' }, buf),
      { image: buf, mimetype: 'image/png', caption: 'Foto' }
    )
    assert.deepEqual(
      buildMediaSendContent({ media: { kind: 'audio', mime_type: 'audio/ogg' } }, buf),
      { audio: buf, mimetype: 'audio/ogg', ptt: true }
    )
    assert.deepEqual(
      buildMediaSendContent({ media: { kind: 'document', mime_type: 'application/pdf', file_name: 'fatura.pdf' }, caption: 'Anexo' }, buf),
      { document: buf, mimetype: 'application/pdf', fileName: 'fatura.pdf', caption: 'Anexo' }
    )
  })

  it('monta a mensagem citada mínima', () => {
    assert.deepEqual(buildQuotedMessage({ external_id: 'Q', from_me: true, remote_jid: LID, body: 'antes' }, PN), {
      key: { remoteJid: PN, fromMe: true, id: 'Q' },
      message: { conversation: 'antes' }
    })
    assert.equal(buildQuotedMessage(null, PN), null)
    assert.equal(buildQuotedMessage({ from_me: true }, PN), null)
  })
})

describe('política de desconexão', () => {
  it('515 reconecta na hora', () => {
    assert.equal(disconnectAction(515).action, 'restart')
  })

  it('401 apaga as credenciais e desliga', () => {
    assert.deepEqual(disconnectAction(401, { registered: true }), {
      action: 'wipe', status: 'disconnected', wanted: false, error: 'O WhatsApp foi desconectado pelo celular.'
    })
  })

  it('440 para com erro', () => {
    assert.deepEqual(disconnectAction(440, { registered: true }), {
      action: 'stop', status: 'error', error: 'Este número foi conectado em outro lugar.'
    })
  })

  it('408 antes de parear = QR expirado; depois de parear = reconecta', () => {
    assert.deepEqual(disconnectAction(408, { registered: false }), {
      action: 'expired', status: 'disconnected', wanted: false, error: 'O QR Code expirou. Gere um novo.'
    })
    assert.equal(disconnectAction(408, { registered: true }).action, 'reconnect')
  })

  it('demais códigos reconectam', () => {
    for (const code of [428, 500, 503, 411, undefined]) assert.equal(disconnectAction(code).action, 'reconnect')
  })

  it('espera cresce de 2 s até 60 s', () => {
    assert.deepEqual([0, 1, 2, 3, 4, 5, 6, 50].map((n) => backoffDelay(n)), [2000, 4000, 8000, 16000, 32000, 60000, 60000, 60000])
    const jittered = backoffDelay(2, { jitter: 0.2, random: () => 1 })
    assert.ok(jittered <= 9600 && jittered >= 6400)
  })
})

describe('distribuição entre processos', () => {
  it('FNV-1a é estável', () => {
    assert.equal(fnv1a(''), 0x811c9dc5)
    assert.equal(fnv1a('a'), 0xe40c292c)
    assert.equal(fnv1a('foobar'), 0xbf9cf968)
  })

  it('mesma sessão sempre no mesmo processo (maiúscula ou minúscula)', () => {
    const id = 'A1B2C3D4-0000-4000-8000-000000000001'
    assert.equal(shardFor(id, 4), shardFor(id.toLowerCase(), 4))
    assert.equal(shardFor(id, 1), 0)
  })

  it('espalha bem 10 mil sessões entre 2 e 4 processos', () => {
    for (const workers of [2, 4]) {
      const counts = new Array(workers).fill(0)
      for (let i = 0; i < 10000; i++) {
        const id = `${i.toString(16).padStart(8, '0')}-1111-4222-8333-${(i * 7919).toString(16).padStart(12, '0')}`
        counts[shardFor(id, workers)] += 1
      }
      const expected = 10000 / workers
      for (const c of counts) assert.ok(Math.abs(c - expected) / expected < 0.1, `desequilíbrio: ${counts}`)
    }
  })
})

describe('histórico do primeiro pareamento', () => {
  function chatMessages (jid, count, baseTs) {
    return Array.from({ length: count }, (_, i) => msg({ id: `${jid}-${i}`, remoteJid: jid, message: { conversation: `m${i}` }, ts: baseTs + i }))
  }

  it('pega até 50 conversas mais recentes e 20 mensagens de cada, só individuais', () => {
    const messages = []
    for (let c = 0; c < 60; c++) messages.push(...chatMessages(`55119${String(c).padStart(8, '0')}@s.whatsapp.net`, 30, 1000 + c * 100))
    messages.push(...chatMessages('123-456@g.us', 5, 999999))
    const budget = createHistoryBudget()
    const { messages: events, jids } = selectHistory(SID, { messages }, budget)
    assert.equal(jids.length, 50)
    assert.equal(events.length, 50 * 20)
    assert.ok(events.every((e) => e.history === true && e.remote_jid.endsWith('@s.whatsapp.net')))
    // As 10 conversas mais antigas (0..9) ficaram de fora.
    assert.ok(!jids.includes('5511900000000@s.whatsapp.net'))
    assert.ok(jids.includes('5511900000059@s.whatsapp.net'))
    // De cada conversa, as 20 mais novas, em ordem cronológica.
    const last = events.filter((e) => e.remote_jid === '5511900000059@s.whatsapp.net')
    assert.equal(last[0].body, 'm10')
    assert.equal(last[19].body, 'm29')
  })

  it('o orçamento vale entre lotes e completa o JID alternativo pela conversa', () => {
    const budget = createHistoryBudget({ maxChats: 2, maxPerChat: 3 })
    const first = selectHistory(SID, {
      messages: chatMessages(LID, 2, 100),
      chats: [{ id: LID, pnJid: PN }]
    }, budget)
    assert.equal(first.messages.length, 2)
    assert.equal(first.messages[0].remote_jid_alt, PN)
    assert.ok(first.jids.includes(PN))
    const second = selectHistory(SID, {
      messages: [...chatMessages(LID, 5, 200), ...chatMessages('5511888887777@s.whatsapp.net', 1, 300), ...chatMessages('5511777776666@s.whatsapp.net', 1, 50)]
    }, budget)
    // LID só tinha vaga para mais 1; a terceira conversa não cabe.
    assert.equal(second.messages.filter((e) => e.remote_jid === LID).length, 1)
    assert.equal(second.messages.filter((e) => e.remote_jid === '5511777776666@s.whatsapp.net').length, 0)
    assert.equal(budget.chats.size, 2)
  })

  it('vincula pnJid e lidJid nas duas direções, lê nome do chat e status do histórico', () => {
    const budget = createHistoryBudget({ maxChats: 5, maxPerChat: 10 })
    const hist = selectHistory(SID, {
      chats: [{ id: PN, pnJid: PN, lidJid: LID, name: 'Luana Silva' }],
      messages: [
        { ...msg({ id: 'H1', remoteJid: LID, fromMe: true, message: { conversation: 'oi' }, ts: 100 }), status: 4 },
        { ...msg({ id: 'H2', remoteJid: PN, fromMe: false, message: { imageMessage: { mimetype: 'image/jpeg' } }, ts: 101 }) }
      ]
    }, budget)
    assert.equal(hist.messages.length, 2)
    assert.equal(hist.messages[0].remote_jid_alt, PN)
    assert.equal(hist.messages[0].status, 'read')
    assert.equal(hist.messages[1].remote_jid_alt, LID)
    assert.equal(hist.chatContacts.length, 1)
    assert.equal(hist.chatContacts[0].name, 'Luana Silva')
    assert.equal(hist.chatContacts[0].jid, PN)
    assert.equal(hist.chatContacts[0].jid_alt, LID)
    assert.equal(hist.mediaItems.length, 1)
    assert.equal(hist.mediaItems[0].externalId, 'H2')
  })

  it('ordena mediaItems do histórico da mídia mais recente para a mais antiga', () => {
    const budget = createHistoryBudget({ maxChats: 5, maxPerChat: 10 })
    const hist = selectHistory(SID, {
      messages: [
        msg({ id: 'OLD_AUDIO', remoteJid: PN, message: { audioMessage: { mimetype: 'audio/ogg' } }, ts: 100 }),
        msg({ id: 'NEW_AUDIO', remoteJid: '5511888887777@s.whatsapp.net', message: { audioMessage: { mimetype: 'audio/ogg' } }, ts: 500 }),
        msg({ id: 'MID_AUDIO', remoteJid: PN, message: { audioMessage: { mimetype: 'audio/ogg' } }, ts: 300 })
      ]
    }, budget)
    assert.deepEqual(hist.mediaItems.map((m) => m.externalId), ['NEW_AUDIO', 'MID_AUDIO', 'OLD_AUDIO'])
  })
})
