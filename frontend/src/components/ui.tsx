import {
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type PointerEvent,
  type ReactNode,
} from "react";
import { BarChart3, ChartPie, ShieldCheck, Target, Wallet, X } from "lucide-react";
import { Link } from "react-router";

import { prefersReducedMotion } from "../lib/announce";
import { haptic } from "../lib/haptics";

export function Brand({ to }: { to?: string }) {
  const content = (
    <>
      <span className="brand__logo" aria-hidden>
        <Wallet size={18} />
      </span>
      Meu Orçamento
    </>
  );
  return to ? (
    <Link to={to} className="brand">
      {content}
    </Link>
  ) : (
    <p className="brand">{content}</p>
  );
}

/** Telas de entrada: tela dividida no desktop (marca + formulário), tela cheia no celular. */
export function AuthLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="auth">
      <aside className="auth__aside">
        <Brand />
        <div>
          <p className="auth__headline">Seu dinheiro organizado, mês a mês.</p>
          <ul className="auth__features">
            <li>
              <Wallet size={20} /> Contas fixas, parcelas e metas num só lugar
            </li>
            <li>
              <ChartPie size={20} /> Para onde vai cada real, por categoria
            </li>
            <li>
              <BarChart3 size={20} /> Score, projeção de 12 meses e simulador
            </li>
            <li>
              <Target size={20} /> Metas com quanto falta e quanto guardar
            </li>
            <li>
              <ShieldCheck size={20} /> Verificação em duas etapas e dados só seus
            </li>
          </ul>
        </div>
        <p className="small" style={{ opacity: 0.7, margin: 0 }}>
          Seus dados não são vendidos nem usados para publicidade.
        </p>
      </aside>
      <div className="auth__panel">
        <div className="auth__card">
          <Brand />
          <h1>{title}</h1>
          {children}
        </div>
        <footer className="footer">
          <Link to="/privacidade">Privacidade</Link>
          <Link to="/termos">Termos de uso</Link>
        </footer>
      </div>
    </main>
  );
}

/** Título da página com subtítulo e ações (botões) à direita. */
export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        {typeof title === "string" ? <h1>{title}</h1> : title}
        {subtitle && <p className="page-header__sub">{subtitle}</p>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  );
}

/** Cartão de indicador (renda, saldo, etc.). */
export function Kpi({
  icon,
  label,
  value,
  foot,
  tone = "accent",
  valueClass,
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  foot?: ReactNode;
  tone?: "accent" | "expense" | "neutral";
  valueClass?: string;
}) {
  return (
    <div className="kpi">
      <div className="kpi__head">
        <span className={`kpi__icon ${tone === "accent" ? "" : `kpi__icon--${tone}`}`} aria-hidden>
          {icon}
        </span>
        {label}
      </div>
      <div className={`kpi__value ${valueClass ?? ""}`}>{value}</div>
      {foot && <div className="kpi__foot">{foot}</div>}
    </div>
  );
}

/**
 * Janela de formulário: modal centralizado no desktop, bottom sheet no celular.
 * Usa o <dialog> nativo (foco preso, Esc fecha, acessível).
 */
export function Sheet({
  open,
  title,
  onClose,
  children,
  wide,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  // Mantém o conteúdo na tela enquanto a janela anima a saída.
  const [rendered, setRendered] = useState(open);
  const titleId = useId();
  const drag = useRef<{ y: number; t: number; dy: number } | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open) {
      setRendered(true);
      dialog.classList.remove("is-closing");
      if (!dialog.open) {
        // O campo com autoFocus já recebeu o foco ao montar; showModal() o levaria para o
        // primeiro botão (o X). Devolve o foco a ele.
        const focused = document.activeElement;
        dialog.showModal();
        if (focused instanceof HTMLElement && focused !== document.body && dialog.contains(focused)) focused.focus();
      }
      return;
    }
    if (!dialog.open) return;
    const finish = () => {
      dialog.classList.remove("is-closing");
      dialog.style.transition = "";
      dialog.style.transform = "";
      if (dialog.open) dialog.close();
      setRendered(false);
    };
    // Já saiu arrastando, ou animações desligadas no sistema: fecha direto.
    if (dialog.dataset.dragged || prefersReducedMotion()) {
      delete dialog.dataset.dragged;
      finish();
      return;
    }
    dialog.classList.add("is-closing");
    const timer = window.setTimeout(finish, 180);
    return () => window.clearTimeout(timer);
  }, [open]);

  // Celular: arrastar a alça (ou o título) para baixo fecha a janela.
  function onDragStart(e: PointerEvent<HTMLDivElement>) {
    if (e.pointerType === "mouse" || (e.target as Element).closest("button")) return;
    drag.current = { y: e.clientY, t: e.timeStamp, dy: 0 };
    e.currentTarget.setPointerCapture(e.pointerId);
    ref.current!.style.transition = "none";
  }

  function onDragMove(e: PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    const dy = Math.max(0, e.clientY - drag.current.y);
    drag.current.dy = dy;
    ref.current!.style.transform = `translateY(${dy}px)`;
  }

  function onDragEnd(e: PointerEvent<HTMLDivElement>) {
    const state = drag.current;
    const dialog = ref.current;
    drag.current = null;
    if (!state || !dialog) return;
    const velocity = state.dy / Math.max(e.timeStamp - state.t, 1);
    if (state.dy > dialog.offsetHeight / 3 || (velocity > 0.5 && state.dy > 40)) {
      haptic("tap");
      dialog.style.transition = "transform 0.18s ease-in";
      dialog.style.transform = "translateY(100%)";
      dialog.dataset.dragged = "1";
      window.setTimeout(onClose, 170);
    } else {
      dialog.style.transition = "transform 0.25s cubic-bezier(0.2, 0.8, 0.2, 1)";
      dialog.style.transform = "";
    }
  }

  const dragProps = {
    onPointerDown: onDragStart,
    onPointerMove: onDragMove,
    onPointerUp: onDragEnd,
    onPointerCancel: onDragEnd,
  };

  return (
    <dialog
      ref={ref}
      className={`sheet ${wide ? "sheet--wide" : ""}`}
      aria-labelledby={titleId}
      // Só ações do usuário (Esc, X, clique fora) chamam onClose. O fechamento feito pelo
      // código ao trocar de janela não pode, senão anularia a próxima janela que está abrindo.
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      // Clique fora (no fundo escuro) fecha.
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      {(open || rendered) && (
        <div className="sheet__inner">
          <div className="sheet__grab" {...dragProps}>
            <div className="sheet__handle" aria-hidden />
          </div>
          <div className="sheet__header" {...dragProps}>
            <h2 id={titleId}>{title}</h2>
            <button type="button" className="icon-btn" aria-label="Fechar" onClick={onClose}>
              <X size={20} />
            </button>
          </div>
          <div className="sheet__body">{children}</div>
        </div>
      )}
    </dialog>
  );
}

type FieldProps = InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string };

export function Field({ label, hint, id, ...props }: FieldProps) {
  const fieldId = id ?? props.name;
  return (
    <div className="field">
      <label htmlFor={fieldId}>{label}</label>
      <input id={fieldId} {...props} />
      {hint && <small className="muted">{hint}</small>}
    </div>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  loading?: boolean;
  variant?: "primary" | "secondary" | "danger";
  block?: boolean;
};

export function Button({
  loading,
  variant = "primary",
  block,
  children,
  disabled,
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      className={`btn btn--${variant} ${block ? "btn--block" : ""} ${className ?? ""}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? "Aguarde…" : children}
    </button>
  );
}

export function Alert({ tone, children }: { tone: "error" | "success" | "info"; children: ReactNode }) {
  if (!children) return null;
  return (
    <div className={`alert alert--${tone}`} role={tone === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

/** Blocos cinza pulsando no lugar do conteúdo enquanto ele carrega (evita a tela "pular"). */
export function Skeleton({ height = 16, width, radius }: { height?: number; width?: string; radius?: number }) {
  return <span className="skeleton" style={{ height, width, borderRadius: radius }} aria-hidden />;
}

export function LoadingRegion({ label = "Carregando", children }: { label?: string; children: ReactNode }) {
  return (
    <div role="status" aria-label={label} aria-busy="true">
      {children}
    </div>
  );
}
