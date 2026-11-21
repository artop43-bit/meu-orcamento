import type { CSSProperties } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Lock } from "lucide-react";
import { Link } from "react-router";

import { useMe } from "../api/auth";
import { SolutionIcon } from "../components/SolutionIcon";
import { useEnterSolution } from "../components/SolutionTransition";
import { PageHeader } from "../components/ui";
import { HUB_SOLUTIONS, isPlainLeftClick, isSolutionBlocked } from "../lib/hub";
import { prefetchProps } from "../lib/prefetch";

/** Painel inicial após o login: escolhe qual solução abrir usando a mesma conta. */
export default function Hub() {
  const queryClient = useQueryClient();
  const enterSolution = useEnterSolution();
  const blockedResources = useMe().data?.blocked_resources;

  return (
    <>
      <PageHeader
        title="Escolha uma solução"
        subtitle="Acesse as aplicações conectadas à sua conta neste servidor."
      />

      <ul className="hub-grid" aria-label="Soluções disponíveis">
        {HUB_SOLUTIONS.map((solution, index) => {
          const locked = isSolutionBlocked(solution.id, blockedResources);
          return (
            // --i: ordem do cartão, para os cartões entrarem um logo depois do outro.
            <li key={solution.id} style={{ "--i": index } as CSSProperties}>
              {locked ? (
                <div
                  className="settings-list__item hub-card hub-card--soon"
                  aria-disabled="true"
                  title="Recurso bloqueado pelo administrador para a sua conta"
                >
                  <span className="settings-list__icon hub-card__icon--muted" aria-hidden>
                    <Lock size={20} />
                  </span>
                  <span className="settings-list__text">
                    <span className="hub-card__head">
                      <strong>{solution.name}</strong>
                      <span className="badge badge--warn">Bloqueado pelo administrador</span>
                    </span>
                    <span className="muted small">
                      O acesso a esta solução está temporariamente bloqueado para a sua conta.
                    </span>
                  </span>
                </div>
              ) : solution.status === "active" && solution.to ? (
                <Link
                  to={solution.to}
                  className="settings-list__item hub-card"
                  {...prefetchProps(queryClient, solution.to)}
                  onClick={(event) => {
                    // Clique simples: animação de entrada enquanto a solução carrega.
                    // Com Ctrl/⌘/Shift (nova aba ou janela), o link segue o comportamento do navegador.
                    if (!isPlainLeftClick(event)) return;
                    event.preventDefault();
                    enterSolution(solution);
                  }}
                >
                  <span className="settings-list__icon" aria-hidden>
                    <SolutionIcon icon={solution.icon} size={20} />
                  </span>
                  <span className="settings-list__text">
                    <span className="hub-card__head">
                      <strong>{solution.name}</strong>
                      <span className="badge badge--ok">{solution.badge}</span>
                    </span>
                    <span className="muted small">{solution.description}</span>
                  </span>
                  <span className="hub-card__cta" aria-hidden>
                    <span className="small">{solution.actionLabel}</span>
                    <ChevronRight size={18} />
                  </span>
                </Link>
              ) : (
                <div className="settings-list__item hub-card hub-card--soon" aria-disabled="true">
                  <span className="settings-list__icon hub-card__icon--muted" aria-hidden>
                    <SolutionIcon icon={solution.icon} size={20} />
                  </span>
                  <span className="settings-list__text">
                    <span className="hub-card__head">
                      <strong>{solution.name}</strong>
                      <span className="badge badge--muted">{solution.badge}</span>
                    </span>
                    <span className="muted small">{solution.description}</span>
                  </span>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}
