import { FileCheck2 } from "lucide-react";

import { SolutionShell, type SolutionNavItem } from "../../components/SolutionShell";

const PROPOSALS_NAV: SolutionNavItem[] = [
  { to: "/propostas", label: "Documentos", icon: FileCheck2, end: true },
];

export default function ProposalsShell() {
  return (
    <SolutionShell
      solutionId="propostas"
      releaseId="propostas"
      icon="proposals"
      name="Propostas & PDFs"
      homeTo="/propostas"
      nav={PROPOSALS_NAV}
    />
  );
}
