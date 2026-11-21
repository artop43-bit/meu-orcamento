import { ArrowLeftRight, ChevronLeft, CircleHelp, Repeat, SlidersHorizontal, Tags } from "lucide-react";
import { Link, Outlet, useLocation } from "react-router";

import { SettingsCards, type SettingsItem } from "../components/SettingsCards";
import { PageHeader } from "../components/ui";

export type { SettingsItem };

export const SETTINGS_ITEMS: SettingsItem[] = [
  { to: "/ajustes/recorrencias", label: "Recorrências", description: "Despesas e receitas lançadas automaticamente, assinaturas e custo anual.", icon: <Repeat size={20} /> },
  { to: "/ajustes/categorias", label: "Categorias e regras", description: "Categorias, limites mensais e regras de classificação automática.", icon: <Tags size={20} /> },
  { to: "/ajustes/dados", label: "Importar e exportar", description: "Extratos OFX/CSV, planilhas, backup completo e recomeçar do zero.", icon: <ArrowLeftRight size={20} /> },
  { to: "/ajustes/preferencias", label: "Preferências", description: "Mês financeiro, chave Pix, MEI, avisos financeiros, privacidade e atalhos.", icon: <SlidersHorizontal size={20} /> },
  { to: "/ajustes/ajuda", label: "Central de ajuda", description: "Guia de cada tela, exemplos e o tour de apresentação.", icon: <CircleHelp size={20} /> },
];

/** Tela "Ajustes" do Meu Orçamento: apenas configurações específicas da solução. */
export default function SettingsHub() {
  return (
    <>
      <PageHeader title="Ajustes" subtitle="Configurações, dados e preferências do Meu Orçamento." />
      <SettingsCards items={SETTINGS_ITEMS} />
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
