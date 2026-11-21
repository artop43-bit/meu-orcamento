// Credenciais do WhatsApp de cada sessão guardadas no Postgres (tabela messaging_auth_keys),
// no lugar do useMultiFileAuthState (que a própria Baileys diz não ser para produção).
// Também guarda valores soltos do conector (tabela messaging_connector_kv).

import { createHash } from 'node:crypto'
import { BufferJSON, initAuthCreds, makeCacheableSignalKeyStore, proto } from 'baileys'

export const CREDS_CATEGORY = 'creds'
const MAX_KEY_ID = 200
const MAX_CATEGORY = 48
const CHUNK = 500

export function serialize (value) {
  return JSON.stringify(value, BufferJSON.replacer)
}

export function deserialize (text) {
  return JSON.parse(text, BufferJSON.reviver)
}

/** A coluna key_id tem 200 caracteres: ids maiores viram um hash estável. */
export function safeKeyId (id) {
  const text = String(id)
  if (text.length <= MAX_KEY_ID) return text
  return 'sha256:' + createHash('sha256').update(text).digest('hex')
}

function chunks (list, size = CHUNK) {
  const out = []
  for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size))
  return out
}

/** Acesso ao banco (SQL puro). Separado da lógica para poder testar com um pool falso. */
export function createPgAuthRepository (pool) {
  return {
    async readCreds (sessionId) {
      const { rows } = await pool.query(
        'SELECT value FROM messaging_auth_keys WHERE session_id = $1::uuid AND category = $2 AND key_id = $3',
        [sessionId, CREDS_CATEGORY, '']
      )
      return rows[0]?.value ?? null
    },

    async writeCreds (sessionId, value) {
      await pool.query(
        `INSERT INTO messaging_auth_keys (session_id, category, key_id, value, updated_at)
         VALUES ($1::uuid, $2, $3, $4, now())
         ON CONFLICT (session_id, category, key_id)
         DO UPDATE SET value = EXCLUDED.value, updated_at = now()`,
        [sessionId, CREDS_CATEGORY, '', value]
      )
    },

    async readKeys (sessionId, category, keyIds) {
      const found = new Map()
      for (const part of chunks(keyIds)) {
        const { rows } = await pool.query(
          `SELECT key_id, value FROM messaging_auth_keys
           WHERE session_id = $1::uuid AND category = $2 AND key_id = ANY($3::text[])`,
          [sessionId, category, part]
        )
        for (const row of rows) found.set(row.key_id, row.value)
      }
      return found
    },

    /** Grava e apaga chaves numa transação só (ou vai tudo, ou nada). */
    async writeKeys (sessionId, upserts, deletes) {
      if (!upserts.length && !deletes.length) return
      const client = await pool.connect()
      try {
        await client.query('BEGIN')
        for (const part of chunks(upserts)) {
          await client.query(
            `INSERT INTO messaging_auth_keys (session_id, category, key_id, value, updated_at)
             SELECT $1::uuid, t.category, t.key_id, t.value, now()
             FROM unnest($2::text[], $3::text[], $4::text[]) AS t(category, key_id, value)
             ON CONFLICT (session_id, category, key_id)
             DO UPDATE SET value = EXCLUDED.value, updated_at = now()`,
            [sessionId, part.map((r) => r.category), part.map((r) => r.keyId), part.map((r) => r.value)]
          )
        }
        for (const part of chunks(deletes)) {
          await client.query(
            `DELETE FROM messaging_auth_keys
             WHERE session_id = $1::uuid
               AND (category, key_id) IN (SELECT * FROM unnest($2::text[], $3::text[]))`,
            [sessionId, part.map((r) => r.category), part.map((r) => r.keyId)]
          )
        }
        await client.query('COMMIT')
      } catch (err) {
        await client.query('ROLLBACK').catch(() => {})
        throw err
      } finally {
        client.release()
      }
    },

    async deleteKeys (sessionId) {
      await pool.query(
        'DELETE FROM messaging_auth_keys WHERE session_id = $1::uuid AND category <> $2',
        [sessionId, CREDS_CATEGORY]
      )
    },

    async deleteAll (sessionId) {
      await pool.query('DELETE FROM messaging_auth_keys WHERE session_id = $1::uuid', [sessionId])
    }
  }
}

export function createPgKvRepository (pool) {
  return {
    async get (key) {
      const { rows } = await pool.query('SELECT value FROM messaging_connector_kv WHERE key = $1', [key])
      return rows[0]?.value ?? null
    },
    async set (key, value) {
      await pool.query(
        `INSERT INTO messaging_connector_kv (key, value, updated_at) VALUES ($1, $2, now())
         ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()`,
        [key, value]
      )
    }
  }
}

/** Cache pequeno com validade e tamanho máximo (no lugar do NodeCache, para limitar a memória). */
export class TtlCache {
  constructor ({ ttlMs = 5 * 60 * 1000, max = 2000, now = Date.now } = {}) {
    this.ttlMs = ttlMs
    this.max = max
    this.now = now
    this.map = new Map()
  }

  get (key) {
    const item = this.map.get(key)
    if (!item) return undefined
    if (item.expires <= this.now()) {
      this.map.delete(key)
      return undefined
    }
    return item.value
  }

  set (key, value) {
    this.map.delete(key)
    this.map.set(key, { value, expires: this.now() + this.ttlMs })
    while (this.map.size > this.max) this.map.delete(this.map.keys().next().value)
    return true
  }

  del (key) {
    this.map.delete(key)
  }

  flushAll () {
    this.map.clear()
  }

  get size () {
    return this.map.size
  }
}

function reviveKey (category, value) {
  if (category === 'app-state-sync-key' && value) {
    return proto.Message.AppStateSyncKeyData.fromObject(value)
  }
  return value
}

/**
 * Estado de autenticação da Baileys por sessão, guardado pelo repositório.
 * Depois de `removeAll`, as gravações atrasadas de um socket antigo são descartadas
 * (senão chaves velhas voltariam para o banco depois do logout).
 */
export class AuthStore {
  constructor (repo, { logger } = {}) {
    this.repo = repo
    this.logger = logger
    this.handles = new Map()
  }

  async load (sessionId, { cache } = {}) {
    const handle = { revoked: false, pending: new Set() }
    let set = this.handles.get(sessionId)
    if (!set) {
      set = new Set()
      this.handles.set(sessionId, set)
    }
    set.add(handle)

    const track = (promise) => {
      handle.pending.add(promise)
      promise.finally(() => handle.pending.delete(promise)).catch(() => {})
      return promise
    }

    let saved
    try {
      saved = await this.repo.readCreds(sessionId)
    } catch (err) {
      set.delete(handle)
      if (!set.size && this.handles.get(sessionId) === set) this.handles.delete(sessionId)
      throw err
    }
    const creds = saved ? deserialize(saved) : initAuthCreds()
    const repo = this.repo

    const keys = {
      async get (category, ids) {
        const data = {}
        if (!ids?.length) return data
        const byStored = new Map(ids.map((id) => [safeKeyId(id), id]))
        const found = await repo.readKeys(sessionId, category, [...byStored.keys()])
        for (const [storedId, text] of found) {
          const id = byStored.get(storedId)
          if (id === undefined) continue
          data[id] = reviveKey(category, deserialize(text))
        }
        return data
      },
      async set (data) {
        if (handle.revoked) return
        const upserts = new Map()
        const deletes = new Map()
        for (const category of Object.keys(data || {})) {
          if (category.length > MAX_CATEGORY) continue
          for (const id of Object.keys(data[category] || {})) {
            const keyId = safeKeyId(id)
            const mapKey = `${category}\u0000${keyId}`
            const value = data[category][id]
            if (value === null || value === undefined) {
              upserts.delete(mapKey)
              deletes.set(mapKey, { category, keyId })
            } else {
              deletes.delete(mapKey)
              upserts.set(mapKey, { category, keyId, value: serialize(value) })
            }
          }
        }
        await track(repo.writeKeys(sessionId, [...upserts.values()], [...deletes.values()]))
      },
      async clear () {
        if (handle.revoked) return
        await track(repo.deleteKeys(sessionId))
      }
    }

    // Gravações das credenciais em ordem. Uma falha não trava as próximas (a fila segue).
    let chain = Promise.resolve()
    const saveCreds = () => {
      const result = chain.then(async () => {
        if (handle.revoked) return
        await track(repo.writeCreds(sessionId, serialize(creds)))
      })
      chain = result.catch(() => {})
      return result
    }

    const release = () => {
      const current = this.handles.get(sessionId)
      if (!current) return
      current.delete(handle)
      if (!current.size) this.handles.delete(sessionId)
    }

    return {
      state: { creds, keys: makeCacheableSignalKeyStore(keys, this.logger, cache) },
      rawKeys: keys,
      saveCreds,
      release,
      get revoked () {
        return handle.revoked
      }
    }
  }

  /** Apaga tudo da sessão (logout): para as gravações em andamento e limpa o banco. */
  async removeAll (sessionId) {
    const set = this.handles.get(sessionId)
    const pending = []
    if (set) {
      for (const handle of set) {
        handle.revoked = true
        pending.push(...handle.pending)
      }
      this.handles.delete(sessionId)
    }
    await Promise.allSettled(pending)
    await this.repo.deleteAll(sessionId)
  }
}
