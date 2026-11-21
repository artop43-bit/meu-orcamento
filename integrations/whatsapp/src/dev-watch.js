/**
 * Reinicia o conector (`src/index.js`) em desenvolvimento sempre que algum arquivo de `src/`
 * muda. Usa checagem periódica (stat) em vez de inotify, porque no Docker Desktop para Windows
 * o `--watch-path` nativo do Node não percebe edições feitas no PC.
 */
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC_DIR = path.dirname(fileURLToPath(import.meta.url));
const ENTRY = path.join(SRC_DIR, "index.js");
const POLL_MS = 1500;

function snapshotDir(dir) {
  const entries = [];
  for (const item of fs.readdirSync(dir, { withFileTypes: true })) {
    if (item.name === "dev-watch.js") continue;
    const full = path.join(dir, item.name);
    if (item.isDirectory()) {
      entries.push(...snapshotDir(full));
    } else if (item.isFile() && item.name.endsWith(".js")) {
      const st = fs.statSync(full);
      entries.push(`${full}:${st.size}:${Math.trunc(st.mtimeMs)}`);
    }
  }
  entries.sort();
  return entries.join("|");
}

let child = null;
let restarting = false;
let shuttingDown = false;
let lastSig = snapshotDir(SRC_DIR);

function startChild() {
  child = spawn(process.execPath, [ENTRY], { stdio: "inherit", env: process.env });
  child.on("exit", (code, signal) => {
    child = null;
    if (shuttingDown) process.exit(code ?? 0);
    if (restarting) {
      restarting = false;
      startChild();
      return;
    }
    if (code && code !== 0 && signal !== "SIGTERM") {
      console.error(`[dev-watch] conector saiu (código ${code}); aguardando próxima edição.`);
    }
  });
}

function restartChild() {
  if (!child) {
    startChild();
    return;
  }
  restarting = true;
  child.kill("SIGTERM");
}

const timer = setInterval(() => {
  if (shuttingDown) return;
  try {
    const nextSig = snapshotDir(SRC_DIR);
    if (nextSig !== lastSig) {
      lastSig = nextSig;
      console.log("[dev-watch] alteração em src/ detectada — reiniciando conector…");
      restartChild();
    }
  } catch {
    // Arquivo salvo no meio da leitura: tenta novamente no próximo ciclo.
  }
}, POLL_MS);

function shutdown() {
  shuttingDown = true;
  clearInterval(timer);
  if (child) child.kill("SIGTERM");
  else process.exit(0);
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

startChild();
