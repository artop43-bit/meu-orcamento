import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { Link } from "react-router";

export type SettingsItem = {
  to: string;
  label: string;
  description: string;
  icon: ReactNode;
  badge?: string | null;
};

/** Grade de cartões de navegação usada pelas telas de Ajustes / Configurações. */
export function SettingsCards({ items }: { items: SettingsItem[] }) {
  return (
    <ul className="settings-list">
      {items.map((item) => (
        <li key={item.to}>
          <Link to={item.to} className="settings-list__item">
            <span className="settings-list__icon" aria-hidden>
              {item.icon}
            </span>
            <span className="settings-list__text">
              <strong className="row" style={{ gap: 8, alignItems: "center" }}>
                <span>{item.label}</span>
                {item.badge && <span className="badge badge--accent">{item.badge}</span>}
              </strong>
              <span className="muted small">{item.description}</span>
            </span>
            <ChevronRight size={18} aria-hidden className="muted" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
