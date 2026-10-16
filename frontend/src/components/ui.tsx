import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router";

export function AuthLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="auth">
      <div className="auth__card">
        <p className="brand">Meu Orçamento</p>
        <h1>{title}</h1>
        {children}
      </div>
      <footer className="footer">
        <Link to="/privacidade">Privacidade</Link>
        <Link to="/termos">Termos de uso</Link>
      </footer>
    </main>
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
};

export function Button({ loading, variant = "primary", children, disabled, ...props }: ButtonProps) {
  return (
    <button className={`btn btn--${variant}`} disabled={disabled || loading} {...props}>
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
