import { money } from "../lib/format";

type Series = { values: number[]; color: string; label: string; dashed?: boolean };

/**
 * Gráfico de linhas simples em SVG, com linha do zero.
 * Usado na projeção (saldo acumulado) e no simulador (real x simulado).
 */
export function LineChart({ labels, series, height = 200 }: { labels: string[]; series: Series[]; height?: number }) {
  const width = 640;
  // Margens laterais maiores para os rótulos do primeiro e do último mês não serem cortados.
  const pad = { top: 12, right: 28, bottom: 24, left: 28 };
  const all = series.flatMap((s) => s.values);
  const max = Math.max(0, ...all);
  const min = Math.min(0, ...all);
  const span = max - min || 1;
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const x = (i: number) => pad.left + (labels.length <= 1 ? innerW / 2 : (i / (labels.length - 1)) * innerW);
  const y = (v: number) => pad.top + ((max - v) / span) * innerH;

  return (
    <figure className="line-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={series.map((s) => s.label).join(" e ")}>
        <line x1={pad.left} x2={width - pad.right} y1={y(0)} y2={y(0)} className="line-chart__zero" />
        {series.map((s) => (
          <polyline
            key={s.label}
            fill="none"
            stroke={s.color}
            strokeWidth={2.5}
            strokeDasharray={s.dashed ? "6 4" : undefined}
            strokeLinejoin="round"
            points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")}
          >
            <title>{s.label}</title>
          </polyline>
        ))}
        {series.map((s) =>
          s.values.map((v, i) => (
            <circle key={`${s.label}-${i}`} cx={x(i)} cy={y(v)} r={3} fill={s.color}>
              <title>{`${labels[i]}: ${money(v)}`}</title>
            </circle>
          )),
        )}
        {labels.map((label, i) => (
          <text key={label} x={x(i)} y={height - 6} textAnchor="middle" className="line-chart__label">
            {label}
          </text>
        ))}
      </svg>
      {series.length > 1 && (
        <figcaption className="legend">
          {series.map((s) => (
            <span key={s.label}>
              <i className="swatch" style={{ background: s.color }} /> {s.label}
            </span>
          ))}
        </figcaption>
      )}
    </figure>
  );
}
