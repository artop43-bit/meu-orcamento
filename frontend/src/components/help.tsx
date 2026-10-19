import { useEffect, useId, useRef, useState, type ReactNode } from "react";
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
      <button
        type="button"
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
      >
        <Info size={14} aria-hidden />
      </button>
      {open && (
        <span id={id} className="tip__text" role="note">
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
    text: "Um tour rápido de 5 passos. Pode pular quando quiser e rever depois em Ajuda.",
  },
  {
    icon: <Wallet size={22} />,
    title: "Orçamento: renda e contas do mês",
    text: (
      <>
        Lance quanto entra (salário, bicos) e o que sai. Ao digitar a descrição, a categoria é sugerida sozinha
        (ex.: <em>“Uber”</em> → Transporte). Contas que se repetem, parcelas e frequência (mensal, anual…) ficam no mesmo
        formulário.
      </>
    ),
  },
  {
    icon: <CalendarDays size={22} />,
    title: "Calendário",
    text: "Veja vencimentos, recebimentos e parcelas por dia. Planeje gastos futuros (aniversário, IPVA, viagem): eles entram na previsão e viram lançamento com um toque.",
  },
  {
    icon: <ChartPie size={22} />,
    title: "Análise financeira e consultor",
    text: "Score, regra 50/30/20, projeção dos próximos meses e um consultor que explica o mês em linguagem simples.",
  },
  {
    icon: <Landmark size={22} />,
    title: "Investimentos e Mercado",
    text: "Registre sua carteira (com código e quantidade, o valor se atualiza pela cotação) e acompanhe índices, moedas, cripto e renda fixa. É informativo: o app não recomenda compra ou venda.",
  },
  {
    icon: <Target size={22} />,
    title: "Metas",
    text: "Defina objetivos (reserva, viagem) e acompanhe quanto falta. Pronto! Em Ajuda há exemplos de cada tela.",
  },
];

function readSeen(): boolean {
  try {
    return localStorage.getItem(TOUR_KEY) === "1";
  } catch {
    return true; // Sem armazenamento (privado): não insiste a cada tela.
  }
}

function markSeen() {
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
    markSeen();
    setOpen(false);
  }

  const current = STEPS[step];
  const last = step === STEPS.length - 1;
  return (
    <Sheet open={open} title={`Tour rápido · ${step + 1} de ${STEPS.length}`} onClose={close}>
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
            Pular tour
          </Button>
          {step > 0 && (
            <Button type="button" variant="secondary" onClick={() => setStep(step - 1)}>
              Voltar
            </Button>
          )}
          <Button type="button" onClick={() => (last ? close() : setStep(step + 1))}>
            {last ? "Começar" : "Próximo"}
          </Button>
        </div>
      </div>
    </Sheet>
  );
}
