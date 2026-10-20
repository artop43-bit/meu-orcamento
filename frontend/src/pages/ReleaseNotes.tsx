import { useState } from "react";
import { ChevronDown, MessageSquarePlus, Sparkles } from "lucide-react";

import { openFeedback } from "../components/power";
import { Button, PageHeader } from "../components/ui";
import { RELEASES } from "../lib/releases";
import { RELEASE } from "../release";

/** Ajustes › Notas da versão: histórico de novidades e atalho para sugerir melhorias. */
export default function ReleaseNotesPage() {
  const [open, setOpen] = useState<Set<string>>(() => new Set([RELEASES[0]?.version ?? ""]));
  const toggle = (version: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(version)) next.delete(version);
      else next.add(version);
      return next;
    });

  return (
    <>
      <PageHeader
        title="Notas da versão"
        subtitle={`Versão atual: ${RELEASE.version}. O que mudou em cada atualização do Meu Orçamento.`}
        actions={
          <Button type="button" onClick={() => openFeedback({ kind: "idea", context: `Versão ${RELEASE.version}` })}>
            <MessageSquarePlus size={16} /> Enviar sugestão
          </Button>
        }
      />
      <ol className="releases">
        {RELEASES.map((release, index) => {
          const expanded = open.has(release.version);
          return (
            <li key={release.version} className={`card release ${index === 0 ? "release--current" : ""}`}>
              <button
                type="button"
                className="release__head"
                aria-expanded={expanded}
                aria-controls={`release-${release.version}`}
                onClick={() => toggle(release.version)}
              >
                <span className="release__version">
                  {index === 0 && <Sparkles size={16} aria-hidden />} Versão {release.version}
                  {index === 0 && <span className="badge badge--accent">Atual</span>}
                </span>
                <span className="release__title">{release.title}</span>
                <span className="muted small">{release.date}</span>
                <ChevronDown size={18} aria-hidden className="release__chevron" />
              </button>
              {expanded && (
                <div id={`release-${release.version}`} className="release__body">
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
      <section className="card stack" style={{ marginTop: 20 }}>
        <h2>Sugira a próxima melhoria</h2>
        <p className="muted" style={{ margin: 0 }}>
          A próxima versão é montada com as sugestões da comunidade. Envie a sua: a resposta da administração aparece em Ajustes › Minhas
          solicitações.
        </p>
        <div>
          <Button type="button" variant="secondary" onClick={() => openFeedback({ kind: "idea", context: `Versão ${RELEASE.version}` })}>
            <MessageSquarePlus size={16} /> Enviar sugestão
          </Button>
        </div>
      </section>
    </>
  );
}
