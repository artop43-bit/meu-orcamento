import { Database, Kanban, LayoutDashboard, Users } from "lucide-react";

import { releaseLabel } from "../release";
import { SolutionShell, type SolutionNavItem } from "./SolutionShell";

const NAV_ITEMS: SolutionNavItem[] = [
  { to: "/crm", label: "Painéis", icon: LayoutDashboard, end: true },
  { to: "/crm/funil", label: "Funil CRM", icon: Kanban, end: false },
  { to: "/crm/contatos", label: "Contatos", icon: Users, end: false },
  { to: "/crm/fontes", label: "Fontes", icon: Database, end: false },
];

/** Moldura da solução Dashboard & CRM baseada na SolutionShell única. */
export function CrmShell() {
  return (
    <SolutionShell
      solutionId="dashboard-crm"
      releaseId="dashboard-crm"
      icon="crm"
      name="Dashboard & CRM"
      homeTo="/crm"
      nav={NAV_ITEMS}
      showVersionBadge={false}
      footer={<p className="muted small">{releaseLabel("dashboard-crm")}</p>}
    />
  );
}
