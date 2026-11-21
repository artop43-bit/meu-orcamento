import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Calendar, Plus, Trash2 } from "lucide-react";

import { errorMessage } from "../../api/client";
import {
  crmApi,
  crmKeys,
  useDashboards,
  useDashboardView,
  useSources,
  type DashboardTemplate,
  type DateRangeKey,
  type WidgetType,
} from "../../api/crm";
import { WidgetChart } from "../../components/crm/WidgetChart";
import { EmptyGuide } from "../../components/help";
import { Alert, PageHeader, Sheet } from "../../components/ui";
import { announce } from "../../lib/announce";
import { DATE_RANGES, WIDGET_TYPE_LABELS } from "../../lib/crm";

export default function Dashboards() {
  const qc = useQueryClient();
  const dashboardsQuery = useDashboards();
  const sourcesQuery = useSources();
  const dashboards = useMemo(() => dashboardsQuery.data ?? [], [dashboardsQuery.data]);
  const sources = useMemo(() => sourcesQuery.data ?? [], [sourcesQuery.data]);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dateRange, setDateRange] = useState<DateRangeKey>("all");

  useEffect(() => {
    if (!selectedId && dashboards.length > 0) {
      setSelectedId(dashboards[0]!.id);
    }
  }, [dashboards, selectedId]);

  const viewQuery = useDashboardView(selectedId, dateRange);
  const view = viewQuery.data;

  // Janela: Novo painel
  const [newDashOpen, setNewDashOpen] = useState(false);
  const [dashName, setDashName] = useState("");
  const [dashDesc, setDashDesc] = useState("");
  const [dashTemplate, setDashTemplate] = useState<DashboardTemplate>("crm_overview");
  const [dashSourceId, setDashSourceId] = useState("");
  const [dashError, setDashError] = useState<string | null>(null);

  // Janela: Novo gráfico
  const [widgetOpen, setWidgetOpen] = useState(false);
  const [wTitle, setWTitle] = useState("");
  const [wSourceId, setWSourceId] = useState("");
  const [wType, setWType] = useState<WidgetType>("bar");
  const [wSpan, setWSpan] = useState<1 | 2>(1);
  const [wMetric, setWMetric] = useState<"count" | "sum" | "avg" | "min" | "max">("sum");
  const [wValueField, setWValueField] = useState("");
  const [wGroupBy, setWGroupBy] = useState("");
  const [wDateBucket, setWDateBucket] = useState<"day" | "week" | "month">("month");
  const [wError, setWError] = useState<string | null>(null);

  const selectedSource = useMemo(
    () => sources.find((s) => s.id === wSourceId) ?? sources[0] ?? null,
    [sources, wSourceId],
  );

  useEffect(() => {
    if (widgetOpen && !wSourceId && sources.length > 0) {
      setWSourceId(sources[0]!.id);
    }
  }, [widgetOpen, wSourceId, sources]);

  const createDash = useMutation({
    mutationFn: crmApi.createDashboard,
    onSuccess: (created) => {
      setNewDashOpen(false);
      setDashName("");
      setDashDesc("");
      setDashError(null);
      void qc.invalidateQueries({ queryKey: crmKeys.dashboards });
      setSelectedId(created.id);
      announce(`Painel "${created.name}" criado.`);
    },
    onError: (err) => setDashError(errorMessage(err)),
  });

  const deleteDash = useMutation({
    mutationFn: crmApi.deleteDashboard,
    onSuccess: () => {
      setSelectedId(null);
      void qc.invalidateQueries({ queryKey: crmKeys.dashboards });
      announce("Painel excluído.");
    },
  });

  const addWidget = useMutation({
    mutationFn: ({
      dashboardId,
      body,
    }: {
      dashboardId: string;
      body: Parameters<typeof crmApi.addWidget>[1];
    }) => crmApi.addWidget(dashboardId, body),
    onSuccess: () => {
      setWidgetOpen(false);
      setWTitle("");
      setWError(null);
      if (selectedId) {
        void qc.invalidateQueries({ queryKey: ["crm", "dashboard", selectedId] });
      }
      void qc.invalidateQueries({ queryKey: crmKeys.dashboards });
      announce("Gráfico adicionado ao painel.");
    },
    onError: (err) => setWError(errorMessage(err)),
  });

  const removeWidget = useMutation({
    mutationFn: crmApi.deleteWidget,
    onSuccess: () => {
      if (selectedId) {
        void qc.invalidateQueries({ queryKey: ["crm", "dashboard", selectedId] });
      }
      void qc.invalidateQueries({ queryKey: crmKeys.dashboards });
      announce("Gráfico removido.");
    },
  });

  function submitDashboard(event: FormEvent) {
    event.preventDefault();
    setDashError(null);
    createDash.mutate({
      name: dashName,
      description: dashDesc || undefined,
      template: dashTemplate,
      source_id: dashTemplate === "dataset" ? dashSourceId || sources[0]?.id || null : null,
    });
  }

  function submitWidget(event: FormEvent) {
    event.preventDefault();
    if (!selectedId || !selectedSource) return;
    setWError(null);
    addWidget.mutate({
      dashboardId: selectedId,
      body: {
        source_id: selectedSource.id,
        title: wTitle,
        widget_type: wType,
        span: wSpan,
        query: {
          metric: wMetric,
          ...(wValueField ? { value_field: wValueField } : {}),
          ...(wGroupBy ? { group_by: wGroupBy } : {}),
          ...(wType === "line" ? { date_bucket: wDateBucket } : {}),
        },
      },
    });
  }

  const numericCols = (selectedSource?.schema ?? []).filter(
    (c) => c.type === "currency" || c.type === "number",
  );
  const allCols = selectedSource?.schema ?? [];

  return (
    <div className="stack">
      <PageHeader
        title="Painéis"
        subtitle="Combine dados do CRM, Mensageria, Meu Orçamento, PDFs, CSV e APIs em gráficos personalizados."
        actions={
          <>
            <button type="button" className="btn btn--secondary" onClick={() => setNewDashOpen(true)}>
              <Plus size={16} aria-hidden />
              Novo painel
            </button>
            {selectedId && (
              <button type="button" className="btn btn--primary" onClick={() => setWidgetOpen(true)}>
                <Plus size={16} aria-hidden />
                Adicionar gráfico
              </button>
            )}
          </>
        }
      />

      <div className="list-tools list-tools--pills">
        <div className="chips" role="group" aria-label="Painéis disponíveis">
          {dashboards.map((d) => (
            <button
              key={d.id}
              type="button"
              aria-pressed={d.id === selectedId}
              className="chip-btn"
              onClick={() => setSelectedId(d.id)}
            >
              {d.name}
            </button>
          ))}
        </div>

        <div className="row">
          <label className="row">
            <Calendar size={15} aria-hidden />
            <span className="sr-only">Período do painel</span>
            <select
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value as DateRangeKey)}
              aria-label="Período do painel"
            >
              {DATE_RANGES.map(([val, label]) => (
                <option key={val} value={val}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {view && !view.is_default && (
            <button
              type="button"
              className="icon-btn"
              onClick={() => deleteDash.mutate(view.id)}
              aria-label="Excluir painel"
              title="Excluir painel"
            >
              <Trash2 size={16} aria-hidden />
            </button>
          )}
        </div>
      </div>

      {viewQuery.isPending ? (
        <div className="card">
          <p className="muted small">Carregando painel…</p>
        </div>
      ) : viewQuery.isError ? (
        <Alert tone="error">
          {errorMessage(viewQuery.error)}
        </Alert>
      ) : view ? (
        view.widgets.length === 0 ? (
          <EmptyGuide
            icon={<Calendar size={24} />}
            title="Este painel ainda não tem gráficos."
            text="Adicione o primeiro gráfico para acompanhar os dados desta solução."
            action={<button type="button" className="btn btn--primary" onClick={() => setWidgetOpen(true)}>
              <Plus size={16} aria-hidden />
              Adicionar primeiro gráfico
            </button>}
          />
        ) : (
          <div className="grid-2">
            {view.widgets.map((widget) => (
              <article
                key={widget.id}
                className={`card stack ${widget.span === 2 ? "crm-widget-card--wide" : ""}`}
              >
                <div className="split">
                  <div>
                    <h2 className="small">{widget.title}</h2>
                    {widget.source_name && <span className="muted small">{widget.source_name}</span>}
                  </div>
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={() => removeWidget.mutate(widget.id)}
                    aria-label={`Remover gráfico ${widget.title}`}
                    title="Remover gráfico"
                  >
                    <Trash2 size={15} aria-hidden />
                  </button>
                </div>
                <WidgetChart widget={widget} />
              </article>
            ))}
          </div>
        )
      ) : null}

      {/* Janela: Novo painel */}
      <Sheet open={newDashOpen} title="Novo painel" onClose={() => setNewDashOpen(false)}>
        <form className="inline-form stack" onSubmit={submitDashboard}>
          {dashError && (
            <Alert tone="error">
              {dashError}
            </Alert>
          )}
          <label className="field">
            <span className="field-label">Nome do painel</span>
            <input
              type="text"
              required
              placeholder="Ex.: Comercial + PDF de Vendas"
              value={dashName}
              onChange={(e) => setDashName(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Descrição (opcional)</span>
            <input
              type="text"
              placeholder="Resumo do que este painel acompanha"
              value={dashDesc}
              onChange={(e) => setDashDesc(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Modelo inicial</span>
            <select
              value={dashTemplate}
              onChange={(e) => setDashTemplate(e.target.value as DashboardTemplate)}
            >
              <option value="crm_overview">Visão CRM (funil, receita, origens e tabela)</option>
              <option value="messaging_overview">Mensageria · WhatsApp (volume e contatos ativos)</option>
              <option value="budget_overview">Meu Orçamento (receitas, despesas e categorias)</option>
              <option value="dataset">Gerar automático a partir de uma Fonte (PDF, CSV ou API)</option>
              <option value="blank">Painel em branco</option>
            </select>
          </label>
          {dashTemplate === "dataset" && (
            <label className="field">
              <span className="field-label">Fonte de dados</span>
              <select
                value={dashSourceId || sources[0]?.id || ""}
                onChange={(e) => setDashSourceId(e.target.value)}
              >
                {sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.row_count} reg.)
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="form-actions">
            <button type="button" className="btn btn--secondary" onClick={() => setNewDashOpen(false)}>
              Cancelar
            </button>
            <button type="submit" className="btn btn--primary" disabled={createDash.isPending}>
              {createDash.isPending ? "Criando…" : "Criar painel"}
            </button>
          </div>
        </form>
      </Sheet>

      {/* Janela: Adicionar gráfico */}
      <Sheet open={widgetOpen} title="Adicionar gráfico" onClose={() => setWidgetOpen(false)}>
        <form className="inline-form stack" onSubmit={submitWidget}>
          {wError && (
            <Alert tone="error">
              {wError}
            </Alert>
          )}
          <label className="field">
            <span className="field-label">Título do cartão</span>
            <input
              type="text"
              required
              placeholder="Ex.: Faturamento por cliente"
              value={wTitle}
              onChange={(e) => setWTitle(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Fonte de dados</span>
            <select
              value={selectedSource?.id ?? ""}
              onChange={(e) => {
                setWSourceId(e.target.value);
                setWValueField("");
                setWGroupBy("");
              }}
            >
              {sources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.row_count} reg.)
                </option>
              ))}
            </select>
          </label>
          <div className="grid-2">
            <label className="field">
              <span className="field-label">Tipo visual</span>
              <select value={wType} onChange={(e) => setWType(e.target.value as WidgetType)}>
                {(Object.entries(WIDGET_TYPE_LABELS) as [WidgetType, string][]).map(([k, label]) => (
                  <option key={k} value={k}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Largura no painel</span>
              <select value={wSpan} onChange={(e) => setWSpan(Number(e.target.value) as 1 | 2)}>
                <option value={1}>Meia largura (1 coluna)</option>
                <option value={2}>Largura inteira (2 colunas)</option>
              </select>
            </label>
          </div>

          {wType !== "table" && (
            <div className="grid-2">
              <label className="field">
                <span className="field-label">Cálculo</span>
                <select
                  value={wMetric}
                  onChange={(e) =>
                    setWMetric(e.target.value as "count" | "sum" | "avg" | "min" | "max")
                  }
                >
                  <option value="sum">Soma</option>
                  <option value="count">Contagem</option>
                  <option value="avg">Média</option>
                  <option value="max">Maior valor</option>
                  <option value="min">Menor valor</option>
                </select>
              </label>
              {wMetric !== "count" && (
                <label className="field">
                  <span className="field-label">Coluna numérica</span>
                  <select value={wValueField} onChange={(e) => setWValueField(e.target.value)}>
                    <option value="">Automática</option>
                    {numericCols.map((c) => (
                      <option key={c.name} value={c.name}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          )}

          {wType !== "kpi" && wType !== "table" && (
            <div className="grid-2">
              <label className="field">
                <span className="field-label">Agrupar por</span>
                <select value={wGroupBy} onChange={(e) => setWGroupBy(e.target.value)}>
                  <option value="">Automático</option>
                  {allCols.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </label>
              {wType === "line" && (
                <label className="field">
                  <span className="field-label">Agrupamento de data</span>
                  <select
                    value={wDateBucket}
                    onChange={(e) => setWDateBucket(e.target.value as "day" | "week" | "month")}
                  >
                    <option value="day">Por dia</option>
                    <option value="week">Por semana</option>
                    <option value="month">Por mês</option>
                  </select>
                </label>
              )}
            </div>
          )}

          <div className="form-actions">
            <button type="button" className="btn btn--secondary" onClick={() => setWidgetOpen(false)}>
              Cancelar
            </button>
            <button type="submit" className="btn btn--primary" disabled={addWidget.isPending}>
              {addWidget.isPending ? "Adicionando…" : "Adicionar"}
            </button>
          </div>
        </form>
      </Sheet>
    </div>
  );
}
