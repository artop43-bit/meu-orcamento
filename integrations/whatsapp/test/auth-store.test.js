import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { proto } from 'baileys'
import {
  AuthStore,
  CREDS_CATEGORY,
  TtlCache,
  createPgAuthRepository,
  createPgKvRepository,
  deserialize,
  safeKeyId,
  serialize
} from '../src/auth-store.js'

/**
 * Pool do Postgres de mentira: entende só os comandos SQL do auth-store (pelo texto) e guarda tudo
 * em memória, com transação (BEGIN/COMMIT/ROLLBACK). `failOn` faz o próximo comando que casar falhar.
 */
class FakePool {
  constructor () {
    this.auth = new Map() // "sessão|categoria|id" → value
    this.kv = new Map()
    this.queries = []
    this.failOn = null
    this.snapshot = null
  }

  key (sid, category, keyId) {
    return `${sid}|${category}|${keyId}`
  }

  async connect () {
    return { query: (text, params) => this.query(text, params), release: () => {} }
  }

  async query (text, params = []) {
    const sql = text.replace(/\s+/g, ' ').trim()
    this.queries.push({ sql, params })
    if (this.failOn && this.failOn.test(sql)) {
      this.failOn = null
      throw Object.assign(new Error('falha simulada do banco'), { code: 'XX000' })
    }
    if (sql === 'BEGIN') {
      this.snapshot = new Map(this.auth)
      return { rows: [] }
    }
    if (sql === 'COMMIT') {
      this.snapshot = null
      return { rows: [] }
    }
    if (sql === 'ROLLBACK') {
      if (this.snapshot) this.auth = this.snapshot
      this.snapshot = null
      return { rows: [] }
    }
    if (sql.startsWith('SELECT value FROM messaging_auth_keys')) {
      const value = this.auth.get(this.key(params[0], params[1], params[2]))
      return { rows: value === undefined ? [] : [{ value }] }
    }
    if (sql.startsWith('INSERT INTO messaging_auth_keys') && sql.includes('VALUES')) {
      assert.equal(typeof params[3], 'string', 'value é TEXT')
      this.auth.set(this.key(params[0], params[1], params[2]), params[3])
      return { rows: [] }
    }
    if (sql.startsWith('SELECT key_id, value FROM messaging_auth_keys')) {
      const rows = []
      for (const keyId of params[2]) {
        const value = this.auth.get(this.key(params[0], params[1], keyId))
        if (value !== undefined) rows.push({ key_id: keyId, value })
      }
      return { rows }
    }
    if (sql.startsWith('INSERT INTO messaging_auth_keys') && sql.includes('unnest')) {
      const [sid, categories, keyIds, values] = params
      assert.equal(categories.length, keyIds.length)
      assert.equal(categories.length, values.length)
      categories.forEach((category, i) => {
        assert.equal(typeof values[i], 'string', 'value é TEXT')
        assert.ok(keyIds[i].length <= 200, 'key_id cabe na coluna')
        this.auth.set(this.key(sid, category, keyIds[i]), values[i])
      })
      return { rows: [] }
    }
    if (sql.startsWith('DELETE FROM messaging_auth_keys') && sql.includes('unnest')) {
      const [sid, categories, keyIds] = params
      categories.forEach((category, i) => this.auth.delete(this.key(sid, category, keyIds[i])))
      return { rows: [] }
    }
    if (sql.startsWith('DELETE FROM messaging_auth_keys') && sql.includes('category <>')) {
      for (const k of [...this.auth.keys()]) {
        const [sid, category] = k.split('|')
        if (sid === params[0] && category !== params[1]) this.auth.delete(k)
      }
      return { rows: [] }
    }
    if (sql.startsWith('DELETE FROM messaging_auth_keys')) {
      for (const k of [...this.auth.keys()]) if (k.startsWith(`${params[0]}|`)) this.auth.delete(k)
      return { rows: [] }
    }
    if (sql.startsWith('SELECT value FROM messaging_connector_kv')) {
      const value = this.kv.get(params[0])
      return { rows: value === undefined ? [] : [{ value }] }
    }
    if (sql.startsWith('INSERT INTO messaging_connector_kv')) {
      this.kv.set(params[0], params[1])
      return { rows: [] }
    }
    throw new Error(`SQL inesperado no teste: ${sql}`)
  }

  keysOf (sid) {
    return [...this.auth.keys()].filter((k) => k.startsWith(`${sid}|`)).map((k) => k.split('|').slice(1).join('|'))
  }
}

const SID = '11111111-2222-3333-4444-555555555555'
const OTHER = '99999999-2222-3333-4444-555555555555'

function bytes (value) {
  return Buffer.from(value).toString('hex')
}

describe('serialização (BufferJSON)', () => {
  it('Buffer e Uint8Array voltam como bytes iguais', () => {
    const original = {
      buf: Buffer.from([1, 2, 3, 250]),
      u8: new Uint8Array([9, 8, 7]),
      nested: { list: [Buffer.from('olá')], n: 5, s: 'texto' }
    }
    const text = serialize(original)
    assert.equal(typeof text, 'string')
    const back = deserialize(text)
    assert.ok(Buffer.isBuffer(back.buf))
    assert.equal(bytes(back.buf), bytes(original.buf))
    assert.equal(bytes(back.u8), bytes(original.u8))
    assert.equal(back.nested.list[0].toString(), 'olá')
    assert.equal(back.nested.n, 5)
    assert.equal(back.nested.s, 'texto')
  })

  it('id de chave grande demais vira hash estável que cabe na coluna', () => {
    assert.equal(safeKeyId('abc'), 'abc')
    const long = 'x'.repeat(300)
    assert.equal(safeKeyId(long), safeKeyId(long))
    assert.ok(safeKeyId(long).length <= 200)
    assert.notEqual(safeKeyId(long), safeKeyId('y'.repeat(300)))
  })
})

describe('AuthStore no Postgres (pool de mentira)', () => {
  it('sessão nova começa com credenciais novas e as guarda em creds/""', async () => {
    const pool = new FakePool()
    const store = new AuthStore(createPgAuthRepository(pool))
    const auth = await store.load(SID)
    assert.ok(auth.state.creds.noiseKey?.private)
    assert.equal(auth.state.creds.registered, false)
    await auth.saveCreds()
    assert.deepEqual(pool.keysOf(SID), [`${CREDS_CATEGORY}|`])
  })

  it('credenciais fazem a volta completa com os bytes intactos', async () => {
    const pool = new FakePool()
    const store = new AuthStore(createPgAuthRepository(pool))
    const first = await store.load(SID)
    first.state.creds.me = { id: '5511999999999:3@s.whatsapp.net', name: 'Fulano' }
    await first.saveCreds()
    first.release()

    const second = await new AuthStore(createPgAuthRepository(pool)).load(SID)
    const a = first.state.creds
    const b = second.state.creds
    assert.equal(bytes(b.noiseKey.private), bytes(a.noiseKey.private))
    assert.equal(bytes(b.noiseKey.public), bytes(a.noiseKey.public))
    assert.equal(bytes(b.signedIdentityKey.private), bytes(a.signedIdentityKey.private))
    assert.equal(bytes(b.signedPreKey.signature), bytes(a.signedPreKey.signature))
    assert.equal(b.registrationId, a.registrationId)
    assert.equal(b.advSecretKey, a.advSecretKey)
    assert.deepEqual(b.me, a.me)
  })

  it('chaves Signal: grava pelo cache, lê do banco e revive app-state-sync-key', async () => {
    const pool = new FakePool()
    const writer = await new AuthStore(createPgAuthRepository(pool)).load(SID, { cache: new TtlCache() })
    const keyData = new Uint8Array([1, 2, 3, 4, 5])
    await writer.state.keys.set({
      'pre-key': { 1: { public: Buffer.from([7, 7]), private: new Uint8Array([8, 8]) } },
      session: { '5511999999999.0': Buffer.from([4, 2]) },
      'app-state-sync-key': {
        AAAAAQ: { keyData, fingerprint: { rawId: 10, currentIndex: 2, deviceIndexes: [0, 1] }, timestamp: 1700000000 }
      }
    })

    // Leitor novo, com cache vazio: tudo vem do "banco".
    const reader = await new AuthStore(createPgAuthRepository(pool)).load(SID, { cache: new TtlCache() })
    const preKeys = await reader.state.keys.get('pre-key', ['1', '2'])
    assert.deepEqual(Object.keys(preKeys), ['1'])
    assert.equal(bytes(preKeys['1'].public), '0707')
    assert.equal(bytes(preKeys['1'].private), '0808')

    const sessions = await reader.state.keys.get('session', ['5511999999999.0'])
    assert.equal(bytes(sessions['5511999999999.0']), '0402')

    const appKeys = await reader.state.keys.get('app-state-sync-key', ['AAAAAQ'])
    const revived = appKeys.AAAAAQ
    assert.ok(revived instanceof proto.Message.AppStateSyncKeyData, 'é o objeto do protobuf')
    assert.equal(bytes(revived.keyData), bytes(keyData))
    assert.equal(revived.fingerprint.rawId, 10)
    assert.equal(Number(revived.timestamp), 1700000000)
  })

  it('valor null apaga a chave; ids gigantes funcionam pelo id original', async () => {
    const pool = new FakePool()
    const auth = await new AuthStore(createPgAuthRepository(pool)).load(SID)
    const longId = 'z'.repeat(260)
    await auth.rawKeys.set({ 'sender-key': { [longId]: Buffer.from([1]) }, 'pre-key': { 5: { public: Buffer.from([5]) } } })
    assert.equal(pool.keysOf(SID).length, 2)
    const got = await auth.rawKeys.get('sender-key', [longId])
    assert.equal(bytes(got[longId]), '01')

    await auth.rawKeys.set({ 'pre-key': { 5: null } })
    assert.deepEqual(await auth.rawKeys.get('pre-key', ['5']), {})
    assert.equal(pool.keysOf(SID).length, 1)
  })

  it('gravação de chaves é uma transação só: se falhar, nada fica pela metade', async () => {
    const pool = new FakePool()
    const auth = await new AuthStore(createPgAuthRepository(pool)).load(SID)
    await auth.rawKeys.set({ 'pre-key': { 1: { public: Buffer.from([1]) } } })
    pool.failOn = /^DELETE FROM messaging_auth_keys.*unnest/
    await assert.rejects(auth.rawKeys.set({ 'pre-key': { 2: { public: Buffer.from([2]) }, 1: null } }))
    assert.ok(pool.queries.some((q) => q.sql === 'ROLLBACK'))
    assert.deepEqual(pool.keysOf(SID).sort(), ['pre-key|1'])
  })

  it('uma falha ao salvar as credenciais não trava as próximas gravações', async () => {
    const pool = new FakePool()
    const auth = await new AuthStore(createPgAuthRepository(pool)).load(SID)
    pool.failOn = /^INSERT INTO messaging_auth_keys.*VALUES/
    await assert.rejects(auth.saveCreds())
    auth.state.creds.me = { id: '5511888888888@s.whatsapp.net' }
    await auth.saveCreds()
    const saved = deserialize(pool.auth.get(`${SID}|creds|`))
    assert.equal(saved.me.id, '5511888888888@s.whatsapp.net')
  })

  it('logout (removeAll) apaga só a sessão e descarta gravações atrasadas do socket antigo', async () => {
    const pool = new FakePool()
    const store = new AuthStore(createPgAuthRepository(pool))
    const auth = await store.load(SID)
    await auth.saveCreds()
    await auth.rawKeys.set({ session: { a: Buffer.from([1]) } })
    const other = await store.load(OTHER)
    await other.saveCreds()

    await store.removeAll(SID)
    assert.deepEqual(pool.keysOf(SID), [])
    assert.equal(auth.revoked, true)
    // O socket antigo ainda tenta gravar: nada volta para o banco.
    await auth.saveCreds()
    await auth.rawKeys.set({ session: { b: Buffer.from([2]) } })
    assert.deepEqual(pool.keysOf(SID), [])
    assert.deepEqual(pool.keysOf(OTHER), ['creds|'])
  })

  it('clear() apaga as chaves mas mantém as credenciais', async () => {
    const pool = new FakePool()
    const auth = await new AuthStore(createPgAuthRepository(pool)).load(SID)
    await auth.saveCreds()
    await auth.rawKeys.set({ session: { a: Buffer.from([1]) } })
    await auth.rawKeys.clear()
    assert.deepEqual(pool.keysOf(SID), ['creds|'])
  })
})

describe('messaging_connector_kv e cache', () => {
  it('guarda e lê valores soltos (wa_version)', async () => {
    const pool = new FakePool()
    const kv = createPgKvRepository(pool)
    assert.equal(await kv.get('wa_version'), null)
    await kv.set('wa_version', '[2,3000,1]')
    await kv.set('wa_version', '[2,3000,2]')
    assert.equal(await kv.get('wa_version'), '[2,3000,2]')
  })

  it('TtlCache respeita validade e tamanho máximo', () => {
    let now = 0
    const cache = new TtlCache({ ttlMs: 100, max: 2, now: () => now })
    cache.set('a', 1)
    cache.set('b', 2)
    cache.set('c', 3)
    assert.equal(cache.get('a'), undefined, 'o mais antigo saiu')
    assert.equal(cache.get('b'), 2)
    now = 200
    assert.equal(cache.get('b'), undefined, 'expirou')
    cache.set('d', 4)
    cache.flushAll()
    assert.equal(cache.size, 0)
  })
})
