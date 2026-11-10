import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUp, MessageCircleQuestion } from "lucide-react";
import { Link } from "react-router";

import { askApi, type AskAnswer } from "../api/insights";
import { errorMessage } from "../api/client";
import { prefersReducedMotion } from "../lib/announce";

const STARTERS = [
  "O que mais gastei este mês?",
  "Qual mês gastei mais este ano?",
  "Quando gastei mais em alimentação?",
  "O que vence nos próximos dias?",
  "Onde encontro as recorrências?",
];

type Turn = { id: number; question: string; answer?: AskAnswer; error?: string };

/** Tire sua dúvida: perguntas sobre os próprios dados, respondidas pelo próprio site (sem IA externa). */
export function AskBot() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (turns.length) endRef.current?.scrollIntoView({ block: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [turns]);

  async function ask(question: string) {
    const clean = question.trim().slice(0, 200);
    if (!clean || busy) return;
    const id = nextId.current++;
    setTurns((t) => [...t, { id, question: clean }]);
    setText("");
    setBusy(true);
    try {
      const answer = await askApi.ask(clean);
      setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, answer } : turn)));
    } catch (error) {
      setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, error: errorMessage(error) } : turn)));
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(text);
  }

  const last = turns.at(-1)?.answer;
  const chips = turns.length === 0 ? STARTERS : (last?.suggestions ?? []);

  return (
    <section className="card ask" aria-label="Tire sua dúvida">
      {turns.length === 0 && (
        <div className="ask__intro">
          <span className="ask__badge" aria-hidden>
            <MessageCircleQuestion size={20} />
          </span>
          <p>
            Pergunte sobre o que você já cadastrou: gastos por categoria ou lugar, meses, vencimentos, cartões, receitas e metas. Também
            digo onde fica cada coisa no site. Tudo é respondido aqui mesmo, com os seus dados, e a pergunta não fica salva.
          </p>
        </div>
      )}

      <div className="ask__log" aria-live="polite">
        {turns.map((turn) => (
          <div className="ask__turn" key={turn.id}>
            <p className="ask__q">{turn.question}</p>
            {!turn.answer && !turn.error && (
              <p className="ask__a ask__a--wait" role="status">
                Procurando nos seus lançamentos…
              </p>
            )}
            {turn.error && (
              <p className="ask__a ask__a--error" role="alert">
                {turn.error}
              </p>
            )}
            {turn.answer && (
              <div className="ask__a">
                <p>{turn.answer.answer}</p>
                {turn.answer.items.length > 0 && (
                  <ul className="ask__items">
                    {turn.answer.items.map((item, i) => {
                      const body = (
                        <>
                          <span className="ask__item-main">
                            <span className="ask__item-label">{item.label}</span>
                            {item.detail && <span className="ask__item-detail">{item.detail}</span>}
                          </span>
                          {item.value && <span className="ask__item-value">{item.value}</span>}
                        </>
                      );
                      return <li key={i}>{item.link ? <Link to={item.link}>{body}</Link> : <span>{body}</span>}</li>;
                    })}
                  </ul>
                )}
                {turn.answer.links.length > 0 && (
                  <p className="ask__links">
                    {turn.answer.links.map((link) => (
                      <Link key={link.to + link.label} to={link.to} className="chip-btn">
                        {link.label} ›
                      </Link>
                    ))}
                  </p>
                )}
              </div>
            )}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {chips.length > 0 && (
        <div className="ask__chips" aria-label="Sugestões de pergunta" role="group">
          {chips.map((chip) => (
            <button key={chip} type="button" className="chip-btn" onClick={() => void ask(chip)} disabled={busy}>
              {chip}
            </button>
          ))}
        </div>
      )}

      <form className="ask__form" onSubmit={submit}>
        <label className="sr-only" htmlFor="ask-input">
          Sua pergunta
        </label>
        <input
          id="ask-input"
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={200}
          placeholder="Ex.: quanto gastei com mercado em outubro?"
          autoComplete="off"
          enterKeyHint="send"
        />
        <button type="submit" className="icon-btn ask__send" aria-label="Perguntar" disabled={busy || !text.trim()}>
          <ArrowUp size={18} aria-hidden />
        </button>
      </form>
    </section>
  );
}
