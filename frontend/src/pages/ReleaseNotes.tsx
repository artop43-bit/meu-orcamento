import { useMemo, useState } from "react";
import { ChevronDown, LayoutDashboard, LayoutGrid, MessageCircle, MessageSquarePlus, Sparkles, Wallet } from "lucide-react";
import { useSearchParams } from "react-router";

import { openFeedback } from "../components/power";
import { Button, PageHeader } from "../components/ui";
import {
  filterReleasesBySolution,
  RELEASE_SOLUTIONS,
  RELEASES,
  releaseSolutionLabel,
  releaseDate,
  releaseKey,
  type ReleaseSolutionFilter,
  type ReleaseSolutionId,
} from "../lib/releases";

function solutionIcon(id: ReleaseSolutionId) {
  switch (id) {
    case "hub":
      return <LayoutGrid size={16} aria-hidden />;
    case "mensageria":
      return <MessageCircle size={16} aria-hidden />;
    case "dashboard-crm":
      return <LayoutDashboard size={16} aria-hidden />;
    default:
      return <Wallet size={16} aria-hidden />;
  }
}

/** Configurações › Notas da versão: histórico de novidades separado por solução e atalho para sugerir melhorias. */
export default function ReleaseNotesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawParam = searchParams.get("solucao");
  const activeFilter: ReleaseSolutionFilter =
    rawParam && RELEASE_SOLUTIONS.some((s) => s.id === rawParam)
      ? (rawParam as ReleaseSolutionId)
      : "all";

  const [open, setOpen] = useState<Set<string>>(
    () =>
      new Set(
        RELEASE_SOLUTIONS.map((sol) => {
          const first = filterReleasesBySolution(RELEASES, sol.id)[0];
          return first ? releaseKey(first) : "";
        }).filter(Boolean),
      ),
  );

  function selectSolution(nextFilter: ReleaseSolutionFilter) {
    const nextParams = new URLSearchParams(searchParams);
    if (nextFilter === "all") nextParams.delete("solucao");
    else nextParams.set("solucao", nextFilter);
    setSearchParams(nextParams, { replace: true });
  }

  const toggle = (key: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const groups = useMemo(() => {
    const targetSolutions =
      activeFilter === "all"
        ? RELEASE_SOLUTIONS
        : RELEASE_SOLUTIONS.filter((s) => s.id === activeFilter);
    return targetSolutions
      .map((sol) => ({
        solution: sol,
        items: filterReleasesBySolution(RELEASES, sol.id),
      }))
      .filter((g) => g.items.length > 0);
  }, [activeFilter]);

  return (
    <>
      <PageHeader
        title="Notas da versão"
        subtitle="O que mudou em cada solução da plataforma, com versões e notas próprias."
        actions={
          <Button type="button" onClick={() => openFeedback({ kind: "idea", context: `Notas da versão: ${activeFilter === "all" ? "Todas as soluções" : releaseSolutionLabel(activeFilter)}` })}>
            <MessageSquarePlus size={16} /> Enviar sugestão
          </Button>
        }
      />

      <div className="tabs" role="tablist" aria-label="Filtrar notas por solução" style={{ marginBottom: 18 }}>
        <button
          type="button"
          role="tab"
          aria-selected={activeFilter === "all"}
          className={activeFilter === "all" ? "active" : ""}
          onClick={() => selectSolution("all")}
        >
          <Sparkles size={15} aria-hidden /> Todas as soluções
        </button>
        {RELEASE_SOLUTIONS.map((sol) => (
          <button
            key={sol.id}
            type="button"
            role="tab"
            aria-selected={activeFilter === sol.id}
            className={activeFilter === sol.id ? "active" : ""}
            onClick={() => selectSolution(sol.id)}
          >
            {solutionIcon(sol.id)} {sol.label}
          </button>
        ))}
      </div>

      <div className="stack" style={{ gap: 24 }}>
        {groups.map(({ solution, items }) => (
          <section
            key={solution.id}
            className="stack"
            aria-label={`Notas da versão de ${solution.label}`}
          >
            <div className="card release-solution-head">
              <div className="row" style={{ gap: 10, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
                <div className="row" style={{ gap: 10, alignItems: "center" }}>
                  <span className="settings-list__icon" aria-hidden>
                    {solutionIcon(solution.id)}
                  </span>
                  <div>
                    <h2 style={{ margin: 0, fontSize: "1.08rem" }}>{solution.label}</h2>
                    <p className="muted small" style={{ margin: "2px 0 0" }}>
                      {solution.description}
                    </p>
                  </div>
                </div>
                <span className="badge badge--muted">
                  {items.length} {items.length === 1 ? "versão" : "versões"}
                </span>
              </div>
            </div>

            <ol className="releases">
              {items.map((release, index) => {
                const key = releaseKey(release);
                const expanded = open.has(key);
                const solLabel = releaseSolutionLabel(release.solution ?? solution.id);
                return (
                  <li key={key} className={`card release ${index === 0 ? "release--current" : ""}`}>
                    <button
                      type="button"
                      className="release__head"
                      aria-expanded={expanded}
                      aria-controls={`release-${key}`}
                      onClick={() => toggle(key)}
                    >
                      <span className="release__version">
                        {index === 0 && <Sparkles size={16} aria-hidden />} Versão {release.version}
                        <span className="badge badge--muted">{solLabel}</span>
                        {index === 0 && <span className="badge badge--accent">Atual</span>}
                      </span>
                      <span className="release__title">{release.title}</span>
                      <span className="muted small">{releaseDate(release)}</span>
                      <ChevronDown size={18} aria-hidden className="release__chevron" />
                    </button>
                    {expanded && (
                      <div id={`release-${key}`} className="release__body">
                        {release.sections.map((section) => (
                          <div key={section.title}>
                            <h3>{section.title}</h3>
                            <ul>
                              {section.items.map((item) => (
                                <li key={item}>{item}</li>
                              ))}
                            </ul>
                          </div>
                        ))}
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>
        ))}
      </div>

      <section className="card stack" style={{ marginTop: 20 }}>
        <h2>Sugira a próxima melhoria</h2>
        <p className="muted" style={{ margin: 0 }}>
          A próxima versão é montada com as sugestões da comunidade. Envie a sua: cada solicitação ganha um número, e o andamento e a resposta
          da administração aparecem em Mensagens › Solicitações.
        </p>
        <div>
          <Button type="button" variant="secondary" onClick={() => openFeedback({ kind: "idea", context: `Notas da versão: ${activeFilter === "all" ? "Todas as soluções" : releaseSolutionLabel(activeFilter)}` })}>
            <MessageSquarePlus size={16} /> Enviar sugestão
          </Button>
        </div>
      </section>
    </>
  );
}
