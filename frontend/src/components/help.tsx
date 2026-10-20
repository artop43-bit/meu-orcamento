import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { CalendarDays, ChartPie, Info, Landmark, Sparkles, Target, Wallet } from "lucide-react";

import { Button, Sheet } from "./ui";

/**
 * Dica curta (ⓘ) ao lado de um campo. É um botão que abre/fecha o texto logo abaixo:
 * funciona com toque, teclado e leitor de tela (não depende de passar o mouse).
 */
export function Tip({ children, label = "Ajuda" }: { children: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const ref = useRef<HTMLSpanElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);

  // A dica nunca sai da janela nem da tela: desloca para o lado que tiver espaço.
  useLayoutEffect(() => {
    const el = textRef.current;
    if (!open || !el) return;
    el.style.setProperty("--tip-shift", "0px");
    const box = el.getBoundingClientRect();
    const area = (el.closest(".sheet__inner") ?? document.documentElement).getBoundingClientRect();
    const left = Math.max(area.left, 0) + 8;
    const right = Math.min(area.right, window.innerWidth) - 8;
    let shift = 0;
    if (box.left < left) shift = left - box.left;
    else if (box.right > right) shift = right - box.right;
    el.style.setProperty("--tip-shift", `${Math.round(shift)}px`);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent && event.key !== "Escape") return;
      if (event instanceof MouseEvent && ref.current?.contains(event.target as Node)) return;
      setOpen(false);
    };
    document.addEventListener("keydown", close);
    document.addEventListener("click", close);
    return () => {
      document.removeEventListener("keydown", close);
      document.removeEventListener("click", close);
    };
  }, [open]);

  return (
    <span className="tip" ref={ref}>
      {/* span com papel de botão (e não <button>): dentro de um <label>, um <button> passaria a ser
          o campo rotulado e o input perderia o nome ("Vencimento", "Dia do recebimento"...). */}
      <span
        role="button"
        tabIndex={0}
        className="tip__btn"
        aria-label={label}
        aria-expanded={open}
        aria-controls={id}
        onClick={(e) => {
          // Dentro de <label>, o clique não pode ir para o campo.
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            e.stopPropagation();
            setOpen((v) => !v);
          }
        }}
      >
        <Info size={14} aria-hidden />
      </span>
      {open && (
        <span id={id} ref={textRef} className="tip__text" role="note">
          {children}
        </span>
      )}
    </span>
  );
}

/** Estado vazio que ensina: o que é a tela, um exemplo e o botão para começar. */
export function EmptyGuide({
  icon,
  title,
  text,
  example,
  action,
}: {
  icon: ReactNode;
  title: string;
  text: ReactNode;
  example?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-guide">
      <span className="kpi__icon kpi__icon--neutral empty-guide__icon" aria-hidden>
        {icon}
      </span>
      <h3>{title}</h3>
      <p className="muted">{text}</p>
      {example && <p className="empty-guide__example small">{example}</p>}
      {action}
    </div>
  );
}

// ---------------------------------------------------------------- tour do 1º acesso

const TOUR_KEY = "tour-v05-visto";
const TOUR_EVENT = "abrir-tour";

type Step = { icon: ReactNode; title: string; text: ReactNode };

const STEPS: Step[] = [
  {
    icon: <Sparkles size={22} />,
    title: "Bem-vindo ao Meu Orçamento",
    text: "Apresentação rápida dos recursos principais. Ela pode ser revista a qualquer momento em Ajustes › Central de ajuda.",
  },
  {
    icon: <Wallet size={22} />,
    title: "Orçamento",
    text: (
      <>
        Registre receitas e despesas do mês. A categoria é sugerida pela descrição (ex.: <em>“Uber”</em> → Transporte), e despesas
        parceladas ou recorrentes são lançadas automaticamente nos meses seguintes. O lançamento rápido aceita frases como
        “mercado 120 pix ontem”.
      </>
    ),
  },
  {
    icon: <CalendarDays size={22} />,
    title: "Calendário",
    text: "Vencimentos, recebimentos, parcelas e faturas por dia. Despesas previstas (IPVA, viagens) entram na projeção e são confirmadas quando ocorrem.",
  },
  {
    icon: <ChartPie size={22} />,
    title: "Insights",
    text: "Score financeiro, regra 50/30/20, projeção de 12 meses e alertas objetivos sobre o mês.",
  },
  {
    icon: <Landmark size={22} />,
    title: "Investimentos e cotações",
    text: "Carteira atualizada pela cotação e acompanhamento de índices, moedas, criptoativos e renda fixa. Conteúdo informativo, sem recomendação de compra ou venda.",
  },
  {
    icon: <Target size={22} />,
    title: "Contas, cartões e metas",
    text: "Saldos por conta, faturas de cartão com melhor dia de compra e metas com aporte mensal calculado.",
  },
];

function readSeen(): boolean {
  try {
    return localStorage.getItem(TOUR_KEY) === "1";
  } catch {
    return true; // Sem armazenamento (privado): não insiste a cada tela.
  }
}

/** Marca a apresentação como vista (a configuração inicial já cumpre esse papel). */
export function markTourSeen() {
  try {
    localStorage.setItem(TOUR_KEY, "1");
  } catch {
    // Navegação privada: tudo bem.
  }
}

/** Abre o tour de qualquer lugar (ex.: botão "Rever o tour" na Ajuda). */
export function openTour() {
  window.dispatchEvent(new Event(TOUR_EVENT));
}

export function Tour() {
  const [open, setOpen] = useState(() => !readSeen() && !navigator.webdriver);
  const [step, setStep] = useState(0);

  useEffect(() => {
    const show = () => {
      setStep(0);
      setOpen(true);
    };
    window.addEventListener(TOUR_EVENT, show);
    return () => window.removeEventListener(TOUR_EVENT, show);
  }, []);

  function close() {
    markTourSeen();
    setOpen(false);
  }

  const current = STEPS[step];
  const last = step === STEPS.length - 1;
  return (
    <Sheet open={open} title={`Apresentação · ${step + 1} de ${STEPS.length}`} onClose={close}>
      <div className="tour stack" aria-live="polite">
        <span className="kpi__icon tour__icon" aria-hidden>
          {current.icon}
        </span>
        <h3 style={{ margin: 0 }}>{current.title}</h3>
        <p style={{ margin: 0 }}>{current.text}</p>
        <div className="tour__dots" aria-hidden>
          {STEPS.map((_, i) => (
            <span key={i} className={i === step ? "is-active" : undefined} />
          ))}
        </div>
        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={close}>
            Pular
          </Button>
          {step > 0 && (
            <Button type="button" variant="secondary" onClick={() => setStep(step - 1)}>
              Voltar
            </Button>
          )}
          <Button type="button" onClick={() => (last ? close() : setStep(step + 1))}>
            {last ? "Concluir" : "Próximo"}
          </Button>
        </div>
      </div>
    </Sheet>
  );
}
