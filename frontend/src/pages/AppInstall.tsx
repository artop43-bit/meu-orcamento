import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, Download, MonitorSmartphone, Smartphone } from "lucide-react";

import { errorMessage } from "../api/client";
import { currentSubscription, disablePush, enablePush, PUSH_KEY, pushApi, pushSupported, type PushConfig } from "../api/push";
import { Alert, Button, PageHeader } from "../components/ui";
import { announce } from "../lib/announce";

export const APK_URL = "/downloads/meu-orcamento.apk";

type InstallPrompt = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

function isAndroid() {
  return /Android/i.test(navigator.userAgent);
}

function isIos() {
  return /iPhone|iPad|iPod/i.test(navigator.userAgent);
}

function installed() {
  return window.matchMedia?.("(display-mode: standalone)").matches || document.referrer.startsWith("android-app://");
}

function Notifications() {
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: PUSH_KEY, queryFn: pushApi.config });
  const [subscribed, setSubscribed] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const supported = pushSupported();

  useEffect(() => {
    void currentSubscription().then((s) => setSubscribed(Boolean(s)));
  }, []);

  function store(data: PushConfig | null) {
    if (data) queryClient.setQueryData(PUSH_KEY, data);
  }

  async function toggle() {
    setBusy(true);
    setError("");
    setInfo("");
    try {
      if (subscribed) {
        store(await disablePush());
        setSubscribed(false);
        announce("Notificações desativadas neste aparelho");
      } else {
        store(await enablePush(config.data!.public_key));
        setSubscribed(true);
        announce("Notificações ativadas neste aparelho");
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    setError("");
    try {
      const { sent } = await pushApi.test();
      setInfo(sent > 0 ? "Notificação de teste enviada." : "Nenhum aparelho recebeu. Ative as notificações neste aparelho primeiro.");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function pref(key: "push_due" | "push_messages" | "push_alerts", value: boolean) {
    const previous = config.data;
    if (previous) queryClient.setQueryData(PUSH_KEY, { ...previous, [key]: value });
    try {
      store(await pushApi.prefs({ [key]: value }));
    } catch (err) {
      if (previous) queryClient.setQueryData(PUSH_KEY, previous);
      setError(errorMessage(err));
    }
  }

  const data = config.data;
  return (
    <section className="card stack">
      <h2>
        <BellRing size={18} aria-hidden /> Notificações no aparelho
      </h2>
      <p className="muted small" style={{ margin: 0 }}>
        Avisos na tela do celular ou do computador, mesmo com o app fechado. Funcionam no app Android, no Chrome e no Edge; no iPhone, só
        com o Meu Orçamento adicionado à tela de início (exigência da Apple).
      </p>
      <Alert tone="error">{error}</Alert>
      <Alert tone="success">{info}</Alert>
      {!supported && <Alert tone="info">Este navegador não aceita notificações. No iPhone, adicione o app à tela de início e abra por lá.</Alert>}
      {supported && data && !data.enabled && <Alert tone="info">As notificações no aparelho ainda não estão disponíveis no servidor.</Alert>}
      {supported && data?.enabled && (
        <>
          <div className="row">
            <Button type="button" variant={subscribed ? "secondary" : "primary"} loading={busy} onClick={() => void toggle()}>
              {subscribed ? "Desativar neste aparelho" : "Ativar neste aparelho"}
            </Button>
            {subscribed && (
              <Button type="button" variant="secondary" onClick={() => void test()}>
                Enviar notificação de teste
              </Button>
            )}
          </div>
          <fieldset className="radios">
            <legend className="field-label">O que avisar</legend>
            <label className="check">
              <input type="checkbox" checked={data.push_due} onChange={(e) => void pref("push_due", e.target.checked)} />
              Contas a vencer
            </label>
            <label className="check">
              <input type="checkbox" checked={data.push_messages} onChange={(e) => void pref("push_messages", e.target.checked)} />
              Mensagens (respostas às solicitações e recados)
            </label>
            <label className="check">
              <input type="checkbox" checked={data.push_alerts} onChange={(e) => void pref("push_alerts", e.target.checked)} />
              Alertas de gastos e assinaturas
            </label>
          </fieldset>
          <p className="muted small" style={{ margin: 0 }}>
            {data.devices === 0 ? "Nenhum aparelho ativado." : `${data.devices} aparelho(s) recebendo notificações.`} Recados marcados como
            importantes chegam sempre.
          </p>
        </>
      )}
    </section>
  );
}

/** Ajustes › App e notificações: instalar no Android (APK), no iPhone e no computador. */
export default function AppInstallPage() {
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);
  const [done, setDone] = useState(installed());

  useEffect(() => {
    const capture = (event: Event) => {
      event.preventDefault();
      setPrompt(event as InstallPrompt);
    };
    window.addEventListener("beforeinstallprompt", capture);
    return () => window.removeEventListener("beforeinstallprompt", capture);
  }, []);

  async function install() {
    if (!prompt) return;
    await prompt.prompt();
    const { outcome } = await prompt.userChoice;
    if (outcome === "accepted") setDone(true);
    setPrompt(null);
  }

  return (
    <>
      <PageHeader title="App e notificações" subtitle="Instale o Meu Orçamento no celular ou no computador e receba avisos no aparelho." />
      <div className="stack" style={{ gap: 20 }}>
        {done && <Alert tone="success">Você está usando o app instalado.</Alert>}
        <section className="card stack">
          <h2>
            <Smartphone size={18} aria-hidden /> Android
          </h2>
          <p className="muted" style={{ margin: 0 }}>
            O app para Android é distribuído aqui mesmo, sem loja. Ele abre em tela cheia, recebe notificações e se atualiza sozinho: as telas
            novas chegam sem precisar instalar de novo.
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
            <li>Toque em “Instalar” e abra o Meu Orçamento pelo ícone na tela de início.</li>
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
          {!isIos() && (
            <div>
              <Button type="button" variant="secondary" disabled={!prompt} onClick={() => void install()}>
                {prompt ? "Instalar no computador" : done ? "Já instalado" : "Instalação indisponível neste navegador"}
              </Button>
            </div>
          )}
        </section>
        <Notifications />
      </div>
    </>
  );
}
