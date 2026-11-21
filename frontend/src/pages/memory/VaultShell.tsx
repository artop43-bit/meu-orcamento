import { ShieldCheck } from "lucide-react";

import { SolutionShell, type SolutionNavItem } from "../../components/SolutionShell";
import { releaseLabel } from "../../release";

const NAV_ITEMS: SolutionNavItem[] = [
  { to: "/cofre", label: "Documentos", icon: ShieldCheck, end: true },
];

/** Moldura do Cofre de Documentos & Garantias (`/cofre`) baseada na SolutionShell única. */
export function VaultShell() {
  return (
    <SolutionShell
      solutionId="cofre"
      releaseId="cofre"
      icon="vault"
      name="Cofre & Garantias"
      homeTo="/cofre"
      nav={NAV_ITEMS}
      footer={<p className="muted small">{releaseLabel("cofre")}</p>}
    />
  );
}

export default VaultShell;
