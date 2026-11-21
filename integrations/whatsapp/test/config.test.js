import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { baileysLevel, loadConfig } from '../src/config.js'
import { Gate } from '../src/gate.js'

const FULL = { CONNECTOR_TOKEN: 't', HUB_API_URL: 'http://backend:8000/', DATABASE_URL: 'postgres://u:p@db:5432/x' }

describe('configuração', () => {
  it('valores padrão do contrato', () => {
    const config = loadConfig(FULL)
    assert.equal(config.port, 3100)
    assert.equal(config.workers, 2)
    assert.equal(config.workerMaxOldSpaceMb, 3072)
    assert.equal(config.maxConcurrentPairings, 3)
    assert.equal(config.logLevel, 'warn')
    assert.equal(config.apiUrl, 'http://backend:8000')
    assert.equal(config.configured, true)
  })

  it('aceita MESSAGING_CONNECTOR_TOKEN quando CONNECTOR_TOKEN está vazio', () => {
    const config = loadConfig({ ...FULL, CONNECTOR_TOKEN: '', MESSAGING_CONNECTOR_TOKEN: 'da-api' })
    assert.equal(config.token, 'da-api')
    assert.equal(config.configured, true)
    assert.equal(loadConfig({ ...FULL, MESSAGING_CONNECTOR_TOKEN: 'outro' }).token, 't', 'CONNECTOR_TOKEN tem preferência')
  })

  it('sem token nenhum: não configurado (o serviço sobe só com /health)', () => {
    const config = loadConfig({ ...FULL, CONNECTOR_TOKEN: '', MESSAGING_CONNECTOR_TOKEN: '  ' })
    assert.equal(config.configured, false)
    assert.equal(config.missing.length, 1)
    assert.match(config.missing[0], /CONNECTOR_TOKEN/)
    assert.equal(loadConfig({}).missing.length, 3)
  })

  it('números fora do intervalo voltam para o limite', () => {
    const config = loadConfig({ ...FULL, PORT: '99999', WORKERS: '0', MAX_CONCURRENT_PAIRINGS: 'abc', LOG_LEVEL: 'DEBUG' })
    assert.equal(config.port, 65535)
    assert.equal(config.workers, 1)
    assert.equal(config.maxConcurrentPairings, 3)
    assert.equal(config.logLevel, 'debug')
  })

  it('a Baileys nunca loga em debug/trace (despejaria o conteúdo das mensagens)', () => {
    assert.equal(baileysLevel('debug'), 'warn')
    assert.equal(baileysLevel('trace'), 'warn')
    assert.equal(baileysLevel('info'), 'warn')
    assert.equal(baileysLevel('error'), 'error')
    assert.equal(baileysLevel('silent'), 'silent')
  })
})

describe('Gate (vagas de pareamento)', () => {
  it('libera no máximo `limit` de cada vez, na ordem de chegada', async () => {
    const gate = new Gate(2)
    const order = []
    const r1 = await gate.acquire()
    const r2 = await gate.acquire()
    const third = gate.acquire().then((release) => { order.push('c'); return release })
    const fourth = gate.acquire().then((release) => { order.push('d'); return release })
    await new Promise((resolve) => setImmediate(resolve))
    assert.equal(gate.active, 2)
    assert.equal(gate.pending, 2)
    r1()
    r1() // liberar duas vezes não abre vaga extra
    const r3 = await third
    assert.equal(gate.active, 2)
    assert.deepEqual(order, ['c'])
    r2()
    const r4 = await fourth
    assert.deepEqual(order, ['c', 'd'])
    r3()
    r4()
    assert.equal(gate.active, 0)
  })
})
