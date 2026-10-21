import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Flag, Plus, Trash2, Trophy } from "lucide-react";

import { useCategories } from "../api/budget";
import { errorMessage } from "../api/client";
import { CHALLENGES_KEY, habitsApi, type Challenge, type ChallengeKind, type ChallengeTemplate } from "../api/habits";
import { announce } from "../lib/announce";
import { money, shortDate } from "../lib/format";
import { Bar, CategorySelect, MoneyInput, requireMoney } from "./budget";
import { Tip } from "./help";
import { Alert, Button, Sheet } from "./ui";

/** Valor opcional: vazio vira null; preenchido é validado como dinheiro. */
const requireMoneyOrNull = (value: string) => (value.trim() ? requireMoney(value) : null);

const KIND_LABELS: Record<ChallengeKind, string> = {
  no_keyword: "Sem gastos com certas palavras (ex.: ifood, rappi)",
  no_category: "Sem gastos numa categoria",
  no_nonessential: "Só gastos essenciais",
  max_category: "Gastar no máximo um valor numa categoria",
};

const STATUS: Record<Challenge["status"], { label: string; tone: string }> = {
  active: { label: "Em andamento", tone: "badge--info" },
  won: { label: "Concluído", tone: "badge--ok" },
  lost: { label: "Não deu desta vez", tone: "badge--muted" },
};

function ChallengeCard({ challenge, onRemove }: { challenge: Challenge; onRemove: () => void }) {
  const pct = (challenge.elapsed_days / challenge.days) * 100;
  const status = STATUS[challenge.status];
  return (
    <article className="card stack challenge">
      <div className="section-header">
        <h3 className="challenge__title">
          {challenge.status === "won" ? <Trophy size={18} aria-hidden /> : <Flag size={18} aria-hidden />} {challenge.title}
        </h3>
        <button type="button" className="icon-btn" aria-label={`Excluir o desafio ${challenge.title}`} onClick={onRemove}>
          <Trash2 size={16} aria-hidden />
        </button>
      </div>
      <span className={`badge ${status.tone}`} style={{ justifySelf: "start" }}>
        {status.label}
      </span>
      <Bar pct={pct} color={challenge.status === "lost" ? "var(--border-strong)" : "var(--positive)"} />
      <p className="muted small" style={{ margin: 0 }}>
        Dia {challenge.elapsed_days} de {challenge.days} · {shortDate(challenge.start_date)} a {shortDate(challenge.end_date)}
        {challenge.kind === "max_category" && challenge.max_amount && ` · ${money(challenge.spent)} de ${money(challenge.max_amount)}`}
      </p>
      {challenge.status === "lost" && challenge.slips.length > 0 && (
        <p className="small" style={{ margin: 0 }}>
          Lançamento que interrompeu: {challenge.slips[0]!.description} ({money(challenge.slips[0]!.amount)}, {shortDate(challenge.slips[0]!.date)}).
          Um novo desafio pode começar quando quiser.
        </p>
      )}
      {challenge.status === "won" && (
        <p className="small" style={{ margin: 0 }}>
          Desafio concluído: {challenge.days} dias seguindo o combinado.
        </p>
      )}
    </article>
  );
}

function ChallengeForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const categories = useCategories();
  const templates = useQuery({ queryKey: ["challenge-templates"], queryFn: habitsApi.templates, staleTime: Infinity });
  const [choice, setChoice] = useState<string>("delivery");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<ChallengeKind>("no_keyword");
  const [categoryId, setCategoryId] = useState("");
  const [keywords, setKeywords] = useState("");
  const [max, setMax] = useState("");
  const [days, setDays] = useState("30");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const template: ChallengeTemplate | undefined = templates.data?.find((t) => t.key === choice);
  const custom = choice === "custom";
  const needsMax = custom ? kind === "max_category" : template?.kind === "max_category";
  const needsCategory = custom && (kind === "no_category" || kind === "max_category");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const created = await habitsApi.createChallenge(
        custom
          ? { title, kind, category_id: categoryId || null, keywords: keywords || null, max_amount: requireMoneyOrNull(max), days: Number(days) }
          : { template: choice, max_amount: needsMax ? requireMoneyOrNull(max) : null },
      );
      await queryClient.invalidateQueries({ queryKey: CHALLENGES_KEY });
      announce(`Desafio “${created.title}” iniciado`);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <Alert tone="error">{error}</Alert>
      <fieldset className="radios">
        <legend className="field-label">Escolha um desafio</legend>
        <div className="stack stack--tight">
          {(templates.data ?? []).map((t) => (
            <label key={t.key} className="check challenge-option">
              <input type="radio" name="template" checked={choice === t.key} onChange={() => setChoice(t.key)} />
              <span>
                <strong>{t.title}</strong>
                <span className="muted small"> · {t.text}</span>
              </span>
            </label>
          ))}
          <label className="check challenge-option">
            <input type="radio" name="template" checked={custom} onChange={() => setChoice("custom")} />
            <span>
              <strong>Personalizado</strong>
              <span className="muted small"> · do seu jeito</span>
            </span>
          </label>
        </div>
      </fieldset>
      {custom && (
        <>
          <label>
            Nome do desafio
            <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={80} placeholder="Ex.: Mês sem bar" required />
          </label>
          <label>
            Regra
            <select value={kind} onChange={(e) => setKind(e.target.value as ChallengeKind)}>
              {(Object.keys(KIND_LABELS) as ChallengeKind[]).map((k) => (
                <option key={k} value={k}>
                  {KIND_LABELS[k]}
                </option>
              ))}
            </select>
          </label>
          {kind === "no_keyword" && (
            <label>
              <span className="field-label">
                Palavras <Tip>Separadas por vírgula. Qualquer despesa cuja descrição contenha uma delas interrompe o desafio.</Tip>
              </span>
              <input value={keywords} onChange={(e) => setKeywords(e.target.value)} maxLength={200} placeholder="Ex.: bar, boteco, chopp" required />
            </label>
          )}
          {needsCategory && (
            <label>
              Categoria
              <CategorySelect categories={categories.data ?? []} value={categoryId} onChange={setCategoryId} />
            </label>
          )}
          <label className="narrow">
            Duração (dias)
            <input type="number" min={3} max={90} value={days} onChange={(e) => setDays(e.target.value)} required />
          </label>
        </>
      )}
      {needsMax && (
        <label>
          Valor máximo no período
          <MoneyInput value={max} onChange={setMax} />
        </label>
      )}
      <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" loading={busy}>
          Começar desafio
        </Button>
      </div>
    </form>
  );
}

/** Metas › Desafios: hábitos curtos, com progresso pelos próprios lançamentos. */
export function Challenges() {
  const queryClient = useQueryClient();
  const list = useQuery({ queryKey: CHALLENGES_KEY, queryFn: habitsApi.challenges });
  const [adding, setAdding] = useState(false);
  const challenges = list.data ?? [];
  const active = challenges.filter((c) => c.status === "active");
  const finished = challenges.filter((c) => c.status !== "active");
  const wins = finished.filter((c) => c.status === "won").length;

  async function remove(challenge: Challenge) {
    await habitsApi.deleteChallenge(challenge.id);
    await queryClient.invalidateQueries({ queryKey: CHALLENGES_KEY });
    announce(`Desafio “${challenge.title}” excluído`);
  }

  return (
    <section className="stack challenges" style={{ marginTop: 24 }} aria-labelledby="desafios">
      <div className="section-header">
        <div>
          <h2 id="desafios">Desafios</h2>
          <p className="muted small" style={{ margin: 0 }}>
            Metas curtas de hábito, acompanhadas pelos seus lançamentos.{wins > 0 && ` ${wins} desafio(s) concluído(s) até agora.`}
          </p>
        </div>
        <Button type="button" variant="secondary" onClick={() => setAdding(true)}>
          <Plus size={16} /> Novo desafio
        </Button>
      </div>
      {list.isError && <Alert tone="error">{errorMessage(list.error)}</Alert>}
      {list.data && challenges.length === 0 && (
        <p className="muted" style={{ margin: 0 }}>
          Nenhum desafio ainda. Experimente “30 dias sem delivery” ou crie um do seu jeito.
        </p>
      )}
      {active.length > 0 && (
        <div className="grid-cards">
          {active.map((c) => (
            <ChallengeCard key={c.id} challenge={c} onRemove={() => void remove(c)} />
          ))}
        </div>
      )}
      {finished.length > 0 && (
        <details className="more">
          <summary>Encerrados ({finished.length})</summary>
          <div className="grid-cards" style={{ marginTop: 12 }}>
            {finished.map((c) => (
              <ChallengeCard key={c.id} challenge={c} onRemove={() => void remove(c)} />
            ))}
          </div>
        </details>
      )}
      <Sheet open={adding} title="Novo desafio" onClose={() => setAdding(false)}>
        {adding && <ChallengeForm onDone={() => setAdding(false)} />}
      </Sheet>
    </section>
  );
}
