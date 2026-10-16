import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import { money, monthLabel } from "../../lib/format";
import { colorFor, compactValue, formatValue, niceScale, type ChartType, type ChartUnit } from "./format";

/**
 * Gráfico do app (SVG próprio, sem biblioteca externa).
 * - Mouse: dica com os valores ao passar por cima.
 * - Toque: arrastar o dedo percorre os pontos (ou tocar, quando o gráfico rola de lado).
 * - Teclado: o gráfico recebe foco e as setas percorrem os pontos; o leitor de tela anuncia.
 * - Períodos longos no celular: o gráfico rola de lado em vez de apertar as colunas.
 */

export type ChartLabel = { key: string; label: string; color?: string | null };
export type ChartSeries = { key: string; name: string; color?: string | null; values: (number | null)[] };
export type ChartCompare = { name: string; values: (number | null)[] } | null;

export type ChartProps = {
  type: ChartType;
  labels: ChartLabel[];
  series: ChartSeries[];
  compare?: ChartCompare;
  unit?: ChartUnit;
  /** Rótulos são meses ("2026-05")? Então são exibidos como "mai/26". */
  monthLabels?: boolean;
  height?: number;
  /** Descrição curta para leitor de tela (ex.: "Gastos por mês de mai/26 a out/26"). */
  description: string;
  /** Ao clicar num rótulo (ex.: abrir o mês). */
  onSelect?: (key: string) => void;
};

const PAD = { top: 16, right: 12, bottom: 30 };
// Largura mínima por coluna antes de o gráfico passar a rolar (barras lado a lado precisam de mais).
const MIN_COL = 30;
const MIN_COL_GROUPED = 34;

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}


// Só formata como mês o que é mês ("2026-05"): durante a troca de agrupamento o gráfico
// anterior continua na tela por um instante, com rótulos de categoria.
function displayLabel(label: string, monthLabels?: boolean) {
  return monthLabels && /^\d{4}-\d{2}$/.test(label) ? monthLabel(label, true) : label;
}

export function Chart(props: ChartProps) {
  if (props.type === "table") return <ChartTable {...props} />;
  if (props.type === "donut") return <DonutChart {...props} />;
  if (props.type === "hbar") return <HBarChart {...props} />;
  return <XYChart {...props} />;
}

// ---------------------------------------------------------------- barras, empilhadas, linhas, área

function XYChart({ type, labels, series, compare, unit = "money", monthLabels, height = 260, description, onSelect }: ChartProps) {
  const [boxRef, boxWidth] = useWidth<HTMLDivElement>();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState<number | null>(null);
  const [announce, setAnnounce] = useState("");
  const tooltipId = useId();
  const count = labels.length;
  const stacked = type === "stacked";

  // Escala com passos redondos (ex.: 0, 1 mil, 2 mil…), incluindo valores negativos.
  const { max, min, ticks } = useMemo(() => {
    const totals = labels.map((_, i) =>
      stacked
        ? series.reduce((sum, s) => sum + Math.max(0, s.values[i] ?? 0), 0)
        : Math.max(...series.map((s) => s.values[i] ?? 0)),
    );
    const lows = labels.map((_, i) => Math.min(0, ...series.map((s) => s.values[i] ?? 0), compare?.values[i] ?? 0));
    const high = Math.max(0, ...totals, ...(compare?.values.map((v) => v ?? 0) ?? []));
    const low = Math.min(0, ...lows);
    return niceScale(low, high);
  }, [labels, series, compare, stacked]);

  // Margem esquerda do tamanho do maior rótulo da régua.
  const padLeft = Math.max(40, Math.max(...ticks.map((t) => compactValue(t, unit).length)) * 6.6 + 14);
  const minCol = type === "bar" && series.length > 1 ? MIN_COL_GROUPED : MIN_COL;
  const scrollable = boxWidth > 0 && count * minCol + padLeft + PAD.right > boxWidth;
  const width = scrollable ? count * minCol + padLeft + PAD.right : Math.max(boxWidth, 200);
  const innerW = width - padLeft - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const col = count ? innerW / count : innerW;

  const span = max - min || 1;
  const y = (v: number) => PAD.top + ((max - v) / span) * innerH;
  const x = (i: number) => padLeft + col * i + col / 2;

  // Período longo: começa mostrando os meses mais recentes.
  useEffect(() => {
    if (scrollable && scrollRef.current) scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
  }, [scrollable, count]);

  // Chave muda quando os dados mudam: reinicia a animação de entrada.
  const animKey = useMemo(() => series.map((s) => s.key + s.values.join(",")).join("|") + type, [series, type]);

  function indexAt(clientX: number, svg: SVGSVGElement) {
    const rect = svg.getBoundingClientRect();
    const px = ((clientX - rect.left) / rect.width) * width;
    const i = Math.floor((px - padLeft) / col);
    return Math.max(0, Math.min(count - 1, i));
  }

  const drag = useRef<{ x: number; moved: boolean } | null>(null);

  function onPointerDown(e: PointerEvent<SVGSVGElement>) {
    if (e.pointerType === "mouse") return;
    drag.current = { x: e.clientX, moved: false };
    if (!scrollable) setActive(indexAt(e.clientX, e.currentTarget));
  }

  function onPointerMove(e: PointerEvent<SVGSVGElement>) {
    if (e.pointerType === "mouse") {
      setActive(indexAt(e.clientX, e.currentTarget));
      return;
    }
    if (!drag.current) return;
    if (Math.abs(e.clientX - drag.current.x) > 6) drag.current.moved = true;
    if (!scrollable) setActive(indexAt(e.clientX, e.currentTarget));
  }

  function onPointerUp(e: PointerEvent<SVGSVGElement>) {
    if (e.pointerType !== "mouse" && drag.current && !drag.current.moved && scrollable) {
      setActive(indexAt(e.clientX, e.currentTarget));
    }
    drag.current = null;
  }

  function describe(i: number) {
    const parts = series.map((s) => `${s.name}: ${formatValue(s.values[i], unit)}`);
    if (compare) parts.push(`${compare.name}: ${formatValue(compare.values[i], unit)}`);
    return `${displayLabel(labels[i].label, monthLabels)}. ${parts.join("; ")}`;
  }

  function onKeyDown(e: KeyboardEvent<SVGSVGElement>) {
    let next = active;
    if (e.key === "ArrowRight") next = active === null ? 0 : Math.min(count - 1, active + 1);
    else if (e.key === "ArrowLeft") next = active === null ? count - 1 : Math.max(0, active - 1);
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = count - 1;
    else if (e.key === "Enter" && active !== null && onSelect) {
      onSelect(labels[active].key);
      return;
    } else if (e.key === "Escape") next = null;
    else return;
    e.preventDefault();
    setActive(next);
    if (next !== null) setAnnounce(describe(next));
  }

  const barSeries = type === "bar" || type === "stacked";
  const groupW = Math.min(col * 0.72, 56);
  const barW = stacked ? groupW : groupW / Math.max(series.length, 1);

  const linePath = (values: (number | null)[]) =>
    values
      .map((v, i) => (v === null ? null : `${x(i)},${y(v)}`))
      .reduce<string[]>((acc, point) => {
        if (point === null) acc.push("");
        else acc[acc.length - 1] = `${acc[acc.length - 1] ?? ""}${acc[acc.length - 1] ? " L" : "M"}${point}`;
        return acc;
      }, [""])
      .filter(Boolean)
      .join(" ");

  const labelEvery = Math.ceil((count * 34) / Math.max(innerW, 1));

  return (
    <div className="chart2" ref={boxRef}>
      {/* Gráfico que rola de lado: a régua de valores fica parada à esquerda. */}
      {scrollable && (
        <svg className="chart2__yaxis" width={padLeft} height={height} aria-hidden>
          <rect width={padLeft} height={height} className="chart2__yaxis-bg" />
          {ticks.map((t) => (
            <text key={t} x={padLeft - 8} y={y(t) + 4} textAnchor="end" className="chart2__axis">
              {compactValue(t, unit)}
            </text>
          ))}
        </svg>
      )}
      <div className={`chart2__scroll ${scrollable ? "is-scrollable" : ""}`} ref={scrollRef} data-no-swipe={scrollable || undefined}>
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          className={`chart2__svg ${scrollable ? "" : "is-scrub"}`}
          role="img"
          tabIndex={0}
          aria-label={`${description}. Use as setas para percorrer os valores.`}
          aria-describedby={active !== null ? tooltipId : undefined}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={(e) => e.pointerType === "mouse" && setActive(null)}
          onKeyDown={onKeyDown}
          onBlur={() => setActive(null)}
          onClick={() => active !== null && onSelect?.(labels[active].key)}
        >
          {/* grade e eixo */}
          {ticks.map((t) => (
            <g key={t}>
              <line x1={padLeft} x2={width - PAD.right} y1={y(t)} y2={y(t)} className={t === 0 ? "chart2__zero" : "chart2__grid"} />
              {!scrollable && (
                <text x={padLeft - 8} y={y(t) + 4} textAnchor="end" className="chart2__axis">
                  {compactValue(t, unit)}
                </text>
              )}
            </g>
          ))}
          {labels.map((l, i) =>
            i % labelEvery === 0 || i === count - 1 ? (
              <text key={l.key} x={x(i)} y={height - 8} textAnchor="middle" className={`chart2__axis ${active === i ? "is-active" : ""}`}>
                {displayLabel(l.label, monthLabels)}
              </text>
            ) : null,
          )}
          {active !== null && <rect x={padLeft + col * active} y={PAD.top} width={col} height={innerH} className="chart2__hover" />}

          <g key={animKey} className="chart2__data">
            {barSeries &&
              labels.map((_, i) => {
                let base = 0;
                return series.map((s, si) => {
                  const v = s.values[i] ?? 0;
                  const color = colorFor(s.color, si);
                  if (stacked) {
                    const top = base + Math.max(0, v);
                    const rect = (
                      <rect
                        key={s.key + i}
                        x={x(i) - barW / 2}
                        y={y(top)}
                        width={barW}
                        height={Math.max(0, y(base) - y(top))}
                        fill={color}
                        className="chart2__bar"
                        style={{ animationDelay: `${i * 18}ms` }}
                      />
                    );
                    base = top;
                    return rect;
                  }
                  const left = x(i) - groupW / 2 + barW * si;
                  return (
                    <rect
                      key={s.key + i}
                      x={left + 1}
                      y={v >= 0 ? y(v) : y(0)}
                      width={Math.max(2, barW - 2)}
                      height={Math.max(v === 0 ? 0 : 2, Math.abs(y(v) - y(0)))}
                      rx={3}
                      fill={v < 0 ? "var(--error)" : color}
                      className="chart2__bar"
                      style={{ animationDelay: `${i * 18}ms` }}
                    />
                  );
                });
              })}
            {(type === "line" || type === "area") &&
              series.map((s, si) => {
                const color = colorFor(s.color, si);
                const path = linePath(s.values);
                return (
                  <g key={s.key}>
                    {type === "area" && path && (
                      <path d={`${path} L${x(count - 1)},${y(Math.max(min, 0))} L${x(0)},${y(Math.max(min, 0))} Z`} fill={color} className="chart2__area" />
                    )}
                    <path d={path} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" className="chart2__line" pathLength={1} />
                    {s.values.map((v, i) =>
                      v === null ? null : <circle key={i} cx={x(i)} cy={y(v)} r={active === i ? 5 : 3} fill="var(--surface)" stroke={color} strokeWidth={2} />,
                    )}
                  </g>
                );
              })}
            {compare && (
              <g className="chart2__compare">
                <path d={linePath(compare.values)} fill="none" strokeDasharray="5 5" strokeWidth={2} pathLength={undefined} />
                {compare.values.map((v, i) => (v === null ? null : <circle key={i} cx={x(i)} cy={y(v)} r={2.5} />))}
              </g>
            )}
          </g>
        </svg>
      </div>

      {active !== null && (
        <div
          id={tooltipId}
          className="chart2__tip"
          role="status"
          style={{
            left: `${Math.min(Math.max(((x(active) - (scrollRef.current?.scrollLeft ?? 0)) / Math.max(boxWidth, 1)) * 100, 18), 82)}%`,
          }}
        >
          <strong>{displayLabel(labels[active].label, monthLabels)}</strong>
          {series.map((s, si) => (
            <span key={s.key} className="chart2__tip-row">
              <i style={{ background: colorFor(s.color, si) }} /> {s.name}
              <b>{formatValue(s.values[active], unit)}</b>
            </span>
          ))}
          {stacked && series.length > 1 && (
            <span className="chart2__tip-row chart2__tip-total">
              Total <b>{formatValue(series.reduce((sum, s) => sum + (s.values[active] ?? 0), 0), unit)}</b>
            </span>
          )}
          {compare && (
            <span className="chart2__tip-row">
              <i className="is-compare" /> {compare.name}
              <b>{formatValue(compare.values[active], unit)}</b>
            </span>
          )}
        </div>
      )}
      <Legend series={series} compare={compare} />
      <span className="sr-only" aria-live="polite">
        {announce}
      </span>
    </div>
  );
}

function Legend({ series, compare }: { series: ChartSeries[]; compare?: ChartCompare }) {
  if (series.length <= 1 && !compare) return null;
  return (
    <div className="legend chart2__legend">
      {series.map((s, si) => (
        <span key={s.key}>
          <i className="swatch" style={{ background: colorFor(s.color, si) }} /> {s.name}
        </span>
      ))}
      {compare && (
        <span>
          <i className="swatch swatch--dashed" /> {compare.name}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- barras horizontais (ranking)

function HBarChart({ labels, series, compare, unit = "money", description, onSelect }: ChartProps) {
  const values = series[0]?.values ?? [];
  const max = Math.max(1, ...values.map((v) => v ?? 0), ...(compare?.values.map((v) => v ?? 0) ?? []));
  const total = values.reduce<number>((sum, v) => sum + (v ?? 0), 0) || 1;
  return (
    <figure className="hbars" aria-label={description}>
      <ol className="hbars__list">
        {labels.map((l, i) => {
          const v = values[i] ?? 0;
          const c = compare?.values[i] ?? null;
          const delta = c !== null && c > 0 ? ((v - c) / c) * 100 : null;
          return (
            <li key={l.key}>
              <button type="button" className="hbars__row" onClick={() => onSelect?.(l.key)} disabled={!onSelect}>
                <span className="hbars__name">
                  <i className="swatch" style={{ background: colorFor(l.color, i) }} />
                  {l.label}
                </span>
                <span className="hbars__value">
                  {formatValue(v, unit)}
                  {unit === "money" && <span className="muted small"> {Math.round((v / total) * 100)}%</span>}
                </span>
                <span className="hbars__track" aria-hidden>
                  <span className="hbars__fill" style={{ width: `${(v / max) * 100}%`, background: colorFor(l.color, i), animationDelay: `${i * 40}ms` }} />
                  {c !== null && <span className="hbars__mark" style={{ left: `${(c / max) * 100}%` }} title={`${compare?.name}: ${formatValue(c, unit)}`} />}
                </span>
                {compare && (
                  <span className={`hbars__delta small ${delta === null ? "muted" : delta > 0 ? "tone--error" : "tone--ok"}`}>
                    {delta === null ? `${compare.name}: —` : `${delta > 0 ? "+" : ""}${Math.round(delta)}% vs ${compare.name.toLowerCase()}`}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ol>
      {compare && (
        <figcaption className="legend chart2__legend">
          <span>
            <i className="swatch swatch--mark" /> {compare.name}
          </span>
        </figcaption>
      )}
    </figure>
  );
}

// ---------------------------------------------------------------- rosca

function DonutChart({ labels, series, unit = "money", description }: ChartProps) {
  const values = (series.length === 1 ? series[0].values : labels.map((_, i) => series.reduce((s, x) => s + (x.values[i] ?? 0), 0))).map((v) => Math.max(0, v ?? 0));
  const names = series.length === 1 ? labels : labels;
  const total = values.reduce((a, b) => a + b, 0);
  const [active, setActive] = useState<number | null>(null);
  const r = 15.9155;
  let start = 0;
  return (
    <figure className="donut donut--interactive">
      <svg viewBox="0 0 42 42" role="img" aria-label={`${description}: ${names.map((l, i) => `${l.label} ${total ? Math.round((values[i] / total) * 100) : 0}%`).join(", ")}`}>
        <circle cx="21" cy="21" r={r} fill="none" stroke="var(--border)" strokeWidth="5" />
        {values.map((v, i) => {
          const pct = total ? (v / total) * 100 : 0;
          const el = (
            <circle
              key={names[i].key}
              cx="21"
              cy="21"
              r={r}
              fill="none"
              stroke={colorFor(names[i].color, i)}
              strokeWidth={active === i ? 6.5 : 5}
              strokeDasharray={`${pct} ${100 - pct}`}
              strokeDashoffset={25 - start}
              className="donut__slice"
              onPointerEnter={() => setActive(i)}
              onPointerLeave={() => setActive(null)}
            />
          );
          start += pct;
          return el;
        })}
        <text x="21" y="20.2" textAnchor="middle" className="donut__label">
          {active === null ? "Total" : names[active].label.slice(0, 16)}
        </text>
        <text x="21" y="25" textAnchor="middle" className="donut__center">
          {compactValue(active === null ? total : values[active], unit)}
        </text>
      </svg>
      <figcaption>
        <ul className="donut__legend">
          {names.map((l, i) => (
            <li
              key={l.key}
              className={active === i ? "is-active" : undefined}
              onPointerEnter={() => setActive(i)}
              onPointerLeave={() => setActive(null)}
            >
              <i className="swatch" style={{ background: colorFor(l.color, i) }} />
              <span className="grow">{l.label}</span>
              <span className="num">{formatValue(values[i], unit)}</span>
              <span className="muted small donut__pct">{total ? Math.round((values[i] / total) * 100) : 0}%</span>
            </li>
          ))}
        </ul>
      </figcaption>
    </figure>
  );
}

// ---------------------------------------------------------------- tabela

export function ChartTable({ labels, series, compare, unit = "money", monthLabels, description }: ChartProps) {
  const showTotal = series.length > 1 && unit === "money";
  return (
    <div className="table-wrap" data-no-swipe tabIndex={0} role="region" aria-label={`Tabela: ${description}`}>
      <table className="table">
        <caption className="sr-only">{description}</caption>
        <thead>
          <tr>
            <th>{monthLabels ? "Mês" : "Item"}</th>
            {series.map((s) => (
              <th key={s.key} className="num">
                {s.name}
              </th>
            ))}
            {showTotal && <th className="num">Total</th>}
            {compare && <th className="num">{compare.name}</th>}
            {compare && <th className="num">Diferença</th>}
          </tr>
        </thead>
        <tbody>
          {labels.map((l, i) => {
            const sum = series.reduce((acc, s) => acc + (s.values[i] ?? 0), 0);
            const main = series.length > 1 ? sum : (series[0]?.values[i] ?? null);
            const c = compare?.values[i] ?? null;
            const diff = main !== null && c !== null ? main - c : null;
            return (
              <tr key={l.key}>
                <td>{displayLabel(l.label, monthLabels)}</td>
                {series.map((s) => (
                  <td key={s.key} className="num">
                    {formatValue(s.values[i], unit)}
                  </td>
                ))}
                {showTotal && <td className="num">{money(sum)}</td>}
                {compare && <td className="num muted">{formatValue(c, unit)}</td>}
                {compare && (
                  <td className={`num ${diff === null || diff === 0 ? "" : diff > 0 ? "tone--error" : "tone--ok"}`}>
                    {diff === null ? "—" : `${diff > 0 ? "+" : ""}${formatValue(diff, unit)}`}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
