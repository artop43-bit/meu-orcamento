import type { DashboardWidget, WidgetSeriesItem } from "../../api/crm";
import { formatCrmCell, formatWidgetValue, percentShare, widgetAriaLabel } from "../../lib/crm";

const CHART_COLORS = [
  "var(--accent)",
  "var(--chart-2)",
  "var(--chart-1)",
  "var(--chart-3)",
  "var(--chart-5)",
  "var(--chart-6)",
  "var(--chart-4)",
  "var(--chart-7)",
];

function BarView({ series, format }: { series: WidgetSeriesItem[]; format?: "currency" | "number" }) {
  if (!series.length) return <p className="muted small">Sem dados para exibir.</p>;
  const maxVal = Math.max(...series.map((s) => Math.abs(s.value)), 1);
  return (
    <ul className="crm-w-bars" aria-label={widgetAriaLabel("bar", series, format)}>
      {series.map((item, idx) => {
        const pct = Math.max(4, Math.round((Math.abs(item.value) / maxVal) * 100));
        return (
          <li key={`${item.label}-${idx}`}>
            <div className="crm-w-bar__head">
              <span className="crm-w-bar__label">{item.label}</span>
              <strong className="crm-w-bar__val">{formatWidgetValue(item.value, format)}</strong>
            </div>
            <div className="bar" aria-hidden>
              <div
                className="bar__fill"
                data-crm-color={idx % CHART_COLORS.length}
                style={{ width: `${pct}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function FunnelView({ series, format }: { series: WidgetSeriesItem[]; format?: "currency" | "number" }) {
  if (!series.length) return <p className="muted small">Sem etapas com dados no funil.</p>;
  const maxVal = Math.max(...series.map((s) => Math.max(s.value, s.count)), 1);
  return (
    <ol className="crm-w-funnel" aria-label={widgetAriaLabel("funnel", series, format)}>
      {series.map((item, idx) => {
        const basis = item.value > 0 ? item.value : item.count;
        const pct = Math.max(14, Math.round((basis / maxVal) * 100));
        return (
          <li key={`${item.label}-${idx}`}>
            <div className="crm-w-funnel__meta">
              <span>{item.label}</span>
              <span className="muted small">{item.count} reg.</span>
            </div>
            <div className="crm-w-funnel__track">
              <div
                className="crm-w-funnel__bar"
                data-crm-color={idx % CHART_COLORS.length}
                style={{ width: `${pct}%` }}
              />
              <strong className="crm-w-funnel__val">{formatWidgetValue(item.value, format)}</strong>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function LineView({ series, format }: { series: WidgetSeriesItem[]; format?: "currency" | "number" }) {
  if (!series.length) return <p className="muted small">Sem série temporal disponível.</p>;
  const W = 720;
  const H = 170;
  const padX = 24;
  const padY = 18;
  const values = series.map((s) => s.value);
  const maxV = Math.max(...values, 1);
  const minV = Math.min(...values, 0);
  const span = Math.max(maxV - minV, 1);

  const points = series.map((item, idx) => {
    const x =
      series.length === 1 ? W / 2 : padX + (idx / (series.length - 1)) * (W - padX * 2);
    const y = H - padY - ((item.value - minV) / span) * (H - padY * 2);
    return { x, y, ...item };
  });

  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");
  const areaPath =
    points.length > 1
      ? `${linePath} L${points[points.length - 1]!.x.toFixed(1)},${H - padY} L${points[0]!.x.toFixed(1)},${H - padY} Z`
      : "";

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="crm-w-line__svg" role="img" aria-label={widgetAriaLabel("line", series, format)}>
        <line x1={padX} y1={H - padY} x2={W - padX} y2={H - padY} stroke="var(--border)" strokeWidth="1" />
        <line
          x1={padX}
          y1={padY}
          x2={W - padX}
          y2={padY}
          stroke="var(--border)"
          strokeDasharray="3 4"
          strokeWidth="1"
        />
        {areaPath && <path d={areaPath} fill="var(--accent-soft)" opacity="0.65" />}
        {points.length > 1 && (
          <path
            d={linePath}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
        {points.map((p, idx) => (
          <circle
            key={idx}
            cx={p.x}
            cy={p.y}
            r="4.5"
            fill="var(--accent)"
            stroke="var(--surface-solid)"
            strokeWidth="2"
          >
            <title>{`${p.label}: ${formatWidgetValue(p.value, format)}`}</title>
          </circle>
        ))}
      </svg>
      <div className="crm-w-line__legend">
        {series.slice(-6).map((s, idx) => (
          <span key={`${s.label}-${idx}`} className="crm-w-line__tick">
            <span className="muted small">{s.label}</span>
            <strong className="small">{formatWidgetValue(s.value, format)}</strong>
          </span>
        ))}
      </div>
    </div>
  );
}

function DonutView({ series, format }: { series: WidgetSeriesItem[]; format?: "currency" | "number" }) {
  const positive = series.filter((s) => s.value > 0);
  const total = positive.reduce((acc, s) => acc + s.value, 0);
  if (!positive.length || total <= 0) {
    return <p className="muted small">Sem dados positivos para distribuição.</p>;
  }

  const r = 56;
  const cx = 74;
  const cy = 74;
  const circ = 2 * Math.PI * r;
  let offset = 0;

  return (
    <div className="crm-w-donut">
      <svg viewBox="0 0 148 148" className="crm-w-donut__svg" role="img" aria-label={widgetAriaLabel("donut", positive, format)}>
        {positive.slice(0, 8).map((item, idx) => {
          const frac = item.value / total;
          const dash = frac * circ;
          const currentOffset = offset;
          offset += dash;
          return (
            <circle
              key={`${item.label}-${idx}`}
              cx={cx}
              cy={cy}
              r={r}
              fill="none"
              stroke={CHART_COLORS[idx % CHART_COLORS.length]}
              strokeWidth="20"
              strokeDasharray={`${dash} ${circ - dash}`}
              strokeDashoffset={-currentOffset}
              transform={`rotate(-90 ${cx} ${cy})`}
            >
              <title>{`${item.label}: ${formatWidgetValue(item.value, format)} (${percentShare(item.value, total)}%)`}</title>
            </circle>
          );
        })}
      </svg>
      <ul className="crm-w-donut__legend">
        {positive.slice(0, 6).map((item, idx) => (
          <li key={`${item.label}-${idx}`}>
            <span
              className="crm-w-dot"
              data-crm-color={idx % CHART_COLORS.length}
              aria-hidden
            />
            <span className="crm-w-donut__label">{item.label}</span>
            <strong>{percentShare(item.value, total)}%</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function WidgetChart({ widget }: { widget: DashboardWidget }) {
  const { result } = widget;

  if (widget.widget_type === "kpi") {
    return (
      <div className="stat">
        <strong className="stat__value">{formatWidgetValue(result.value ?? 0, result.format)}</strong>
        <span className="muted small">{result.count ?? 0} registro(s) no período</span>
      </div>
    );
  }

  if (widget.widget_type === "table") {
    const cols = result.columns ?? [];
    const rows = result.rows ?? [];
    if (!rows.length) return <p className="muted small">Nenhum registro encontrado.</p>;
    return (
      <div className="table-scroll" tabIndex={0} role="region" aria-label={widget.title}>
        <table className="crm-data-table">
          <thead>
            <tr>
              {cols.map((col) => (
                <th key={col.name}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={idx}>
                {cols.map((col) => (
                  <td key={col.name}>{formatCrmCell(row[col.name], col.type)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  const series = result.series ?? [];
  if (widget.widget_type === "bar") return <BarView series={series} format={result.format} />;
  if (widget.widget_type === "funnel") return <FunnelView series={series} format={result.format} />;
  if (widget.widget_type === "line") return <LineView series={series} format={result.format} />;
  return <DonutView series={series} format={result.format} />;
}
