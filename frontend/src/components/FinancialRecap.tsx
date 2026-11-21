import { useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Award, Flame, Gauge, PiggyBank, SlidersHorizontal, Sparkles, Target, TrendingDown, TrendingUp } from "lucide-react";

import { errorMessage } from "../api/client";
import { profileApi, useProfile, type Profile, type ProfileSummary, type StatKey } from "../api/profile";
import { announce } from "../lib/announce";
import { addMonths, money, percent, thisMonth } from "../lib/format";
import { DateField } from "./DateField";
import { periodTitle, renderShareImage, ShareButtons, shareOrDownload, StoryViewer } from "./retrospective";
import { Alert, Button, LoadingRegion, Sheet, Skeleton } from "./ui";

type Stat = { key: StatKey; label: string; icon: ReactNode; value: (s: ProfileSummary) => string; foot?: (s: ProfileSummary) => string };

const STATS: Stat[] = [
  { key: "avg_income", label: "Média de receitas", icon: <TrendingUp size={17} />, value: (s) => (s.avg_income ? money(s.avg_income) : "—"), foot: (s) => `${s.months} mês(es) fechados` },
  { key: "avg_expenses", label: "Média de despesas", icon: <TrendingDown size={17} />, value: (s) => (s.avg_expenses ? money(s.avg_expenses) : "—"), foot: (s) => `${s.months} mês(es) fechados` },
  { key: "savings_rate", label: "Taxa de poupança", icon: <PiggyBank size={17} />, value: (s) => percent(s.savings_rate), foot: () => "Média dos meses fechados" },
  { key: "goals_completed", label: "Metas concluídas", icon: <Target size={17} />, value: (s) => `${s.goals_completed} de ${s.goals_total}` },
  { key: "positive_months", label: "Meses no azul", icon: <Award size={17} />, value: (s) => String(s.positive_months), foot: () => "Receitas maiores que despesas" },
  { key: "best_streak", label: "Maior sequência no azul", icon: <Flame size={17} />, value: (s) => `${s.best_streak} mês(es)` },
  { key: "score", label: "Score financeiro", icon: <Gauge size={17} />, value: (s) => (s.score === null ? "—" : String(s.score)), foot: (s) => s.score_label ?? "" },
];

function personName(profile: Profile): string {
  return profile.display_name || profile.email.split("@")[0]!;
}

function CustomizeStatsSheet({
  profile,
  open,
  onClose,
}: {
  profile: Profile;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [stats, setStats] = useState(profile.prefs.stats);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    setBusy(true);
    setError("");
    try {
      const updated = await profileApi.update({ prefs: { stats } });
      queryClient.setQueryData(["profile"], updated);
      announce("Resumo atualizado");
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open={open} title="Personalizar resumo" onClose={onClose}>
      <div className="inline-form">
        <Alert tone="error">{error}</Alert>
        <p className="muted small" style={{ margin: 0 }}>
          Escolha quais indicadores aparecem no seu resumo financeiro.
        </p>
        <div className="check-grid">
          {STATS.map((s) => (
            <label key={s.key} className="check">
              <input type="checkbox" checked={stats[s.key]} onChange={(e) => setStats({ ...stats, [s.key]: e.target.checked })} />
              {s.label}
            </label>
          ))}
        </div>
        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="button" loading={busy} onClick={() => void save()}>
            Salvar
          </Button>
        </div>
      </div>
    </Sheet>
  );
}

/** Resumo financeiro acumulado e retrospectiva compartilhável (Meu Orçamento › Análises). */
export function FinancialRecapSection() {
  const queryClient = useQueryClient();
  const profile = useProfile();
  const summary = useQuery({ queryKey: ["profile", "summary"], queryFn: profileApi.summary });
  const [customizing, setCustomizing] = useState(false);
  const [period, setPeriod] = useState<"month" | "year">("month");
  const [month, setMonth] = useState(addMonths(thisMonth(), -1));
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(String(currentYear));
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [prefsError, setPrefsError] = useState("");

  if (profile.isPending) {
    return (
      <LoadingRegion label="Carregando o resumo financeiro">
        <Skeleton height={200} />
      </LoadingRegion>
    );
  }
  if (profile.isError) return <Alert tone="error">{errorMessage(profile.error)}</Alert>;

  const data = profile.data;
  const visible = STATS.filter((s) => data.prefs.stats[s.key]);
  const value = period === "month" ? month : year;
  const person = { name: personName(data), avatarId: data.avatar_id };

  return (
    <div className="stack" style={{ gap: 20 }}>
      <section className="stack" aria-labelledby="summary-title">
        <div className="section-header">
          <div>
            <h2 id="summary-title">Meu resumo</h2>
            <p className="muted small" style={{ margin: 0 }}>
              Consolidado dos meses fechados no Meu Orçamento.
            </p>
          </div>
          <Button type="button" variant="secondary" onClick={() => setCustomizing(true)}>
            <SlidersHorizontal size={16} aria-hidden /> Personalizar
          </Button>
        </div>
        {summary.isPending && <Skeleton height={120} />}
        {summary.isError && <Alert tone="error">{errorMessage(summary.error)}</Alert>}
        {summary.data && visible.length === 0 && <p className="muted">Nenhum indicador selecionado no resumo.</p>}
        {summary.data && visible.length > 0 && (
          <div className="kpis profile-stats">
            {visible.map((s) => (
              <div key={s.key} className="kpi">
                <div className="kpi__head">
                  <span className="kpi__icon" aria-hidden>
                    {s.icon}
                  </span>
                  {s.label}
                </div>
                <div className="kpi__value">{s.value(summary.data)}</div>
                {s.foot && <div className="kpi__foot">{s.foot(summary.data)}</div>}
              </div>
            ))}
          </div>
        )}
      </section>

      <RetrospectiveCard
        profile={data}
        person={person}
        period={period}
        setPeriod={setPeriod}
        month={month}
        setMonth={setMonth}
        year={year}
        setYear={setYear}
        currentYear={currentYear}
        value={value}
        open={open}
        setOpen={setOpen}
        message={message}
        setMessage={setMessage}
        prefsError={prefsError}
        onToggleShowValues={async (show) => {
          setPrefsError("");
          try {
            const updated = await profileApi.update({ prefs: { show_values_in_recap: show } });
            queryClient.setQueryData(["profile"], updated);
            void queryClient.invalidateQueries({ queryKey: ["profile", "recap"] });
          } catch (err) {
            setPrefsError(errorMessage(err));
          }
        }}
      />

      {customizing && <CustomizeStatsSheet profile={data} open={customizing} onClose={() => setCustomizing(false)} />}
    </div>
  );
}

function RetrospectiveCard({
  profile,
  person,
  period,
  setPeriod,
  month,
  setMonth,
  year,
  setYear,
  currentYear,
  value,
  open,
  setOpen,
  message,
  setMessage,
  prefsError,
  onToggleShowValues,
}: {
  profile: Profile;
  person: { name: string; avatarId: string | null };
  period: "month" | "year";
  setPeriod: (p: "month" | "year") => void;
  month: string;
  setMonth: (m: string) => void;
  year: string;
  setYear: (y: string) => void;
  currentYear: number;
  value: string;
  open: boolean;
  setOpen: (o: boolean) => void;
  message: string;
  setMessage: (m: string) => void;
  prefsError: string;
  onToggleShowValues: (show: boolean) => Promise<void>;
}) {
  const recap = useQuery({ queryKey: ["profile", "recap", period, value], queryFn: () => profileApi.retrospective(period, value), enabled: open });

  async function exportImage(format: "story" | "square", share: boolean) {
    if (!recap.data) return;
    setMessage("");
    try {
      const blob = await renderShareImage(recap.data, person, format);
      const result = await shareOrDownload(blob, `retrospectiva-${value}-${format === "story" ? "story" : "feed"}.png`, share);
      setMessage(result === "shared" ? "Imagem compartilhada." : "Imagem baixada.");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setMessage(errorMessage(err));
    }
  }

  return (
    <section className="card stack" aria-labelledby="recap-title">
      <div className="section-header">
        <h2 id="recap-title">
          <Sparkles size={18} aria-hidden /> Retrospectiva
        </h2>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        Os destaques do mês ou do ano em telas, com opção de baixar a imagem para compartilhar.
      </p>
      <Alert tone="error">{prefsError}</Alert>
      <label className="check">
        <input
          type="checkbox"
          checked={profile.prefs.show_values_in_recap}
          onChange={(e) => void onToggleShowValues(e.target.checked)}
        />
        Mostrar valores em reais na retrospectiva e na imagem para compartilhar
      </label>
      <div className="recap-controls">
        <div className="segmented segmented--compact" role="radiogroup" aria-label="Período">
          <label>
            <input type="radio" name="recap-period" checked={period === "month"} onChange={() => setPeriod("month")} />
            Mês
          </label>
          <label>
            <input type="radio" name="recap-period" checked={period === "year"} onChange={() => setPeriod("year")} />
            Ano
          </label>
        </div>
        {period === "month" ? (
          <label>
            <span className="field-label">Mês</span>
            <DateField month value={month} max={thisMonth()} onChange={(v) => v && setMonth(v)} label="Mês da retrospectiva" />
          </label>
        ) : (
          <label>
            Ano
            <select value={year} onChange={(e) => setYear(e.target.value)}>
              {Array.from({ length: 6 }, (_, i) => String(currentYear - i)).map((y) => (
                <option key={y}>{y}</option>
              ))}
            </select>
          </label>
        )}
        <Button type="button" onClick={() => setOpen(true)}>
          <Sparkles size={16} /> Ver retrospectiva
        </Button>
      </div>
      {open && recap.isPending && (
        <LoadingRegion label="Montando a retrospectiva">
          <Skeleton height={60} />
        </LoadingRegion>
      )}
      {open && recap.isError && <Alert tone="error">{errorMessage(recap.error)}</Alert>}
      {open && recap.data && !recap.data.has_data && (
        <Alert tone="info">Sem lançamentos em {periodTitle(recap.data)}. Escolha outro período.</Alert>
      )}
      {open && recap.data?.has_data && (
        <StoryViewer
          data={recap.data}
          person={person}
          onClose={() => setOpen(false)}
          footer={
            <>
              <ShareButtons onExport={exportImage} />
              {message && (
                <p className="story__message" role="status">
                  {message}
                </p>
              )}
            </>
          }
        />
      )}
    </section>
  );
}
