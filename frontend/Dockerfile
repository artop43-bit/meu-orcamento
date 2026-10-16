# Imagem de desenvolvimento (Vite com hot reload).
# A imagem de produção (build estático servido pelo Caddy) entra na fase de deploy.
FROM node:22-alpine

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install

COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]
