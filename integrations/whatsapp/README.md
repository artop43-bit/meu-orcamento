# Conector do WhatsApp (Mensageria)

Serviço Node 24 que liga a Mensageria do Hub ao WhatsApp de cada pessoa, usando a biblioteca
[Baileys](https://github.com/WhiskeySockets/Baileys) (`7.0.0-rc14`, versão fixa). Ele faz o papel do
"WhatsApp Web": a pessoa lê um QR Code no celular e, a partir daí, as conversas individuais aparecem
no Hub e as respostas escritas no Hub saem pelo número dela.

Não tem custo e não usa serviço pago: fala direto com os servidores do WhatsApp, como o WhatsApp Web.

```
[Navegador] → [API FastAPI :8000] ⇄ (X-Connector-Token) ⇄ [este conector :3100] ⇄ WhatsApp
                      │                                            │
                      └──────────────── Postgres ──────────────────┘
          (tabelas messaging_*)          (só messaging_auth_keys e messaging_connector_kv)
```

- **Credenciais do WhatsApp** de cada número ficam no Postgres (`messaging_auth_keys`), nunca em
  arquivos. O `useMultiFileAuthState` da Baileys não é para produção.
- **Todo o resto** (sessões, conversas, mensagens, fila de envio) passa pela API. O conector não
  lê nem grava as outras tabelas.
- A porta 3100 fica **só na rede interna do Docker**; não é aberta para fora.

## Variáveis de ambiente

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `CONNECTOR_TOKEN` | — | Segredo compartilhado com a API (o mesmo `MESSAGING_CONNECTOR_TOKEN`). Se estiver vazio, o conector usa `MESSAGING_CONNECTOR_TOKEN`. |
| `HUB_API_URL` | — | Endereço interno da API, ex.: `http://api:8000`. |
| `DATABASE_URL` | — | Postgres no formato `postgres://usuario:senha@host:5432/banco`. |
| `PORT` | `3100` | Porta da API interna. |
| `WORKERS` | `2` | Quantos processos filhos cuidam das sessões. |
| `WORKER_MAX_OLD_SPACE_MB` | `3072` | Teto de memória (heap) de cada processo filho. |
| `MAX_CONCURRENT_PAIRINGS` | `3` | Pareamentos/sincronizações iniciais ao mesmo tempo, por processo. |
| `LOG_LEVEL` | `warn` | Nível do log. A Baileys nunca loga abaixo de `warn` (em debug ela despejaria o conteúdo das mensagens). |

**Sem configuração** (falta o token, a URL da API ou a do banco) o conector sobe mesmo assim, avisa no
log o que está faltando e fica só respondendo `GET /health` com `200` (`"configured": false`). Assim o
`docker compose up --wait` não trava por causa dele. (Do lado da API, sem o token a Mensageria mostra
na tela que a conexão com o WhatsApp não está disponível.)

## Como conversa com a API

**A API chama o conector** (cabeçalho `X-Connector-Token`, comparado em tempo constante):

| Rota | Resposta | O que faz |
| --- | --- | --- |
| `POST /sessions/{id}/start` | `202` | Inicia ou reinicia a sessão (gera QR novo se ainda não pareou). |
| `POST /sessions/{id}/stop` `{"logout": bool}` | `202` | `true`: desconecta o aparelho no WhatsApp e apaga as credenciais. `false`: só fecha. |
| `POST /sessions/{id}/flush` | `202` | Busca a fila de envio dessa sessão agora. |
| `POST /sessions/{id}/read` `{"remote_jid", "external_ids"}` | `202` | Envia a confirmação de leitura. |
| `GET /health` | `200` | `{ ok, workers, sessions, rss_mb }`, **sem token** (healthcheck). `503` se algum processo filho estiver fora do ar. |
| `GET /stats` | `200` | Detalhes por processo (memória, sessões por status, fila de eventos). |

Sem token válido: `401`. Rota desconhecida: `404`.

**O conector chama a API** (prefixo `/api/messaging/connector`, mesmo cabeçalho):

- `GET /sessions` ao ligar: sessões com `wanted=true`, restauradas uma a uma, a cada ~300 ms,
  tentando de novo (com espera crescente) até a API responder.
- `GET /outbox?session_ids=...` a cada 15 s por processo (uma chamada com as sessões prontas
  daquele processo), além de cada `flush`. Cada item enviado vira um evento `ack`.
- `POST /events` com os eventos em lote (`status`, `message`, `receipt`, `ack`, `read_self`,
  `contact`): junta por até 500 ms ou 100 eventos; se a API falhar, reenvia com espera crescente.
  A fila em memória é limitada (os eventos mais antigos saem primeiro se ela encher).

## Como funciona por dentro

- `src/index.js` — supervisor: sobe a API interna e os `WORKERS` processos filhos (cada um com
  `--max-old-space-size`). Cada sessão vai sempre para o processo `hash(session_id) % WORKERS`
  (FNV-1a, estável). Processo que cai é religado com espera crescente e recebe de novo o `start`
  das suas sessões. No `SIGTERM`, fecha os sockets **sem logout**.
- `src/worker.js` — processo filho: comandos de cada sessão em ordem, varredura da fila, envio
  (com mensagem citada), confirmações.
- `src/session.js` — uma sessão da Baileys: QR, reconexão, histórico, conversão dos eventos.
  - Versão do WhatsApp Web: `fetchLatestWaWebVersion()` a cada conexão; se falhar, a última que
    funcionou (`messaging_connector_kv`, chave `wa_version`); só então a padrão da biblioteca.
  - `Browsers.macOS('Chrome')`, `syncFullHistory: false`, `markOnlineOnConnect: false`.
  - Correção da queda a cada ~50 min: confirma (`ack`) os avisos `status` que o WhatsApp manda.
  - Quedas: 515 reconecta na hora; 401 (saiu pelo celular) apaga as credenciais e manda
    `wanted:false`; 440 (conectado em outro lugar) para com erro; QR esgotado para e manda
    `wanted:false`; o resto reconecta com espera de 2 s até 60 s.
  - Histórico só no primeiro pareamento: até 50 conversas individuais mais recentes e até 20
    mensagens de cada (`history: true`, não contam como não lidas).
- `src/auth-store.js` — credenciais no Postgres (`BufferJSON`, `makeCacheableSignalKeyStore` com
  cache próprio por sessão, `app-state-sync-key` revivido pelo protobuf).
- `src/mapping.js` — funções puras: mensagens, recibos, contatos, política de desconexão.
- `src/api-client.js` — chamadas à API, lotes, reenvio e tempo limite.

## Limites (de propósito)

- **Só conversas individuais.** Grupos, listas de transmissão, status (stories) e canais são
  ignorados já na Baileys (`shouldIgnoreJid`).
- **Só texto.** Mídia não é baixada: aparece como "📷 Foto", "🎤 Áudio", "🎬 Vídeo",
  "📄 Documento · nome", "Figurinha" ou "Mensagem não suportada" (com a legenda, quando houver).
  Pelo Hub só se envia texto.
- Números ocultos pelo WhatsApp (só LID) aparecem sem telefone até o WhatsApp informar o número.

## Riscos

- **Não é oficial.** A Baileys imita o WhatsApp Web; a Meta não apoia esse uso. Uma mudança do
  lado do WhatsApp pode parar o conector até a biblioteca ser atualizada.
- **Risco de bloqueio do número.** Uso parecido com robô (muitas mensagens para quem não tem o
  número salvo, disparos em massa) pode fazer o WhatsApp banir o número. A Mensageria é para
  conversa normal, não para disparo.
- **Chave de acesso (passkey):** há um problema conhecido em aberto na Baileys (issue #2672)
  envolvendo contas com passkey. Se o pareamento falhar para alguém com passkey ativada, comece
  a investigação por ali.
- A versão da Baileys é release candidate (`7.0.0-rc14`) e fica fixa; atualizar exige testar o
  pareamento de verdade antes.

## Capacidade

- Cada número conectado usa de **30 a 80 MB** de memória (mais durante o pareamento e a primeira
  sincronização, por isso o limite de `MAX_CONCURRENT_PAIRINGS`).
- Em produção o contêiner tem teto de **8 GB** (`mem_limit`), com **2 processos** de até 3 GB de
  heap cada. O `GET /health` mostra o total (`rss_mb`) e o `GET /stats` o detalhe por processo.
- A API limita quantos números podem ficar conectados (`MESSAGING_MAX_SESSIONS`, padrão 100).

## Rodar e testar

```bash
npm ci
npm test                 # node --test (sem rede, sem banco)
npm start                # precisa das variáveis acima
```

A imagem Docker (`Dockerfile`) usa `node:24-bookworm-slim`, roda sem root e tem `HEALTHCHECK` no
`/health`.
