import { type CSSProperties } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { originOf, setAppearance } from "../lib/appearance";
import { setPrefs, usePrefs, type Prefs } from "../lib/prefs";
import { STYLES, type StyleName } from "../theme/styles";
import { ACCENTS, type AccentName } from "../theme/tokens";

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
  const queryClient = useQueryClient();
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
              onChange={(e) =>
                name === "theme" || name === "accent"
                  ? setAppearance({ [name]: option } as Partial<Pick<Prefs, "theme" | "accent">>, queryClient, originOf(e))
                  : setPrefs({ [name]: option } as Partial<Prefs>)
              }
            />
            {text}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function StylePicker({ value }: { value: StyleName }) {
  const queryClient = useQueryClient();
  const styles = Object.entries(STYLES) as [StyleName, (typeof STYLES)[StyleName]][];
  return (
    <fieldset className="radios">
      <legend className="field-label">Estilo</legend>
      <div className="style-picker">
        {styles.map(([name, style]) => (
          <label key={name} className="style-option">
            <input type="radio" name="style" checked={value === name} onChange={(e) => setAppearance({ style: name }, queryClient, originOf(e))} />
            <span className="style-thumb" data-thumb={name} aria-hidden>
              <span className="style-thumb__side" />
              <span className="style-thumb__body">
                <span className="style-thumb__card style-thumb__card--hero" />
                <span className="style-thumb__row">
                  <span className="style-thumb__card" />
                  <span className="style-thumb__card" />
                </span>
              </span>
            </span>
            <span className="style-option__text">
              <strong>{style.label}</strong>
              <span className="muted small">{style.text}</span>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function AccentPicker({ value }: { value: AccentName }) {
  const queryClient = useQueryClient();
  const accents = Object.entries(ACCENTS) as [AccentName, (typeof ACCENTS)[AccentName]][];
  return (
    <fieldset className="radios">
      <legend className="field-label">Cor de destaque</legend>
      <div className="accent-swatches">
        {accents.map(([name, accent]) => (
          <label key={name} className="accent-swatch" style={{ "--swatch": accent.light.accent, "--swatch-dark": accent.dark.accent } as CSSProperties}>
            <input type="radio" name="accent" checked={value === name} onChange={(e) => setAppearance({ accent: name }, queryClient, originOf(e))} />
            <span className="accent-swatch__dot" aria-hidden />
            {accent.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** Aparência compartilhada da conta (estilo, tema, cor, texto e espaçamento). */
export function AppearanceSection() {
  const prefs = usePrefs();
  return (
    <section className="card stack">
      <h2>Aparência</h2>
      <p className="muted small" style={{ margin: 0 }}>
        Estilo, tema e cor de destaque ficam salvos na sua conta e valem em todos os aparelhos. Tamanho do texto e espaçamento valem só neste
        aparelho.
      </p>
      <StylePicker value={prefs.style} />
      <Choice
        name="theme"
        label="Tema"
        value={prefs.theme}
        options={[
          ["system", "Automático (sistema)"],
          ["light", "Claro"],
          ["dark", "Escuro"],
        ]}
      />
      <AccentPicker value={prefs.accent} />
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
          ["compacta", "Compacto"],
        ]}
      />
    </section>
  );
}
