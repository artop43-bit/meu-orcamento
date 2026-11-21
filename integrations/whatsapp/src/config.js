// Configuração por variáveis de ambiente (ver README.md).

import pino from 'pino'

function intFrom (value, fallback, { min = 1, max = Number.MAX_SAFE_INTEGER } = {}) {
  const n = Number.parseInt(String(value ?? ''), 10)
  if (!Number.isFinite(n)) return fallback
  return Math.min(max, Math.max(min, n))
}

const LEVELS = new Set(['fatal', 'error', 'warn', 'info', 'debug', 'trace', 'silent'])

export function loadConfig (env = process.env) {
  const logLevel = LEVELS.has(String(env.LOG_LEVEL || '').toLowerCase())
    ? String(env.LOG_LEVEL).toLowerCase()
    : 'warn'
  const config = {
    port: intFrom(env.PORT, 3100, { min: 1, max: 65535 }),
    // Aceita também o nome usado pela API (o mesmo segredo dos dois lados).
    token: String(env.CONNECTOR_TOKEN || env.MESSAGING_CONNECTOR_TOKEN || '').trim(),
    apiUrl: String(env.HUB_API_URL || '').replace(/\/+$/, ''),
    databaseUrl: String(env.DATABASE_URL || ''),
    workers: intFrom(env.WORKERS, 2, { min: 1, max: 64 }),
    workerMaxOldSpaceMb: intFrom(env.WORKER_MAX_OLD_SPACE_MB, 3072, { min: 128 }),
    maxConcurrentPairings: intFrom(env.MAX_CONCURRENT_PAIRINGS, 3, { min: 1, max: 100 }),
    logLevel
  }
  const missing = []
  if (!config.token) missing.push('CONNECTOR_TOKEN (ou MESSAGING_CONNECTOR_TOKEN)')
  if (!config.apiUrl) missing.push('HUB_API_URL')
  if (!config.databaseUrl) missing.push('DATABASE_URL')
  config.missing = missing
  config.configured = missing.length === 0
  return config
}

/** Nível do log da Baileys: nunca debug/trace (eles despejam o conteúdo das mensagens). */
export function baileysLevel (level) {
  return ['error', 'fatal', 'silent'].includes(level) ? level : 'warn'
}

export function createLogger (level, bindings = {}) {
  return pino({ level, base: { ...bindings } })
}
