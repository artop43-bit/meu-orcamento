import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ME_KEY, useMe, type User } from "../api/auth";
import { budgetApi } from "../api/budget";
import { errorMessage } from "../api/client";
import { inboxApi } from "../api/inbox";
import { announce } from "../lib/announce";
import { money, thisMonth } from "../lib/format";
import { Bar, MoneyInput, requireMoney } from "./budget";
import { Tip } from "./help";
import { Alert, Button } from "./ui";

const DAS = "DAS do MEI";

/** Preferências › Pix e MEI (v1.4): chave para cobrar nas Divisões e a opção "Sou MEI". */
export function PixMeiSettings() {
  const queryClient = useQueryClient();
  const { data: user } = useMe();
  const [key, setKey] = useState(user?.pix_key ?? "");
  const [name, setName] = useState(user?.pix_name ?? user?.display_name ?? "");
  const [city, setCity] = useState(user?.pix_city ?? "");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  const mei = user?.mei ?? false;

  async function save(data: Parameters<typeof inboxApi.financeSettings>[0], message: string) {
    setError("");
    setSaved("");
    setBusy(true);
    try {
      const out = await inboxApi.financeSettings(data);
      queryClient.setQueryData<User | null>(ME_KEY, (u) => (u ? { ...u, ...out } : u));
      if (out.pix_key) setKey(out.pix_key);
      setSaved(message);
      announce(message);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void save({ pix_key: key.trim() || null, pix_name: name.trim() || null, pix_city: city.trim() || null }, "Chave Pix salva");
  }

  return (
    <section className="card stack" id="pix">
      <h2>Pix e MEI</h2>
      <Alert tone="error">{error}</Alert>
      {saved && <Alert tone="success">{saved}</Alert>}
      <form className="stack stack--tight" onSubmit={submit}>
        <label>
          <span className="field-label">
            Chave Pix <Tip>Usada para cobrar quem te deve em Divisões. Vale CPF, CNPJ, celular, e-mail ou chave aleatória.</Tip>
          </span>
          <input value={key} onChange={(e) => setKey(e.target.value)} maxLength={80} placeholder="CPF, celular, e-mail ou chave aleatória" autoComplete="off" />
        </label>
        <div className="grid-2">
          <label>
            Nome no Pix
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={25} placeholder="Como aparece para quem paga" />
          </label>
          <label>
            Cidade
            <input value={city} onChange={(e) => setCity(e.target.value)} maxLength={15} placeholder="Ex.: Goiânia" />
          </label>
        </div>
        <div>
          <Button type="submit" variant="secondary" loading={busy}>
            Salvar chave Pix
          </Button>
        </div>
      </form>
      <label className="check" id="mei">
        <input type="checkbox" checked={mei} onChange={(e) => void save({ mei: e.target.checked }, e.target.checked ? "MEI ligado" : "MEI desligado")} />
        Sou MEI (microempreendedor individual)
      </label>
      {mei && <MeiPanel />}
    </section>
  );
}

function MeiPanel() {
  const queryClient = useQueryClient();
  const summary = useQuery({ queryKey: ["budget", "mei"], queryFn: inboxApi.mei });
  const recurring = useQuery({ queryKey: ["budget", "recurring"], queryFn: budgetApi.recurring });
  const hasDas = (recurring.data ?? []).some((r) => r.description === DAS && !r.end_month);
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const data = summary.data;

  async function createDas(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await budgetApi.createRecurring({ kind: "expense", description: DAS, amount: requireMoney(amount), due_day: 20, start_month: thisMonth() });
      await queryClient.invalidateQueries({ queryKey: ["budget"] });
      announce("Lembrete do DAS criado");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack stack--tight mei-panel">
      {data && (
        <>
          <p style={{ margin: 0 }}>
            Faturamento de {data.year}: <strong>{money(data.total)}</strong> de {money(data.limit)} ({data.pct.toLocaleString("pt-BR")}%)
          </p>
          <Bar pct={Math.min(data.pct, 100)} color={data.pct >= 100 ? "var(--error)" : data.pct >= 80 ? "var(--warn)" : "var(--positive)"} />
          <p className="muted small" style={{ margin: 0 }}>
            Conta as receitas marcadas como “Faturamento do MEI”. Em 80% do teto chega um aviso.
          </p>
        </>
      )}
      {hasDas ? (
        <p className="muted small" style={{ margin: 0 }}>
          Lembrete do DAS ativo: conta fixa todo dia 20, com aviso de vencimento.
        </p>
      ) : (
        <form className="row mei-panel__das" onSubmit={createDas}>
          <label>
            <span className="field-label">
              Valor do DAS <Tip>Cria a conta fixa “DAS do MEI” com vencimento todo dia 20, com os lembretes de vencimento do app.</Tip>
            </span>
            <MoneyInput value={amount} onChange={setAmount} />
          </label>
          <Button type="submit" variant="secondary" loading={busy}>
            Criar lembrete do DAS
          </Button>
        </form>
      )}
      <Alert tone="error">{error}</Alert>
    </div>
  );
}
