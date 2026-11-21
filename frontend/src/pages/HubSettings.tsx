import { useQuery } from "@tanstack/react-query";
import { Lock, ShieldCheck, SlidersHorizontal, Smartphone, Sparkles } from "lucide-react";

import { useMe } from "../api/auth";
import { moneyApi } from "../api/money";
import { SettingsCards, type SettingsItem } from "../components/SettingsCards";
import { PageHeader } from "../components/ui";

export const HUB_SETTINGS_ITEMS: SettingsItem[] = [
  { to: "/seguranca", label: "Segurança", description: "Senha, verificação em duas etapas, sessões ativas e exclusão da conta.", icon: <Lock size={20} /> },
  { to: "/preferencias", label: "Preferências", description: "Aparência, avisos por e-mail e webhook.", icon: <SlidersHorizontal size={20} /> },
  { to: "/app", label: "App e notificações", description: "Instalar no Android, iPhone ou computador e receber avisos no aparelho.", icon: <Smartphone size={20} /> },
  { to: "/notas", label: "Notas da versão", description: "Novidades de cada atualização separadas por solução.", icon: <Sparkles size={20} /> },
];

export const HUB_ADMIN_ITEM: SettingsItem = {
  to: "/admin",
  label: "Administração",
  description: "Usuários, liberação de acesso, e-mails, solicitações, recados e erros.",
  icon: <ShieldCheck size={20} />,
};

/** Tela "Configurações" do Hub de Soluções: configurações da conta, notas por solução e painel administrador. */
export default function HubSettings() {
  const { data: user } = useMe();
  const adminOverview = useQuery({
    queryKey: ["admin", "overview"],
    queryFn: moneyApi.adminOverview,
    enabled: Boolean(user?.is_admin),
    staleTime: 30_000,
  });
  const pendingCount = (adminOverview.data?.pending ?? 0) + (adminOverview.data?.feedback_new ?? 0);
  const items: SettingsItem[] = user?.is_admin
    ? [
        ...HUB_SETTINGS_ITEMS,
        {
          ...HUB_ADMIN_ITEM,
          badge: pendingCount > 0 ? `${pendingCount} pendente(s)` : "Admin",
        },
      ]
    : HUB_SETTINGS_ITEMS;

  return (
    <>
      <PageHeader title="Configurações" subtitle="Segurança, aparência, notificações e informações da conta." />
      <SettingsCards items={items} />
    </>
  );
}
