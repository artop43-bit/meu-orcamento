import { useQuery } from "@tanstack/react-query";

import { crmApi, crmKeys, type DataSourceItem } from "../../api/crm";
import { formatCrmCell } from "../../lib/crm";
import { Sheet } from "../ui";

/** Janela modal para inspecionar os registros tabulares de uma fonte cadastrada. */
export function InspectSourceModal({
  source,
  onClose,
}: {
  source: DataSourceItem | null;
  onClose: () => void;
}) {
  const inspectQuery = useQuery({
    queryKey: source ? crmKeys.sourceRows(source.id) : ["crm", "source-rows", "none"],
    queryFn: () => crmApi.sourceRows(source!.id),
    enabled: Boolean(source),
  });

  return (
    <Sheet
      open={Boolean(source)}
      title={source ? `Dados · ${source.name}` : "Dados"}
      onClose={onClose}
      wide
    >
      {inspectQuery.isPending ? (
        <p className="muted small">Carregando registros…</p>
      ) : inspectQuery.data ? (
        <div className="stack">
          <p className="muted small">
            Exibindo {inspectQuery.data.rows.length} de {inspectQuery.data.total_rows} registro(s).
          </p>
          <div className="table-scroll" tabIndex={0} role="region" aria-label="Registros da fonte">
            <table className="crm-data-table">
              <thead>
                <tr>
                  {inspectQuery.data.columns.map((c) => (
                    <th key={c.name}>{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {inspectQuery.data.rows.map((row, idx) => (
                  <tr key={idx}>
                    {inspectQuery.data.columns.map((c) => (
                      <td key={c.name}>{formatCrmCell(row[c.name], c.type)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </Sheet>
  );
}
