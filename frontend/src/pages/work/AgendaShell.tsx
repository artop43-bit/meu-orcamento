import { CalendarDays } from "lucide-react";

import { SolutionShell, type SolutionNavItem } from "../../components/SolutionShell";

const AGENDA_NAV: SolutionNavItem[] = [
  { to: "/agenda", label: "Agenda 360°", icon: CalendarDays, end: true },
];

export default function AgendaShell() {
  return (
    <SolutionShell
      solutionId="agenda"
      releaseId="agenda"
      icon="agenda"
      name="Agenda & Compromissos"
      homeTo="/agenda"
      nav={AGENDA_NAV}
    />
  );
}
