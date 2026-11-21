import { FolderKanban } from "lucide-react";

import { SolutionShell, type SolutionNavItem } from "../../components/SolutionShell";

const PROJECTS_NAV: SolutionNavItem[] = [
  { to: "/projetos", label: "Quadros & Tarefas", icon: FolderKanban, end: true },
];

export default function ProjectsShell() {
  return (
    <SolutionShell
      solutionId="projetos"
      releaseId="projetos"
      icon="projects"
      name="Projetos & Tarefas"
      homeTo="/projetos"
      nav={PROJECTS_NAV}
    />
  );
}
