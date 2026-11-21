// Ponto de entrada do conector: supervisor + API HTTP interna + processos filhos.

import { fork } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { ApiClient } from './api-client.js'
import { createLogger, loadConfig } from './config.js'
import { createHttpServer } from './http-server.js'
import { Supervisor } from './supervisor.js'

const workerPath = fileURLToPath(new URL('./worker.js', import.meta.url))

async function main () {
  const config = loadConfig()
  const logger = createLogger(config.logLevel, { proc: 'supervisor' })

  let supervisor = null
  if (config.configured) {
    const api = new ApiClient({ baseUrl: config.apiUrl, token: config.token, logger })
    supervisor = new Supervisor({
      workers: config.workers,
      api,
      logger,
      fork: (index) => fork(workerPath, [], {
        execArgv: [`--max-old-space-size=${config.workerMaxOldSpaceMb}`],
        env: { ...process.env, WORKER_INDEX: String(index) },
        serialization: 'json'
      })
    })
  } else {
    // Sem configuração o conector fica no ar só respondendo /health (sem tentar nada em loop),
    // para não derrubar o resto do docker compose.
    logger.warn(
      { missing: config.missing },
      `Conector do WhatsApp sem configuração (falta: ${config.missing.join(', ')}). ` +
        'Ele fica no ar só respondendo /health e nenhuma sessão será aberta.'
    )
  }

  const server = createHttpServer({ token: config.token, supervisor, logger, configured: config.configured })
  server.keepAliveTimeout = 5000
  // Sem host fixo: escuta em IPv4 e IPv6 quando houver (o healthcheck usa "localhost",
  // que pode virar ::1 ou 127.0.0.1 dependendo do contêiner).
  await new Promise((resolve) => server.listen(config.port, resolve))
  logger.info({ port: config.port, workers: config.workers }, 'Conector do WhatsApp no ar')

  const restoring = new AbortController()
  if (supervisor) {
    supervisor.start()
    supervisor.restore({ signal: restoring.signal }).catch((err) => {
      logger.error({ err: err?.message }, 'Não foi possível restaurar as sessões')
    })
  }

  let stopping = false
  const shutdown = async (signal) => {
    if (stopping) return
    stopping = true
    logger.warn({ signal }, 'Desligando o conector (sem logout das sessões)')
    restoring.abort()
    server.close()
    // Menos que os 10 s que o Docker espera antes de matar o contêiner.
    if (supervisor) await supervisor.shutdown(9000)
    process.exit(0)
  }
  process.on('SIGTERM', () => void shutdown('SIGTERM'))
  process.on('SIGINT', () => void shutdown('SIGINT'))
  process.on('unhandledRejection', (err) => logger.error({ err: err?.message || String(err) }, 'Promessa rejeitada sem tratamento'))
}

main().catch((err) => {
  console.error('Falha ao iniciar o conector do WhatsApp:', err)
  process.exit(1)
})
