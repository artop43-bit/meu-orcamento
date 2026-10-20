import { useState, type FormEvent, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Award,
  Briefcase,
  CalendarDays,
  Camera,
  Flame,
  Gauge,
  ImagePlus,
  MapPin,
  Pencil,
  PiggyBank,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { errorMessage } from "../api/client";
import { profileApi, useProfile, type Profile, type ProfileSummary, type StatKey } from "../api/profile";
import { fileUrl } from "../api/support";
import { DateField } from "../components/DateField";
import { Tip } from "../components/help";
import { ImageEditor } from "../components/imageCrop";
import { Avatar } from "../components/media";
import { renderShareImage, shareOrDownload, ShareButtons, StoryViewer, periodTitle } from "../components/retrospective";
import { Alert, Button, LoadingRegion, PageHeader, Sheet, Skeleton } from "../components/ui";
import { announce } from "../lib/announce";
import { addMonths, money, percent, thisMonth } from "../lib/format";
import { StartOver } from "../components/StartOver";

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

function EditProfile({ profile, open, onClose }: { profile: Profile; open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    display_name: profile.display_name ?? "",
    profession: profile.profession ?? "",
    city: profile.city ?? "",
    bio: profile.bio ?? "",
  });
  const [stats, setStats] = useState(profile.prefs.stats);
  const [showValues, setShowValues] = useState(profile.prefs.show_values_in_recap);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const updated = await profileApi.update({ ...form, prefs: { stats, show_values_in_recap: showValues } });
      queryClient.setQueryData(["profile"], updated);
      announce("Perfil atualizado");
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const field = (key: keyof typeof form, label: string, max: number, placeholder: string) => (
    <label>
      {label}
      <input value={form[key]} maxLength={max} placeholder={placeholder} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
    </label>
  );

  return (
    <Sheet open={open} title="Editar perfil" onClose={onClose}>
      <form className="inline-form" onSubmit={submit}>
        <Alert tone="error">{error}</Alert>
        <p className="muted small" style={{ margin: 0 }}>
          Todos os campos são opcionais. O perfil é visível só para você (e para a administração, no caso do nome e da foto).
        </p>
        {field("display_name", "Nome de exibição", 60, "Como prefere ser chamado(a)")}
        <div className="grid-2">
          {field("profession", "Profissão", 80, "Ex.: Designer")}
          {field("city", "Cidade", 80, "Ex.: Belo Horizonte")}
        </div>
        <label>
          Sobre você
          <textarea value={form.bio} maxLength={160} rows={2} placeholder="Uma frase curta (até 160 caracteres)" onChange={(e) => setForm({ ...form, bio: e.target.value })} />
        </label>
        <fieldset className="radios">
          <legend className="field-label">
            Dados exibidos no perfil <Tip>Escolha o que aparece no seu resumo. Nada é publicado: o perfil é só seu.</Tip>
          </legend>
          <div className="check-grid">
            {STATS.map((s) => (
              <label key={s.key} className="check">
                <input type="checkbox" checked={stats[s.key]} onChange={(e) => setStats({ ...stats, [s.key]: e.target.checked })} />
                {s.label}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="check">
          <input type="checkbox" checked={showValues} onChange={(e) => setShowValues(e.target.checked)} />
          Mostrar valores em reais na retrospectiva e na imagem para compartilhar
        </label>
        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={busy}>
            Salvar
          </Button>
        </div>
      </form>
    </Sheet>
  );
}

function RetrospectiveCard({ profile }: { profile: Profile }) {
  const [period, setPeriod] = useState<"month" | "year">("month");
  const [month, setMonth] = useState(addMonths(thisMonth(), -1));
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(String(currentYear));
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const value = period === "month" ? month : year;
  const recap = useQuery({ queryKey: ["profile", "recap", period, value], queryFn: () => profileApi.retrospective(period, value), enabled: open });
  const person = { name: personName(profile), avatarId: profile.avatar_id };

  async function exportImage(format: "story" | "square", share: boolean) {
    if (!recap.data) return;
    setMessage("");
    try {
      const blob = await renderShareImage(recap.data, person, format);
      const result = await shareOrDownload(blob, `retrospectiva-${value}-${format === "story" ? "story" : "feed"}.png`, share);
      setMessage(result === "shared" ? "Imagem compartilhada." : "Imagem baixada.");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return; // compartilhamento cancelado
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
        Os destaques do mês ou do ano em telas, com opção de baixar a imagem para compartilhar. Valores em reais aparecem só se você ativar em
        “Editar perfil”.
      </p>
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
              {message && <p className="story__message" role="status">{message}</p>}
            </>
          }
        />
      )}
    </section>
  );
}

export default function ProfilePage() {
  const profile = useProfile();
  const summary = useQuery({ queryKey: ["profile", "summary"], queryFn: profileApi.summary });
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [image, setImage] = useState<"avatar" | "banner" | null>(null);

  if (profile.isPending)
    return (
      <LoadingRegion label="Carregando o perfil">
        <Skeleton height={260} />
      </LoadingRegion>
    );
  if (profile.isError) return <Alert tone="error">{errorMessage(profile.error)}</Alert>;
  const data = profile.data;
  const name = personName(data);
  const visible = STATS.filter((s) => data.prefs.stats[s.key]);
  const since = new Date(data.member_since).toLocaleDateString("pt-BR", { month: "long", year: "numeric" });

  async function saveImage(purpose: "avatar" | "banner", blob: Blob, filename: string) {
    const updated = await profileApi.setImage(purpose, blob, filename);
    queryClient.setQueryData(["profile"], updated);
    announce(purpose === "avatar" ? "Foto atualizada" : "Banner atualizado");
  }

  return (
    <>
      <PageHeader title="Perfil" subtitle="Seus dados, sua foto e o resumo da sua evolução financeira." />
      <section className="card profile-hero" aria-label="Cartão do perfil">
        <div className="profile-hero__banner" style={data.banner_id ? { backgroundImage: `url(${fileUrl(data.banner_id)})` } : undefined}>
          <button type="button" className="profile-hero__edit-banner" onClick={() => setImage("banner")}>
            <ImagePlus size={16} aria-hidden /> {data.banner_id ? "Trocar banner" : "Adicionar banner"}
          </button>
        </div>
        <div className="profile-hero__body">
          <button type="button" className="profile-hero__avatar" onClick={() => setImage("avatar")} aria-label={data.avatar_id ? "Trocar foto" : "Adicionar foto"}>
            <Avatar fileId={data.avatar_id} name={name} size={104} />
            <span className="profile-hero__camera" aria-hidden>
              <Camera size={16} />
            </span>
          </button>
          <div className="profile-hero__info">
            <h2 className="profile-hero__name">{name}</h2>
            <p className="profile-hero__meta muted">
              {data.profession && (
                <span>
                  <Briefcase size={14} aria-hidden /> {data.profession}
                </span>
              )}
              {data.city && (
                <span>
                  <MapPin size={14} aria-hidden /> {data.city}
                </span>
              )}
              <span>
                <CalendarDays size={14} aria-hidden /> Desde {since}
              </span>
            </p>
            {data.bio && <p className="profile-hero__bio">{data.bio}</p>}
          </div>
          <Button type="button" variant="secondary" className="profile-hero__button" onClick={() => setEditing(true)}>
            <Pencil size={16} /> Editar perfil
          </Button>
        </div>
      </section>

      <section className="stack" aria-labelledby="summary-title" style={{ marginTop: 20 }}>
        <div className="section-header">
          <h2 id="summary-title">Meu resumo</h2>
          <span className="muted small">Os mesmos números de Insights. Escolha o que aparece em “Editar perfil”.</span>
        </div>
        {summary.isPending && <Skeleton height={120} />}
        {summary.isError && <Alert tone="error">{errorMessage(summary.error)}</Alert>}
        {summary.data && visible.length === 0 && <p className="muted">Nenhum dado selecionado para o perfil.</p>}
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

      <div style={{ marginTop: 20 }}>
        <RetrospectiveCard profile={data} />
      </div>

      <div style={{ marginTop: 20 }}>
        <StartOver />
      </div>

      {editing && <EditProfile profile={data} open={editing} onClose={() => setEditing(false)} />}
      <ImageEditor
        purpose={image ?? "avatar"}
        open={image !== null}
        hasImage={image === "banner" ? Boolean(data.banner_id) : Boolean(data.avatar_id)}
        onClose={() => setImage(null)}
        onSave={(blob, filename) => saveImage(image!, blob, filename)}
        onRemove={async () => {
          const updated = await profileApi.removeImage(image!);
          queryClient.setQueryData(["profile"], updated);
        }}
      />
    </>
  );
}
