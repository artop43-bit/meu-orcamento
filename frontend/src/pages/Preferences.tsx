import { useState, type CSSProperties } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarRange, Keyboard, Mail, MessageSquarePlus } from "lucide-react";

import { ME_KEY, useMe, type User } from "../api/auth";
import { api, errorMessage } from "../api/client";
import { ASK_CONVERSATIONS_KEY, askApi } from "../api/insights";
import { sharingApi } from "../api/sharing";
import { openFeedback, openShortcuts, SHORTCUTS } from "../components/power";
import { Alert, Button, PageHeader } from "../components/ui";
import { announce } from "../lib/announce";
import { originOf, setAppearance } from "../lib/appearance";
import { cycleLabel, setCycleStart, thisMonth } from "../lib/format";
import { setPrefs, usePrefs, type Prefs } from "../lib/prefs";
import { PixMeiSettings } from "../components/PixMeiSettings";
import { STYLES, type StyleName } from "../theme/styles";
import { ACCENTS, type AccentName } from "../theme/tokens";

/** v1.7.5: guardar (ou não) as conversas do Tire sua dúvida. Desligar apaga as guardadas. */
function AskHistoryToggle() {
  const me = useMe();
  const client = useQueryClient();
  const on = me.data?.ask_history !== false;
  async function change(value: boolean) {
    await askApi.setHistory(value);
    await client.invalidateQueries({ queryKey: ME_KEY });
    void client.invalidateQueries({ queryKey: ASK_CONVERSATIONS_KEY });
  }
  return (
    <>
      <label className="check">
        <input type="checkbox" checked={on} onChange={(e) => void change(e.target.checked)} />
        Guardar histórico do Tire sua dúvida
      </label>
      <p className="muted small" style={{ margin: 0 }}>
        As conversas ficam na sua conta e são apagadas sozinhas 30 dias depois da última mensagem. Ao desligar, as conversas guardadas são
        apagadas na hora.
      </p>
    </>
  );
}

function Choice<K extends keyof Prefs>({
  name,
  label,
  value,
  options,
}: {
  name: K;
  label: string;
  value: Prefs[K];
  options: [Prefs[K], string][];
}) {
  const queryClient = useQueryClient();
  return (
    <fieldset className="radios">
      <legend className="field-label">{label}</legend>
      <div className="segmented">
        {options.map(([option, text]) => (
          <label key={String(option)}>
            <input
              type="radio"
              name={String(name)}
              checked={value === option}
              onChange={(e) =>
                // Tema e cor de destaque ficam salvos na conta (valem em todos os aparelhos).
                name === "theme" || name === "accent"
                  ? setAppearance({ [name]: option } as Partial<Pick<Prefs, "theme" | "accent">>, queryClient, originOf(e))
                  : setPrefs({ [name]: option } as Partial<Prefs>)
              }
            />
            {text}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/**
 * Estilo visual (v1.6): miniatura de cada um, pintada com o tema e a cor de destaque atuais
 * (o atributo data-style da miniatura troca só a forma, igual ao app inteiro).
 */
function StylePicker({ value }: { value: StyleName }) {
  const queryClient = useQueryClient();
  const styles = Object.entries(STYLES) as [StyleName, (typeof STYLES)[StyleName]][];
  return (
    <fieldset className="radios">
      <legend className="field-label">Estilo</legend>
      <div className="style-picker">
        {styles.map(([name, style]) => (
          <label key={name} className="style-option">
            <input type="radio" name="style" checked={value === name} onChange={(e) => setAppearance({ style: name }, queryClient, originOf(e))} />
            <span className="style-thumb" data-thumb={name} aria-hidden>
              <span className="style-thumb__side" />
              <span className="style-thumb__body">
                <span className="style-thumb__card style-thumb__card--hero" />
                <span className="style-thumb__row">
                  <span className="style-thumb__card" />
                  <span className="style-thumb__card" />
                </span>
              </span>
            </span>
            <span className="style-option__text">
              <strong>{style.label}</strong>
              <span className="muted small">{style.text}</span>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** Cor de destaque: amostras com nome (todas passam no contraste AA, no claro e no escuro). */
function AccentPicker({ value }: { value: AccentName }) {
  const queryClient = useQueryClient();
  const accents = Object.entries(ACCENTS) as [AccentName, (typeof ACCENTS)[AccentName]][];
  return (
    <fieldset className="radios">
      <legend className="field-label">Cor de destaque</legend>
      <div className="accent-swatches">
        {accents.map(([name, accent]) => (
          <label key={name} className="accent-swatch" style={{ "--swatch": accent.light.accent, "--swatch-dark": accent.dark.accent } as CSSProperties}>
            <input type="radio" name="accent" checked={value === name} onChange={(e) => setAppearance({ accent: name }, queryClient, originOf(e))} />
            <span className="accent-swatch__dot" aria-hidden />
            {accent.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

type NotifyPrefs = {
  notify_due: boolean;
  notify_due_days: 1 | 3 | 7;
  notify_hide_values: boolean;
  notify_monthly: boolean;
  notify_messages: boolean;
  notify_alerts: boolean;
  notify_weekly: boolean;
};

/** Mês financeiro: começa no dia 1 ou no dia do salário. Vale para toda a conta. */
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
        Para quem recebe o salário em outro dia: o mês do orçamento passa a ir do dia escolhido até a véspera dele no mês seguinte (ex.: de 5/10
        a 4/11). Orçamento, Insights, relatórios e avisos seguem esse período.
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

/** Avisos por e-mail: vencimentos, resumo do mês e privacidade dos valores. */
function EmailNotices() {
  const queryClient = useQueryClient();
  const prefs = useQuery({ queryKey: ["notify-prefs"], queryFn: () => api.get<NotifyPrefs>("/notifications/prefs") });
  const [error, setError] = useState("");
  // Muda na hora e confirma no servidor; se falhar, volta ao que era e explica.
  async function update(changes: Partial<NotifyPrefs>) {
    const previous = queryClient.getQueryData<NotifyPrefs>(["notify-prefs"]);
    if (previous) queryClient.setQueryData(["notify-prefs"], { ...previous, ...changes });
    setError("");
    try {
      const next = await api.patch<NotifyPrefs>("/notifications/prefs", changes);
      queryClient.setQueryData(["notify-prefs"], next);
    } catch (err) {
      queryClient.setQueryData(["notify-prefs"], previous);
      setError(errorMessage(err));
    }
  }
  const p = prefs.data;
  return (
    <section className="card stack">
      <h2>
        <Mail size={18} aria-hidden /> Avisos por e-mail
      </h2>
      <Alert tone="error">{error}</Alert>
      {!p ? (
        <p className="muted small">Carregando…</p>
      ) : (
        <>
          <label className="check">
            <input type="checkbox" checked={p.notify_due} onChange={(e) => void update({ notify_due: e.target.checked })} />
            Lembrete de vencimentos (um e-mail por dia, às 8h, só quando houver contas em aberto)
          </label>
          {p.notify_due && (
            <fieldset className="radios">
              <legend className="field-label">Avisar com antecedência de</legend>
              <div className="segmented">
                {([1, 3, 7] as const).map((days) => (
                  <label key={days}>
                    <input type="radio" name="due-days" checked={p.notify_due_days === days} onChange={() => void update({ notify_due_days: days })} />
                    {days === 1 ? "1 dia" : `${days} dias`}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          <label className="check">
            <input type="checkbox" checked={p.notify_monthly} onChange={(e) => void update({ notify_monthly: e.target.checked })} />
            Resumo do mês no dia 1 (resultado, poupança, categorias e metas)
          </label>
          <label className="check">
            <input type="checkbox" checked={p.notify_hide_values} onChange={(e) => void update({ notify_hide_values: e.target.checked })} />
            Ocultar valores nos e-mails
          </label>
          <label className="check">
            <input type="checkbox" checked={p.notify_messages} onChange={(e) => void update({ notify_messages: e.target.checked })} />
            Cópia por e-mail das mensagens (respostas às solicitações e recados da administração)
          </label>
          <label className="check">
            <input type="checkbox" checked={p.notify_alerts} onChange={(e) => void update({ notify_alerts: e.target.checked })} />
            Alertas de gastos fora do padrão e de assinaturas
          </label>
          <label className="check">
            <input type="checkbox" checked={p.notify_weekly} onChange={(e) => void update({ notify_weekly: e.target.checked })} />
            Resumo da semana, às segundas às 8h (gastos da semana e as contas que vencem na semana)
          </label>
          <p className="muted small" style={{ margin: 0 }}>
            O aviso de acesso por um aparelho novo é sempre enviado, por segurança.
          </p>
        </>
      )}
    </section>
  );
}

export default function Preferences() {
  const prefs = usePrefs();
  return (
    <>
      <PageHeader title="Preferências" subtitle="Aparência, privacidade e avisos por e-mail." />
      <div className="layout-main-side">
        <div className="stack" style={{ gap: 20 }}>
          <section className="card stack">
            <h2>Aparência</h2>
            <p className="muted small" style={{ margin: 0 }}>
              Estilo, tema e cor de destaque ficam salvos na sua conta e valem em todos os aparelhos. Tamanho do texto e espaçamento valem só neste
              aparelho.
            </p>
            <StylePicker value={prefs.style} />
            <Choice
              name="theme"
              label="Tema"
              value={prefs.theme}
              options={[
                ["system", "Automático (sistema)"],
                ["light", "Claro"],
                ["dark", "Escuro"],
              ]}
            />
            <AccentPicker value={prefs.accent} />
            <Choice
              name="text"
              label="Tamanho do texto"
              value={prefs.text}
              options={[
                ["normal", "Normal"],
                ["grande", "Grande"],
                ["maior", "Maior"],
              ]}
            />
            <Choice
              name="density"
              label="Espaçamento"
              value={prefs.density}
              options={[
                ["confortavel", "Confortável"],
                ["compacta", "Compacto"],
              ]}
            />
          </section>
          <FinancialMonth />
          <PixMeiSettings />
          <EmailNotices />
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
          <section className="card stack">
            <h2>Feedback</h2>
            <p className="muted" style={{ margin: 0 }}>
              Relate problemas ou envie sugestões diretamente à equipe.
            </p>
            <Button type="button" variant="secondary" onClick={openFeedback}>
              <MessageSquarePlus size={16} /> Enviar feedback
            </Button>
          </section>
        </div>
      </div>
    </>
  );
}
