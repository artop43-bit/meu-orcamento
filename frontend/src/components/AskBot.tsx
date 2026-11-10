import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, History, MessageCircleQuestion, Plus, Trash2 } from "lucide-react";
import { Link } from "react-router";

import { useMe } from "../api/auth";
import { errorMessage } from "../api/client";
import { ASK_CONVERSATIONS_KEY, askApi, type AskAnswer, type AskConversation } from "../api/insights";
import { prefersReducedMotion } from "../lib/announce";

const STARTERS = [
  "O que mais gastei este mês?",
  "Qual foi meu maior lançamento?",
  "Quanto posso gastar hoje?",
  "O que vence nos próximos dias?",
  "Quantas parcelas faltam?",
  "Onde encontro as recorrências?",
];

type Turn = { id: number; question: string; answer?: AskAnswer; error?: string };

function dayLabel(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const days = Math.round((new Date(today.toDateString()).getTime() - new Date(date.toDateString()).getTime()) / 86_400_000);
  if (days <= 0) return "Hoje";
  if (days === 1) return "Ontem";
  return date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

/** Tire sua dúvida: perguntas sobre os próprios dados, respondidas pelo próprio site (sem serviço externo). */
export function AskBot() {
  const me = useMe();
  const client = useQueryClient();
  const historyOn = me.data?.ask_history !== false;
  const conversations = useQuery({ queryKey: ASK_CONVERSATIONS_KEY, queryFn: askApi.conversations, enabled: historyOn });
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const list = conversations.data ?? [];

  useEffect(() => {
    if (turns.length) endRef.current?.scrollIntoView({ block: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [turns]);

  async function ask(question: string) {
    const clean = question.trim().slice(0, 200);
    if (!clean || busy) return;
    const id = nextId.current++;
    const context = turns.at(-1)?.answer?.context;
    setTurns((t) => [...t, { id, question: clean }]);
    setText("");
    setBusy(true);
    try {
      const answer = await askApi.ask(clean, conversationId, context);
      setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, answer } : turn)));
      if (answer.conversation_id) {
        setConversationId(answer.conversation_id);
        void client.invalidateQueries({ queryKey: ASK_CONVERSATIONS_KEY });
      }
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

  function startNew() {
    setTurns([]);
    setConversationId(null);
    setShowHistory(false);
    inputRef.current?.focus();
  }

  async function open(conversation: AskConversation) {
    setShowHistory(false);
    setBusy(true);
    try {
      const messages = await askApi.messages(conversation.id);
      setTurns(messages.map((m) => ({ id: nextId.current++, question: m.question, answer: m.answer })));
      setConversationId(conversation.id);
    } catch (error) {
      setTurns([{ id: nextId.current++, question: conversation.title, error: errorMessage(error) }]);
    } finally {
      setBusy(false);
    }
  }

  async function remove(conversation: AskConversation) {
    await askApi.remove(conversation.id);
    if (conversation.id === conversationId) startNew();
    void client.invalidateQueries({ queryKey: ASK_CONVERSATIONS_KEY });
  }

  async function removeAll() {
    await askApi.removeAll();
    startNew();
    void client.invalidateQueries({ queryKey: ASK_CONVERSATIONS_KEY });
  }

  const last = turns.at(-1)?.answer;
  const chips = turns.length === 0 ? STARTERS : (last?.suggestions ?? []);

  return (
    <section className={`card ask ${historyOn ? "ask--history" : ""} ${showHistory ? "is-history-open" : ""}`} aria-label="Tire sua dúvida">
      {historyOn && (
        <aside className="ask__side" aria-label="Conversas anteriores">
          <button type="button" className="btn btn--primary ask__new" onClick={startNew}>
            <Plus size={16} aria-hidden /> Nova conversa
          </button>
          <p className="ask__side-title">Histórico · some após 30 dias</p>
          {list.length === 0 ? (
            <p className="muted small" style={{ margin: 0 }}>
              As conversas aparecem aqui.
            </p>
          ) : (
            <ul className="ask__conversations">
              {list.map((c) => (
                <li key={c.id} className={c.id === conversationId ? "is-current" : ""}>
                  <button type="button" className="ask__conversation" onClick={() => void open(c)} aria-current={c.id === conversationId || undefined}>
                    <span className="ask__conversation-title">{c.title}</span>
                    <span className="ask__conversation-date">{dayLabel(c.updated_at)}</span>
                  </button>
                  <button type="button" className="icon-btn" aria-label={`Apagar a conversa ${c.title}`} title="Apagar" onClick={() => void remove(c)}>
                    <Trash2 size={15} aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="ask__side-foot">
            {list.length > 0 && (
              <button type="button" className="link-btn" onClick={() => void removeAll()}>
                Apagar tudo
              </button>
            )}
            <Link to="/ajustes/preferencias#privacidade">Desligar o histórico</Link>
          </p>
        </aside>
      )}

      <div className="ask__main">
        {historyOn && (
          <button type="button" className="chip-btn ask__history-toggle" aria-expanded={showHistory} onClick={() => setShowHistory((v) => !v)}>
            <History size={15} aria-hidden /> Histórico{list.length > 0 ? ` (${list.length})` : ""}
          </button>
        )}
        {turns.length === 0 && (
          <div className="ask__intro">
            <span className="ask__badge" aria-hidden>
              <MessageCircleQuestion size={20} />
            </span>
            <p>
              Pergunte sobre o que você já cadastrou: gastos por categoria ou lugar, períodos (hoje, semana, mês, ano), vencimentos, faturas,
              parcelas, financiamentos, assinaturas, receitas, metas e investimentos. Também digo onde fica cada coisa no site. Tudo é respondido
              aqui mesmo, com os seus dados, sem serviço externo.{" "}
              {historyOn ? "As conversas ficam guardadas por 30 dias." : "O histórico está desligado: nada é guardado."}
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
            placeholder={turns.length ? "Continue: “e em setembro?”, “e com uber?”" : "Ex.: quanto gastei com mercado em outubro?"}
            autoComplete="off"
            enterKeyHint="send"
          />
          <button type="submit" className="icon-btn ask__send" aria-label="Perguntar" disabled={busy || !text.trim()}>
            <ArrowUp size={18} aria-hidden />
          </button>
        </form>
      </div>
    </section>
  );
}
