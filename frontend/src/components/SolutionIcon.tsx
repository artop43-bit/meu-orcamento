import {
  BookOpenText,
  CalendarDays,
  FileCheck2,
  FolderKanban,
  Layers,
  LayoutDashboard,
  MessageCircle,
  Package,
  ShieldCheck,
  Wallet,
} from "lucide-react";

import type { SolutionIcon as SolutionIconKey } from "../lib/hub";

/** Ícone oficial de cada solução do Hub (reaproveitado nos cartões, barras e transição de entrada). */
export function SolutionIcon({ icon, size = 20 }: { icon: SolutionIconKey; size?: number }) {
  switch (icon) {
    case "wallet":
      return <Wallet size={size} aria-hidden />;
    case "messages":
      return <MessageCircle size={size} aria-hidden />;
    case "crm":
      return <LayoutDashboard size={size} aria-hidden />;
    case "catalog":
      return <Package size={size} aria-hidden />;
    case "proposals":
      return <FileCheck2 size={size} aria-hidden />;
    case "projects":
      return <FolderKanban size={size} aria-hidden />;
    case "agenda":
      return <CalendarDays size={size} aria-hidden />;
    case "vault":
      return <ShieldCheck size={size} aria-hidden />;
    case "notebook":
      return <BookOpenText size={size} aria-hidden />;
    case "layers":
      return <Layers size={size} aria-hidden />;
  }
}
