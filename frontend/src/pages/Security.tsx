import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { QRCodeSVG } from "qrcode.react";

import { authApi, ME_KEY, useMe } from "../api/auth";
import { errorMessage } from "../api/client";
import { ActivitySection, DeleteAccountSection, SessionsSection } from "../components/account";
import { Alert, Button, Field } from "../components/ui";
import { MIN_PASSWORD } from "./Register";

const TWO_FACTOR_KEY = ["auth", "2fa"] as const;

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const text = codes.join("\n");
  return (
    <div className="stack">
      <Alert tone="info">
        Guarde estes códigos em local seguro (gerenciador de senhas ou papel). Cada um funciona uma
        única vez, caso você perca o celular. Eles não serão mostrados de novo.
      </Alert>
      <pre className="codes">{text}</pre>
      <div className="row">
        <Button type="button" variant="secondary" onClick={() => navigator.clipboard.writeText(text)}>
          Copiar
        </Button>
        <Button type="button" onClick={onDone}>
          Já guardei
        </Button>
      </div>
    </div>
  );
}

function TwoFactorSection() {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: TWO_FACTOR_KEY, queryFn: authApi.twoFactorStatus });
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [disabling, setDisabling] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function refresh() {
    queryClient.invalidateQueries({ queryKey: TWO_FACTOR_KEY });
    queryClient.invalidateQueries({ queryKey: ME_KEY });
  }

  async function run(action: () => Promise<void>) {
    setError("");
    setLoading(true);
    try {
      await action();
      setCode("");
      setPassword("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  const start = () => run(async () => setSetup(await authApi.twoFactorSetup()));

  const confirm = (event: FormEvent) => {
    event.preventDefault();
    return run(async () => {
      const result = await authApi.twoFactorEnable(code);
      setSetup(null);
      setCodes(result.recovery_codes);
      refresh();
    });
  };

  const disable = (event: FormEvent) => {
    event.preventDefault();
    return run(async () => {
      await authApi.twoFactorDisable(password, code);
      setDisabling(false);
      refresh();
    });
  };

  const regenerate = (event: FormEvent) => {
    event.preventDefault();
    return run(async () => {
      setCodes((await authApi.regenerateRecoveryCodes(code)).recovery_codes);
      refresh();
    });
  };

  if (codes) return <RecoveryCodes codes={codes} onDone={() => setCodes(null)} />;
  if (status.isPending) return <p className="muted">Carregando…</p>;
  if (status.isError) return <Alert tone="error">{errorMessage(status.error)}</Alert>;

  if (!status.data.enabled) {
    if (!setup) {
      return (
        <div className="stack">
          <p className="muted">
            Além da senha, peça um código do celular ao entrar. Funciona com Google Authenticator,
            Microsoft Authenticator, Authy, 1Password e similares.
          </p>
          <Alert tone="error">{error}</Alert>
          <div>
            <Button type="button" onClick={start} loading={loading}>
              Ativar verificação em duas etapas
            </Button>
          </div>
        </div>
      );
    }
    return (
      <form onSubmit={confirm} className="form">
        <p>1. Escaneie o QR code com seu aplicativo autenticador:</p>
        <div className="qr">
          <QRCodeSVG value={setup.otpauth_uri} size={176} marginSize={2} />
        </div>
        <p className="muted">
          Não consegue escanear? Digite esta chave no aplicativo: <code>{setup.secret}</code>
        </p>
        <p>2. Digite o código de 6 dígitos que aparece no aplicativo:</p>
        <Alert tone="error">{error}</Alert>
        <Field
          label="Código"
          name="code"
          inputMode="numeric"
          autoComplete="one-time-code"
          required
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
        <div className="row">
          <Button type="button" variant="secondary" onClick={() => setSetup(null)}>
            Cancelar
          </Button>
          <Button type="submit" loading={loading}>
            Ativar
          </Button>
        </div>
      </form>
    );
  }

  return (
    <div className="stack">
      <Alert tone="success">A verificação em duas etapas está ativa.</Alert>
      <p className="muted">
        Códigos de recuperação restantes: <strong>{status.data.recovery_codes_remaining}</strong>
      </p>
      <Alert tone="error">{error}</Alert>
      {disabling ? (
        <form onSubmit={disable} className="form">
          <Field
            label="Senha"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Field
            label="Código do aplicativo ou de recuperação"
            name="code"
            autoComplete="one-time-code"
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <div className="row">
            <Button type="button" variant="secondary" onClick={() => setDisabling(false)}>
              Cancelar
            </Button>
            <Button type="submit" variant="danger" loading={loading}>
              Desativar
            </Button>
          </div>
        </form>
      ) : (
        <form onSubmit={regenerate} className="form">
          <Field
            label="Código do aplicativo"
            name="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            hint="Necessário para gerar novos códigos de recuperação (os antigos deixam de valer)."
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <div className="row">
            <Button type="submit" variant="secondary" loading={loading}>
              Gerar novos códigos
            </Button>
            <Button type="button" variant="danger" onClick={() => setDisabling(true)}>
              Desativar 2FA
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}

function ChangePasswordSection() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setDone("");
    if (next !== confirm) {
      setError("As senhas não conferem.");
      return;
    }
    setLoading(true);
    try {
      await authApi.changePassword(current, next);
      setDone("Senha alterada. As outras sessões abertas foram encerradas.");
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submit} className="form">
      <Alert tone="error">{error}</Alert>
      <Alert tone="success">{done}</Alert>
      <Field
        label="Senha atual"
        name="current"
        type="password"
        autoComplete="current-password"
        required
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
      />
      <Field
        label="Nova senha"
        name="next"
        type="password"
        autoComplete="new-password"
        minLength={MIN_PASSWORD}
        maxLength={128}
        required
        value={next}
        onChange={(e) => setNext(e.target.value)}
      />
      <Field
        label="Confirme a nova senha"
        name="confirm"
        type="password"
        autoComplete="new-password"
        required
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
      />
      <div>
        <Button type="submit" loading={loading}>
          Alterar senha
        </Button>
      </div>
    </form>
  );
}

export default function Security() {
  const { data: user } = useMe();
  return (
    <div className="stack">
      <h1>Segurança da conta</h1>
      <section className="card">
        <h2>Verificação em duas etapas</h2>
        <TwoFactorSection />
      </section>
      <section className="card">
        <h2>Alterar senha</h2>
        <ChangePasswordSection />
      </section>
      <section className="card">
        <h2>Sessões ativas</h2>
        <SessionsSection />
      </section>
      <section className="card">
        <h2>Atividade recente</h2>
        <ActivitySection />
      </section>
      {user && (
        <section className="card card--danger">
          <h2>Excluir conta</h2>
          <DeleteAccountSection user={user} />
        </section>
      )}
    </div>
  );
}
