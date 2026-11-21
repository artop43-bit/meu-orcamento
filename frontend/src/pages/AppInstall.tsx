import { useState } from "react";
import { Download, MonitorSmartphone, Smartphone } from "lucide-react";

import { PushNotificationsSection } from "../components/NotificationBlocks";
import { Alert, Button, PageHeader } from "../components/ui";
import { promptInstall, useInstallPrompt } from "../lib/install";

export const APK_URL = "/downloads/meu-orcamento.apk";

function isAndroid() {
  return /Android/i.test(navigator.userAgent);
}

function isIos() {
  return /iPhone|iPad|iPod/i.test(navigator.userAgent);
}

function installed() {
  return window.matchMedia?.("(display-mode: standalone)").matches || document.referrer.startsWith("android-app://");
}

/** Hub › App e notificações: instalar no Android (APK), no iPhone e no computador e ativar push. */
export default function AppInstallPage() {
  const prompt = useInstallPrompt();
  const [done, setDone] = useState(installed());

  async function install() {
    if (await promptInstall()) setDone(true);
  }

  return (
    <>
      <PageHeader title="App e notificações" subtitle="Instale o app no celular ou no computador e ative os avisos neste aparelho." />
      <div className="stack" style={{ gap: 20 }}>
        {done && <Alert tone="success">Você está usando o app instalado.</Alert>}
        <section className="card stack">
          <h2>
            <Smartphone size={18} aria-hidden /> Android
          </h2>
          <p className="muted" style={{ margin: 0 }}>
            O app para Android é distribuído aqui mesmo, sem loja. Ele abre em tela cheia, recebe notificações e se atualiza sozinho: as telas novas
            chegam sem precisar instalar de novo.
          </p>
          <div>
            <a className="btn btn--primary" href={APK_URL} download>
              <Download size={16} aria-hidden /> Baixar o app (APK)
            </a>
          </div>
          <ol className="install-steps">
            <li>Toque em “Baixar o app” e abra o arquivo baixado.</li>
            <li>
              Na primeira vez, o Android pede para <strong>permitir a instalação de apps desta fonte</strong> (o navegador). Autorize e volte.
            </li>
            <li>Toque em “Instalar” e abra pelo ícone na tela de início.</li>
          </ol>
          {isAndroid() && prompt && (
            <p className="muted small" style={{ margin: 0 }}>
              Prefere sem baixar arquivo?{" "}
              <button type="button" className="link-btn" onClick={() => void install()}>
                Adicionar à tela de início pelo navegador
              </button>
            </p>
          )}
        </section>
        <section className="card stack">
          <h2>
            <MonitorSmartphone size={18} aria-hidden /> iPhone e computador
          </h2>
          {isIos() ? (
            <ol className="install-steps">
              <li>No Safari, toque em Compartilhar (quadrado com a seta).</li>
              <li>Escolha “Adicionar à Tela de Início” e confirme.</li>
              <li>Abra pelo ícone: assim as notificações também funcionam.</li>
            </ol>
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              No Chrome ou no Edge do computador, use o botão abaixo ou o ícone de instalar na barra de endereço. O app abre em janela própria.
            </p>
          )}
          {!isIos() && prompt && (
            <div>
              <Button type="button" variant="secondary" onClick={() => void install()}>
                Instalar no computador
              </Button>
            </div>
          )}
          {!isIos() && !prompt && !done && (
            <p className="muted small" style={{ margin: 0 }}>
              Se o botão de instalar não aparecer, abra o menu do navegador e escolha “Instalar o app” (Chrome e Edge).
            </p>
          )}
        </section>
        <PushNotificationsSection scope="account" />
      </div>
    </>
  );
}
