# Caddy servindo o frontend compilado e repassando /api para a API.
# Contexto de build: raiz do repositório (ver docker-compose.prod.yml).

# O resultado do build (HTML/JS/CSS) não depende do processador: compila na arquitetura
# da máquina de build, mesmo quando a imagem final é ARM (mais rápido sob emulação).
FROM --platform=$BUILDPLATFORM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM caddy:2.11-alpine
COPY deploy/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=web /web/dist /srv
