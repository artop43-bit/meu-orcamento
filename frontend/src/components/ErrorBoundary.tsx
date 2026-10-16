import { Component, type ErrorInfo, type ReactNode } from "react";

type State = { error: Error | null };

/**
 * Se uma tela quebrar, mostra um aviso no lugar dela (o menu e o resto do app continuam
 * funcionando) em vez de deixar a página em branco.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Erro na tela:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <section className="card stack" role="alert">
        <h2>Algo deu errado nesta tela</h2>
        <p className="muted" style={{ margin: 0 }}>
          Seus dados estão seguros. Tente de novo; se continuar, recarregue a página.
        </p>
        <div className="row">
          <button type="button" className="btn btn--primary" onClick={() => this.setState({ error: null })}>
            Tentar de novo
          </button>
          <button type="button" className="btn btn--secondary" onClick={() => window.location.reload()}>
            Recarregar
          </button>
        </div>
      </section>
    );
  }
}
