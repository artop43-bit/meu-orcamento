import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowUpRight, Handshake, Plus, Trash2, Users } from "lucide-react";

import { errorMessage } from "../api/client";
import { SPLITS_KEY, sharingApi, type SplitBoard } from "../api/sharing";
import { MoneyInput, requireMoney } from "../components/budget";
import { EmptyGuide } from "../components/help";
import { Alert, Button, Kpi, LoadingRegion, PageHeader, Sheet, Skeleton } from "../components/ui";
import { announce } from "../lib/announce";
import { money, shortDate } from "../lib/format";

function ManualForm({ names, onDone }: { names: string[]; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [person, setPerson] = useState("");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [direction, setDirection] = useState<"owes_me" | "i_owe">("owes_me");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await sharingApi.addManual({ person: person.trim(), description: description.trim(), amount: requireMoney(amount), direction });
      await queryClient.invalidateQueries({ queryKey: SPLITS_KEY });
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
        <legend className="field-label">Quem deve</legend>
        <div className="segmented">
          <label>
            <input type="radio" name="manual-direction" checked={direction === "owes_me"} onChange={() => setDirection("owes_me")} />
            A pessoa me deve
          </label>
          <label>
            <input type="radio" name="manual-direction" checked={direction === "i_owe"} onChange={() => setDirection("i_owe")} />
            Eu devo à pessoa
          </label>
        </div>
      </fieldset>
      <datalist id="manual-people">
        {names.map((n) => (
          <option key={n} value={n} />
        ))}
      </datalist>
      <div className="grid-2">
        <label>
          Pessoa
          <input value={person} onChange={(e) => setPerson(e.target.value)} list="manual-people" required maxLength={60} />
        </label>
        <label>
          Valor
          <MoneyInput value={amount} onChange={setAmount} />
        </label>
      </div>
      <label>
        Descrição
        <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={120} placeholder="Ex.: Ingresso do show" />
      </label>
      <div className="form-actions">
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" loading={busy}>
          Salvar
        </Button>
      </div>
    </form>
  );
}

function SettleForm({ person, balance, onDone }: { person: string; balance: number; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [record, setRecord] = useState(balance > 0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setError("");
    setBusy(true);
    try {
      await sharingApi.settle(person, record && balance > 0);
      announce(`Contas acertadas com ${person}`);
      await queryClient.invalidateQueries({ queryKey: SPLITS_KEY });
      await queryClient.invalidateQueries({ queryKey: ["budget"] });
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <Alert tone="error">{error}</Alert>
      <p style={{ margin: 0 }}>
        {balance > 0 ? (
          <>
            {person} pagou a você <strong>{money(balance)}</strong>?
          </>
        ) : balance < 0 ? (
          <>
            Você pagou <strong>{money(-balance)}</strong> a {person}?
          </>
        ) : (
          <>As contas com {person} estão zeradas.</>
        )}{" "}
        Todos os itens em aberto com {person} ficam quitados.
      </p>
      {balance > 0 && (
        <label className="check">
          <input type="checkbox" checked={record} onChange={(e) => setRecord(e.target.checked)} />
          Lançar o reembolso como receita deste mês
        </label>
      )}
      <div className="form-actions">
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="button" loading={busy} onClick={() => void confirm()}>
          Acertar contas
        </Button>
      </div>
    </div>
  );
}

function PersonCard({ entry, onSettle }: { entry: SplitBoard["people"][number]; onSettle: () => void }) {
  const queryClient = useQueryClient();
  const balance = Number(entry.balance);
  async function remove(id: string) {
    await sharingApi.remove(id);
    await queryClient.invalidateQueries({ queryKey: SPLITS_KEY });
  }
  return (
    <section className="card stack split-person">
      <div className="section-header">
        <h2>{entry.person}</h2>
        <span className={`split-person__balance ${balance >= 0 ? "tone--ok" : "tone--error"}`}>
          {balance > 0 ? `te deve ${money(balance)}` : balance < 0 ? `você deve ${money(-balance)}` : "zerado"}
        </span>
      </div>
      <ul className="items">
        {entry.items.map((s) => (
          <li key={s.id} className="item">
            <span className="item__main">
              <span className="item__title">{s.description}</span>
              <span className="item__meta">
                {s.direction === "owes_me" ? "Deve a você" : "Você deve"} · {shortDate(s.created_at.slice(0, 10))}
              </span>
            </span>
            <strong className="num">{money(s.amount)}</strong>
            <button type="button" className="icon-btn" aria-label={`Remover ${s.description}`} onClick={() => void remove(s.id)}>
              <Trash2 size={16} />
            </button>
          </li>
        ))}
      </ul>
      <div>
        <Button type="button" variant="secondary" onClick={onSettle}>
          <Handshake size={16} /> Acertar contas
        </Button>
      </div>
    </section>
  );
}

/** Divisões: placar de quem deve a quem, acerto de contas e anotações avulsas. */
export default function SplitsPage() {
  const board = useQuery({ queryKey: SPLITS_KEY, queryFn: sharingApi.board });
  const [adding, setAdding] = useState(false);
  const [settling, setSettling] = useState<{ person: string; balance: number } | null>(null);
  const data = board.data;
  return (
    <>
      <PageHeader
        title="Divisões"
        subtitle="Quem deve a quem nas despesas divididas e nas anotações."
        actions={
          <Button type="button" onClick={() => setAdding(true)}>
            <Plus size={16} /> Nova anotação
          </Button>
        }
      />
      {board.isPending && (
        <LoadingRegion label="Carregando as divisões">
          <Skeleton height={180} />
        </LoadingRegion>
      )}
      {board.isError && <Alert tone="error">{errorMessage(board.error)}</Alert>}
      {data && (
        <div className="kpis" style={{ marginBottom: 20 }}>
          <Kpi icon={<ArrowDownLeft size={18} />} label="Te devem" value={money(data.owed_to_me)} foot="Soma do que está em aberto" />
          <Kpi icon={<ArrowUpRight size={18} />} tone="expense" label="Você deve" value={money(data.i_owe)} foot="Soma do que está em aberto" />
        </div>
      )}
      {data && data.people.length === 0 && (
        <section className="card">
          <EmptyGuide
            icon={<Users size={22} />}
            title="Nada em aberto"
            text="Divida uma despesa ao editá-la no Orçamento (botão “Dividir”) ou anote aqui o que alguém te deve ou o que você deve."
          />
        </section>
      )}
      {data && data.people.length > 0 && (
        <div className="grid-cards">
          {data.people.map((entry) => (
            <PersonCard key={entry.person} entry={entry} onSettle={() => setSettling({ person: entry.person, balance: Number(entry.balance) })} />
          ))}
        </div>
      )}
      {data && data.history.length > 0 && (
        <details className="details" style={{ marginTop: 20 }}>
          <summary>Acertos recentes</summary>
          <ul className="items">
            {data.history.map((s) => (
              <li key={s.id} className="item">
                <span className="item__main">
                  <span className="item__title">
                    {s.person} · {s.description}
                  </span>
                  <span className="item__meta">Acertado em {shortDate(s.settled_at?.slice(0, 10) ?? null)}</span>
                </span>
                <span className="num muted">{money(s.amount)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      <Sheet open={adding} title="Nova anotação" onClose={() => setAdding(false)}>
        {adding && <ManualForm names={data?.names ?? []} onDone={() => setAdding(false)} />}
      </Sheet>
      <Sheet open={settling !== null} title={`Acertar contas${settling ? ` com ${settling.person}` : ""}`} onClose={() => setSettling(null)}>
        {settling && <SettleForm person={settling.person} balance={settling.balance} onDone={() => setSettling(null)} />}
      </Sheet>
    </>
  );
}
