# Conector do WhatsApp (Baileys) da Mensageria.
# Funciona em linux/arm64 e linux/amd64: as dependências são JavaScript e WASM, sem compilação nativa.
# Node 24: evita o vazamento de memória do AsyncLocalStorage que aparece nas versões antigas.
FROM node:24-bookworm-slim

ENV NODE_ENV=production \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_AUDIT=false

WORKDIR /app

# Dependências primeiro (sem as de desenvolvimento), para aproveitar o cache de camadas.
# O .npmrc vai junto: o package-lock.json foi gerado com legacy-peer-deps.
COPY package.json package-lock.json .npmrc ./
RUN npm ci --omit=dev && npm cache clean --force

COPY src ./src

# Roda sem privilégios de root (o usuário "node" já vem na imagem oficial).
USER node

EXPOSE 3100

# /health não pede token. Sem configuração ele continua respondendo 200 (o resto do sistema sobe).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["node", "-e", "fetch('http://localhost:' + (process.env.PORT || 3100) + '/health', { signal: AbortSignal.timeout(4000) }).then((r) => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]

CMD ["node", "src/index.js"]
