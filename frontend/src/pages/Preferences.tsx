import { Keyboard, MessageSquarePlus } from "lucide-react";

import { openFeedback, openShortcuts, SHORTCUTS } from "../components/power";
import { Button, PageHeader } from "../components/ui";
import { setPrefs, usePrefs, type Prefs } from "../lib/prefs";

function Choice<K extends keyof Prefs>({
  name,
  label,
  value,
  options,
}: {
  name: K;
  label: string;
  value: Prefs[K];
  options: [Prefs[K], string][];
}) {
  return (
    <fieldset className="radios">
      <legend className="field-label">{label}</legend>
      <div className="segmented">
        {options.map(([option, text]) => (
          <label key={String(option)}>
            <input
              type="radio"
              name={String(name)}
              checked={value === option}
              onChange={() => setPrefs({ [name]: option } as Partial<Prefs>)}
            />
            {text}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export default function Preferences() {
  const prefs = usePrefs();
  return (
    <>
      <PageHeader title="Preferências" subtitle="Aparência e privacidade neste aparelho. Mudam na hora." />
      <div className="layout-main-side">
        <div className="stack" style={{ gap: 20 }}>
          <section className="card stack">
            <h2>Aparência</h2>
            <Choice
              name="theme"
              label="Tema"
              value={prefs.theme}
              options={[
                ["system", "Igual ao aparelho"],
                ["light", "Claro"],
                ["dark", "Escuro"],
              ]}
            />
            <Choice
              name="accent"
              label="Cor de destaque"
              value={prefs.accent}
              options={[
                ["verde", "Verde"],
                ["azul", "Azul"],
                ["roxo", "Roxo"],
                ["laranja", "Laranja"],
              ]}
            />
            <Choice
              name="text"
              label="Tamanho do texto"
              value={prefs.text}
              options={[
                ["normal", "Normal"],
                ["grande", "Grande"],
                ["maior", "Maior"],
              ]}
            />
            <Choice
              name="density"
              label="Espaçamento"
              value={prefs.density}
              options={[
                ["confortavel", "Confortável"],
                ["compacta", "Compacto (mais coisa na tela)"],
              ]}
            />
          </section>
          <section className="card stack">
            <h2>Privacidade</h2>
            <label className="check">
              <input type="checkbox" checked={prefs.privacy} onChange={(e) => setPrefs({ privacy: e.target.checked })} />
              Esconder os valores agora (atalho: tecla P)
            </label>
            <label className="check">
              <input type="checkbox" checked={prefs.privacyOnStart} onChange={(e) => setPrefs({ privacyOnStart: e.target.checked })} />
              Abrir o app sempre com os valores escondidos
            </label>
            <p className="muted small" style={{ margin: 0 }}>
              Útil no ônibus, no trabalho ou ao mostrar a tela para alguém. Os valores viram “R$ ••••” e os gráficos ficam borrados.
            </p>
          </section>
        </div>
        <div className="stack" style={{ gap: 20 }}>
          <section className="card stack">
            <h2>Atalhos</h2>
            <dl className="shortcuts">
              {SHORTCUTS.map(([key, what]) => (
                <div key={key}>
                  <dt>
                    <kbd>{key}</kbd>
                  </dt>
                  <dd>{what}</dd>
                </div>
              ))}
            </dl>
            <Button type="button" variant="secondary" onClick={openShortcuts}>
              <Keyboard size={16} /> Ver atalhos
            </Button>
          </section>
          <section className="card stack">
            <h2>Sugestões</h2>
            <p className="muted" style={{ margin: 0 }}>
              Achou um problema ou tem uma ideia? Mande direto para quem faz o app.
            </p>
            <Button type="button" variant="secondary" onClick={openFeedback}>
              <MessageSquarePlus size={16} /> Enviar sugestão
            </Button>
          </section>
        </div>
      </div>
    </>
  );
}
