import type { ReactNode } from "react";
import { ArrowLeftRight, ChevronLeft, ChevronRight, CircleHelp, Keyboard, MessagesSquare, Repeat, ShieldCheck, SlidersHorizontal, Sparkles, Tags, UserRound } from "lucide-react";
import { Link, Outlet, useLocation } from "react-router";

import { useSupportUnread } from "../api/support";
import { SHORTCUTS } from "../components/power";
import { PageHeader } from "../components/ui";

export type SettingsItem = { to: string; label: string; description: string; icon: ReactNode };

export const SETTINGS_ITEMS: SettingsItem[] = [
  { to: "/ajustes/perfil", label: "Perfil", description: "Nome, foto, banner, resumo pessoal e retrospectiva do mês ou do ano.", icon: <UserRound size={20} /> },
  { to: "/ajustes/solicitacoes", label: "Minhas solicitações", description: "Sugestões e problemas enviados à administração, com as respostas.", icon: <MessagesSquare size={20} /> },
  { to: "/ajustes/recorrencias", label: "Recorrências", description: "Despesas e receitas lançadas automaticamente, assinaturas e custo anual.", icon: <Repeat size={20} /> },
  { to: "/ajustes/categorias", label: "Categorias e regras", description: "Categorias, limites mensais e regras de classificação automática.", icon: <Tags size={20} /> },
  { to: "/ajustes/dados", label: "Importar e exportar", description: "Extratos OFX/CSV, planilhas e backup completo dos dados.", icon: <ArrowLeftRight size={20} /> },
  { to: "/ajustes/seguranca", label: "Segurança", description: "Senha, verificação em duas etapas, sessões ativas e exclusão da conta.", icon: <ShieldCheck size={20} /> },
  { to: "/ajustes/preferencias", label: "Preferências", description: "Tema, cor de destaque, tamanho do texto, densidade e privacidade.", icon: <SlidersHorizontal size={20} /> },
  { to: "/ajustes/atalhos", label: "Atalhos de teclado", description: "Comandos rápidos para lançar e navegar sem o mouse.", icon: <Keyboard size={20} /> },
  { to: "/ajustes/notas", label: "Notas da versão", description: "Novidades de cada atualização e atalho para enviar sugestões.", icon: <Sparkles size={20} /> },
  { to: "/ajustes/ajuda", label: "Central de ajuda", description: "Guia de cada tela, exemplos e o tour de apresentação.", icon: <CircleHelp size={20} /> },
];

/** Tela "Ajustes": lista das sub-telas. */
export default function SettingsHub() {
  const unread = useSupportUnread().data ?? 0;
  return (
    <>
      <PageHeader title="Ajustes" subtitle="Configurações da conta, dados e preferências." />
      <ul className="settings-list">
        {SETTINGS_ITEMS.map((item) => (
          <li key={item.to}>
            <Link to={item.to} className="settings-list__item">
              <span className="settings-list__icon" aria-hidden>
                {item.icon}
              </span>
              <span className="settings-list__text">
                <strong>
                  {item.label}
                  {item.to === "/ajustes/solicitacoes" && unread > 0 && (
                    <span className="badge badge--accent settings-list__badge">{unread} resposta(s) nova(s)</span>
                  )}
                </strong>
                <span className="muted small">{item.description}</span>
              </span>
              <ChevronRight size={18} aria-hidden className="muted" />
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

/** Moldura das sub-telas de Ajustes: link de volta acima do título. */
export function SettingsLayout() {
  const location = useLocation();
  const current = SETTINGS_ITEMS.find((i) => location.pathname.startsWith(i.to));
  return (
    <>
      {current && (
        <nav className="breadcrumb no-print" aria-label="Você está em">
          <Link to="/ajustes">
            <ChevronLeft size={16} aria-hidden /> Ajustes
          </Link>
          <span aria-current="page"> / {current.label}</span>
        </nav>
      )}
      <Outlet />
    </>
  );
}

export function ShortcutsPage() {
  return (
    <>
      <PageHeader title="Atalhos de teclado" subtitle="Disponíveis no computador, em qualquer tela." />
      <section className="card">
        <table className="table shortcuts-table">
          <thead>
            <tr>
              <th scope="col">Tecla</th>
              <th scope="col">Ação</th>
            </tr>
          </thead>
          <tbody>
            {SHORTCUTS.map(([key, what]) => (
              <tr key={key}>
                <td>
                  <kbd>{key}</kbd>
                </td>
                <td>{what}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small" style={{ margin: "12px 0 0" }}>
          Atalhos de uma tecla não funcionam enquanto um campo de texto está em uso.
        </p>
      </section>
    </>
  );
}
