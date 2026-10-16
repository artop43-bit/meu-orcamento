import {
  useEffect,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";
import { BarChart3, ChartPie, ShieldCheck, Target, Wallet, X } from "lucide-react";
import { Link } from "react-router";

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

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={`sheet ${wide ? "sheet--wide" : ""}`}
      aria-label={title}
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
      {open && (
        <div className="sheet__inner">
          <div className="sheet__handle" aria-hidden />
          <div className="sheet__header">
            <h2>{title}</h2>
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
