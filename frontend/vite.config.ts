import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Em desenvolvimento, /api é repassado para a API.
// Dentro do Docker o alvo é http://backend:8000 (definido no docker-compose).
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: {
        // Bibliotecas num arquivo próprio (v1.4.4): mudam raramente e ficam guardadas no
        // aparelho entre as versões; a cada deploy só o código do app é baixado de novo.
        codeSplitting: {
          groups: [{ name: "vendor", test: /node_modules[\/](react|react-dom|scheduler|react-router|@tanstack)[\/]/ }],
        },
      },
    },
  },
  server: {
    host: true,
    port: 5173,
    // Endereços do GitHub Codespaces (o Vite recusa hosts desconhecidos por segurança).
    allowedHosts: [".app.github.dev", ".githubpreview.dev"],
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
    },
  },
});
