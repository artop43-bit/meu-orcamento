import { BookOpenText } from "lucide-react";

import { SolutionShell, type SolutionNavItem } from "../../components/SolutionShell";
import { releaseLabel } from "../../release";

const NAV_ITEMS: SolutionNavItem[] = [
  { to: "/caderno", label: "Notas & Roteiros", icon: BookOpenText, end: true },
];

/** Moldura do Caderno & Base de Conhecimento (`/caderno`) baseada na SolutionShell única. */
export function NotebookShell() {
  return (
    <SolutionShell
      solutionId="caderno"
      releaseId="caderno"
      icon="notebook"
      name="Caderno"
      homeTo="/caderno"
      nav={NAV_ITEMS}
      footer={<p className="muted small">{releaseLabel("caderno")}</p>}
    />
  );
}

export default NotebookShell;
