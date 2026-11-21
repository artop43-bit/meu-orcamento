import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CalendarRange, Keyboard } from "lucide-react";

import { ME_KEY, useMe, type User } from "../api/auth";
import { errorMessage } from "../api/client";
import { ASK_CONVERSATIONS_KEY, askApi } from "../api/insights";
import { sharingApi } from "../api/sharing";
import { EmailNoticesSection, PushNotificationsSection } from "../components/NotificationBlocks";
import { PixMeiSettings } from "../components/PixMeiSettings";
import { openShortcuts, SHORTCUTS } from "../components/power";
import { WebhookSettings } from "../components/WebhookSettings";
import { Alert, Button, PageHeader } from "../components/ui";
import { announce } from "../lib/announce";
import { cycleLabel, setCycleStart, thisMonth } from "../lib/format";
import { setPrefs, usePrefs } from "../lib/prefs";

/** v1.7.5: guardar (ou não) as conversas do Tire sua dúvida. Desligar apaga as guardadas. */
function AskHistoryToggle() {
  const me = useMe();
  const client = useQueryClient();
  const [local, setLocal] = useState<boolean | null>(null);
  const on = local ?? me.data?.ask_history !== false;
  async function change(value: boolean) {
    setLocal(value);
    try {
      await askApi.setHistory(value);
      await client.invalidateQueries({ queryKey: ME_KEY });
      void client.invalidateQueries({ queryKey: ASK_CONVERSATIONS_KEY });
      announce(value ? "Histórico ligado" : "Histórico desligado e conversas apagadas");
    } finally {
      setLocal(null);
    }
  }
  return (
    <>
      <label className="check">
        <input type="checkbox" checked={on} onChange={(e) => void change(e.target.checked)} />
        Guardar histórico do Tire sua dúvida
      </label>
      <p className="muted small" style={{ margin: 0 }}>
        As conversas ficam na sua conta e são apagadas sozinhas 30 dias depois da última mensagem. Ao desligar, as conversas guardadas são apagadas
        na hora.
      </p>
    </>
  );
}

/** Mês financeiro: começa no dia 1 ou no dia do salário. Vale para o Meu Orçamento. */
function FinancialMonth() {
  const queryClient = useQueryClient();
  const { data: user } = useMe();
  const [error, setError] = useState("");
  const current = user?.month_start_day ?? 1;

  async function change(day: number) {
    setError("");
    try {
      await sharingApi.cycle(day);
      setCycleStart(day);
      queryClient.setQueryData<User | null>(ME_KEY, (u) => (u ? { ...u, month_start_day: day } : u));
      await queryClient.invalidateQueries({ queryKey: ["budget"] });
      announce(day === 1 ? "Mês financeiro: do dia 1 ao fim do mês" : `Mês financeiro: começa no dia ${day}`);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <section className="card stack">
      <h2>
        <CalendarRange size={18} aria-hidden /> Mês financeiro
      </h2>
      <p className="muted small" style={{ margin: 0 }}>
        Para quem recebe o salário em outro dia: o mês do orçamento passa a ir do dia escolhido até a véspera dele no mês seguinte (ex.: de 5/10 a
        4/11). Orçamento, Insights, relatórios e avisos seguem esse período.
      </p>
      <Alert tone="error">{error}</Alert>
      <label className="narrow">
        Começa no dia
        <select value={current} onChange={(e) => void change(Number(e.target.value))}>
          {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
            <option key={d} value={d}>
              {d === 1 ? "1 (mês do calendário)" : d}
            </option>
          ))}
        </select>
      </label>
      {current > 1 && <p className="muted small" style={{ margin: 0 }}>Este mês: {cycleLabel(thisMonth())}.</p>}
    </section>
  );
}

/** Preferências específicas do Meu Orçamento. Aparência e avisos gerais da conta ficam no Hub. */
export default function Preferences() {
  const prefs = usePrefs();
  return (
    <>
      <PageHeader title="Preferências" subtitle="Mês financeiro, Pix, avisos financeiros, privacidade e atalhos." />
      <div className="layout-main-side">
        <div className="stack" style={{ gap: 20 }}>
          <FinancialMonth />
          <PixMeiSettings />
          <EmailNoticesSection scope="budget" />
          <WebhookSettings scope="budget" />
          <PushNotificationsSection scope="budget" />
          <section className="card stack" id="privacidade">
            <h2>Privacidade</h2>
            <AskHistoryToggle />
            <label className="check">
              <input type="checkbox" checked={prefs.privacy} onChange={(e) => setPrefs({ privacy: e.target.checked })} />
              Ocultar valores agora (atalho: P)
            </label>
            <label className="check">
              <input type="checkbox" checked={prefs.privacyOnStart} onChange={(e) => setPrefs({ privacyOnStart: e.target.checked })} />
              Iniciar sempre com os valores ocultos
            </label>
            <p className="muted small" style={{ margin: 0 }}>
              Oculta valores em locais públicos ou ao compartilhar a tela: valores exibidos como “R$ ••••” e gráficos desfocados.
            </p>
          </section>
        </div>
        <div className="stack" style={{ gap: 20 }}>
          <section className="card stack" id="atalhos">
            <h2>Atalhos de teclado</h2>
            <dl className="shortcuts">
              {SHORTCUTS.map(([key, what]) => (
                <div key={key}>
                  <dt>
                    <kbd>{key}</kbd>
                  </dt>
                  <dd>{what}</dd>
                </div>
              ))}
            </dl>
            <Button type="button" variant="secondary" onClick={openShortcuts}>
              <Keyboard size={16} /> Ver atalhos
            </Button>
          </section>
        </div>
      </div>
    </>
  );
}
