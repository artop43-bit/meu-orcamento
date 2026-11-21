import { Package, ShoppingBag } from "lucide-react";

import { SolutionShell, type SolutionNavItem } from "../../components/SolutionShell";

const CATALOG_NAV: SolutionNavItem[] = [
  { to: "/catalogo", label: "Itens & Estoque", icon: Package, end: true },
  { to: "/catalogo/pedidos", label: "Pedidos", icon: ShoppingBag },
];

export default function CatalogShell() {
  return (
    <SolutionShell
      solutionId="catalogo"
      releaseId="catalogo"
      icon="catalog"
      name="Catálogo & Estoque"
      homeTo="/catalogo"
      nav={CATALOG_NAV}
    />
  );
}
