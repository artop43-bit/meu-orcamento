import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Plus, X } from "lucide-react";

import { ME_KEY } from "../api/auth";
import { budgetApi, type GoalKind } from "../api/budget";
import { api, errorMessage } from "../api/client";
import { extrasApi } from "../api/extras";
import { DayField } from "../components/DateField";
import { markTourSeen } from "../components/help";
import { MoneyInput, requireMoney } from "../components/budget";
import { Alert, Button, Sheet } from "../components/ui";
import { money, parseMoney, thisMonth } from "../lib/format";
import { GOAL_KINDS } from "../lib/goals";

const STEPS = ["Receita", "Contas fixas", "Cartão", "Meta"];
const FIXED_SUGGESTIONS = ["Aluguel", "Condomínio", "Energia", "Água", "Internet", "Plano de celular", "Academia", "Streaming"];

type FixedRow = { description: string; amount: string; day: string };

/**
 * Configuração inicial guiada: receita, contas fixas, cartão e uma meta, em poucos passos.
 * Todas as etapas podem ser puladas; ao concluir (ou pular tudo) não aparece de novo.
 */
export default function Onboarding({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const month = thisMonth();
  const [step, setStep] = useState(-1);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<string[]>([]);
  // Etapa 1
  const [incomeName, setIncomeName] = useState("Salário");
  const [incomeAmount, setIncomeAmount] = useState("");
  const [incomeDay, setIncomeDay] = useState("");
  // Etapa 2
  const [rows, setRows] = useState<FixedRow[]>([{ description: "", amount: "", day: "" }]);
  // Etapa 3
  const [cardName, setCardName] = useState("");
  const [closing, setClosing] = useState("");
  const [due, setDue] = useState("");
  // Etapa 4
  const [goalKind, setGoalKind] = useState<GoalKind>("emergency");
  const [goalName, setGoalName] = useState("Reserva de emergência");
  const [goalAmount, setGoalAmount] = useState("");
  const [goalMonthly, setGoalMonthly] = useState("");

  async function finish() {
    markTourSeen();
    try {
      await api.post("/onboarding/done");
    } finally {
      await queryClient.invalidateQueries({ queryKey: ME_KEY });
      await queryClient.invalidateQueries({ queryKey: ["budget"] });
      onClose();
    }
  }

  async function next(skip = false) {
    setError("");
    if (skip) {
      setStep((s) => s + 1);
      return;
    }
    setBusy(true);
    try {
      if (step === 0 && incomeAmount.trim()) {
        await budgetApi.createIncome(month, {
          description: incomeName.trim() || "Salário",
          amount: requireMoney(incomeAmount),
          income_type: "fixed",
          day: incomeDay ? Number(incomeDay) : null,
          repeat: "monthly",
        });
        setSummary((s) => [...s, `Receita mensal: ${incomeName} de ${money(parseMoney(incomeAmount) ?? 0)}`]);
      }
      if (step === 1) {
        const filled = rows.filter((r) => r.description.trim() && r.amount.trim());
        for (const r of filled) {
          const day = r.day ? Math.min(Number(r.day), 28) : null;
          await budgetApi.createExpense(month, {
            description: r.description.trim(),
            amount: requireMoney(r.amount),
            due_date: day ? `${month}-${String(day).padStart(2, "0")}` : null,
            repeat: true,
            interval_months: 1,
          });
        }
        if (filled.length) setSummary((s) => [...s, `${filled.length} conta(s) fixa(s) mensal(is)`]);
      }
      if (step === 2 && cardName.trim()) {
        await extrasApi.createCard({
          name: cardName.trim(),
          kind: "credit",
          limit_amount: null,
          closing_day: Number(closing),
          due_day: Number(due),
          color: null,
        });
        setSummary((s) => [...s, `Cartão ${cardName.trim()}`]);
      }
      if (step === 3 && goalAmount.trim()) {
        await budgetApi.createGoal({
          name: goalName.trim() || "Minha meta",
          kind: goalKind,
          target_amount: requireMoney(goalAmount),
          monthly_plan: goalMonthly.trim() ? requireMoney(goalMonthly) : null,
          is_main: true,
        });
        setSummary((s) => [...s, `Meta: ${goalName}`]);
      }
      setStep((s) => s + 1);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void next();
  }

  const title = step === -1 ? "Configuração inicial" : step >= STEPS.length ? "Orçamento configurado" : `Configuração inicial · ${step + 1} de ${STEPS.length}`;

  return (
    <Sheet open title={title} onClose={() => void finish()}>
      {step === -1 && (
        <div className="stack">
          <p style={{ margin: 0 }}>
            Em poucos passos, o orçamento do mês fica pronto: receita, contas fixas, cartão de crédito e uma meta. Cada etapa pode ser
            pulada e tudo pode ser alterado depois.
          </p>
          <ol className="onboarding-list">
            {STEPS.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          <div className="form-actions">
            <Button type="button" variant="secondary" onClick={() => void finish()}>
              Configurar depois
            </Button>
            <Button type="button" onClick={() => setStep(0)}>
              Começar
            </Button>
          </div>
        </div>
      )}

      {step >= 0 && step < STEPS.length && (
        <form className="inline-form" onSubmit={submit}>
          <ol className="steps steps--compact" aria-label="Etapas">
            {STEPS.map((label, i) => (
              <li key={label} className={i === step ? "is-current" : i < step ? "is-done" : undefined} aria-current={i === step ? "step" : undefined}>
                <span className="steps__number">{i + 1}</span>
                {label}
              </li>
            ))}
          </ol>
          <Alert tone="error">{error}</Alert>

          {step === 0 && (
            <>
              <p className="muted" style={{ margin: 0 }}>
                Sua principal receita mensal. Ela é lançada todo mês automaticamente.
              </p>
              <label>
                Descrição
                <input value={incomeName} onChange={(e) => setIncomeName(e.target.value)} maxLength={120} />
              </label>
              <div className="grid-2">
                <label>
                  Valor
                  <MoneyInput value={incomeAmount} onChange={setIncomeAmount} required={false} />
                </label>
                <label>
                  Dia do recebimento
                  <DayField value={incomeDay} onChange={setIncomeDay} recurring />
                </label>
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <p className="muted" style={{ margin: 0 }}>
                Contas que se repetem todo mês. Toque numa sugestão para adicionar.
              </p>
              <div className="chips" role="group" aria-label="Sugestões de contas fixas">
                {FIXED_SUGGESTIONS.filter((name) => !rows.some((r) => r.description === name)).map((name) => (
                  <button
                    key={name}
                    type="button"
                    className="chip-btn"
                    onClick={() => {
                      const empty = rows.findIndex((r) => !r.description);
                      const next = [...rows];
                      if (empty >= 0) next[empty] = { ...next[empty]!, description: name };
                      else next.push({ description: name, amount: "", day: "" });
                      setRows(next);
                    }}
                  >
                    <Plus size={14} aria-hidden /> {name}
                  </button>
                ))}
              </div>
              <ul className="fixed-rows">
                {rows.map((row, i) => (
                  <li key={i} className="fixed-row">
                    <label>
                      <span className="sr-only">Conta {i + 1}</span>
                      <input
                        value={row.description}
                        placeholder="Descrição"
                        aria-label={`Descrição da conta ${i + 1}`}
                        maxLength={120}
                        onChange={(e) => setRows(rows.map((r, j) => (j === i ? { ...r, description: e.target.value } : r)))}
                      />
                    </label>
                    <MoneyInput
                      value={row.amount}
                      required={false}
                      label={`Valor da conta ${i + 1}`}
                      onChange={(v) => setRows(rows.map((r, j) => (j === i ? { ...r, amount: v } : r)))}
                    />
                    <DayField
                      value={row.day}
                      recurring
                      label={`Dia do vencimento da conta ${i + 1}`}
                      onChange={(v) => setRows(rows.map((r, j) => (j === i ? { ...r, day: v } : r)))}
                    />
                    {rows.length > 1 && (
                      <button type="button" className="icon-btn" aria-label={`Remover conta ${i + 1}`} onClick={() => setRows(rows.filter((_, j) => j !== i))}>
                        <X size={16} />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              <div>
                <Button type="button" variant="secondary" onClick={() => setRows([...rows, { description: "", amount: "", day: "" }])}>
                  <Plus size={16} /> Adicionar conta
                </Button>
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <p className="muted" style={{ margin: 0 }}>
                Cartão de crédito principal. As compras no crédito vão para a fatura certa pelo dia de fechamento.
              </p>
              <label>
                Nome do cartão
                <input value={cardName} onChange={(e) => setCardName(e.target.value)} maxLength={60} placeholder="Ex.: Nubank" />
              </label>
              <div className="grid-2 grid-2--even">
                <label>
                  Dia do fechamento
                  <DayField value={closing} onChange={setClosing} recurring required={Boolean(cardName.trim())} />
                </label>
                <label>
                  Dia do vencimento
                  <DayField value={due} onChange={setDue} recurring required={Boolean(cardName.trim())} />
                </label>
              </div>
            </>
          )}

          {step === 3 && (
            <>
              <p className="muted" style={{ margin: 0 }}>
                Um objetivo para acompanhar no Orçamento. A reserva de emergência é o ponto de partida recomendado.
              </p>
              <label>
                Tipo de objetivo
                <select
                  value={goalKind}
                  onChange={(e) => {
                    const kind = e.target.value as GoalKind;
                    setGoalKind(kind);
                    setGoalName(GOAL_KINDS.find((k) => k.value === kind)?.example ?? "");
                  }}
                >
                  {GOAL_KINDS.map((k) => (
                    <option key={k.value} value={k.value}>
                      {k.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Nome da meta
                <input value={goalName} onChange={(e) => setGoalName(e.target.value)} maxLength={80} />
              </label>
              <div className="grid-2">
                <label>
                  Valor total
                  <MoneyInput value={goalAmount} onChange={setGoalAmount} required={false} />
                </label>
                <label>
                  Valor por mês
                  <MoneyInput value={goalMonthly} onChange={setGoalMonthly} required={false} placeholder="Opcional" />
                </label>
              </div>
            </>
          )}

          <div className="form-actions">
            <Button type="button" variant="secondary" onClick={() => void next(true)}>
              Pular etapa
            </Button>
            <Button type="submit" loading={busy}>
              {step === STEPS.length - 1 ? "Concluir" : "Continuar"}
            </Button>
          </div>
        </form>
      )}

      {step >= STEPS.length && (
        <div className="stack">
          <p style={{ margin: 0 }}>
            <CheckCircle2 size={18} aria-hidden className="tone--ok" /> Configuração concluída.
          </p>
          {summary.length > 0 ? (
            <ul className="small">
              {summary.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          ) : (
            <p className="muted small" style={{ margin: 0 }}>
              Nenhuma etapa preenchida. Use “Nova receita” e “Nova despesa” no Orçamento quando quiser.
            </p>
          )}
          <div className="form-actions">
            <Button type="button" onClick={() => void finish()}>
              Ir para o orçamento
            </Button>
          </div>
        </div>
      )}
    </Sheet>
  );
}
