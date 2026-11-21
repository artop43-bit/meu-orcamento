"""Dashboards personalizados, widgets configuráveis e modelos prontos 1-clique."""

from __future__ import annotations

import threading
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.types import utcnow
from app.models import CrmDashboard, CrmPipeline, CrmStage, CrmWidget, DataSource
from app.services.crm import crm as crm_service
from app.services.crm import query_engine
from app.services.crm import sources as sources_service

WIDGET_TYPES = {"kpi", "bar", "line", "donut", "funnel", "table"}
DATE_RANGES = {"all", "7d", "30d", "90d", "month", "year"}


def _default_crm_widgets(
    dashboard_id: uuid.UUID,
    crm_source_id: uuid.UUID,
    contacts_source_id: uuid.UUID | None,
) -> list[CrmWidget]:
    return [
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=crm_source_id,
            title="Valor total em funil",
            widget_type="kpi",
            span=1,
            position=0,
            query_json={"metric": "sum", "value_field": "valor"},
        ),
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=crm_source_id,
            title="Negócios cadastrados",
            widget_type="kpi",
            span=1,
            position=1,
            query_json={"metric": "count"},
        ),
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=crm_source_id,
            title="Funil comercial por etapa",
            widget_type="funnel",
            span=1,
            position=2,
            query_json={"metric": "sum", "value_field": "valor", "group_by": "etapa"},
        ),
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=contacts_source_id or crm_source_id,
            title="Contatos por origem",
            widget_type="donut",
            span=1,
            position=3,
            query_json={"metric": "count", "group_by": "origem"},
        ),
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=crm_source_id,
            title="Evolução de negócios por mês",
            widget_type="line",
            span=2,
            position=4,
            query_json={
                "metric": "sum",
                "value_field": "valor",
                "group_by": "data",
                "date_bucket": "month",
            },
        ),
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=crm_source_id,
            title="Últimos negócios",
            widget_type="table",
            span=2,
            position=5,
            query_json={"columns": ["titulo", "cliente", "etapa", "valor", "data"], "limit": 8},
        ),
    ]


def _messaging_widgets(dashboard_id: uuid.UUID, msg_source_id: uuid.UUID) -> list[CrmWidget]:
    return [
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=msg_source_id,
            title="Mensagens registradas",
            widget_type="kpi",
            span=1,
            position=0,
            query_json={"metric": "count"},
        ),
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=msg_source_id,
            title="Enviadas vs Recebidas",
            widget_type="donut",
            span=1,
            position=1,
            query_json={"metric": "count", "group_by": "direcao"},
        ),
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=msg_source_id,
            title="Mensagens por contato",
            widget_type="bar",
            span=1,
            position=2,
            query_json={"metric": "count", "group_by": "contato"},
        ),
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=msg_source_id,
            title="Tipos de conteúdo",
            widget_type="donut",
            span=1,
            position=3,
            query_json={"metric": "count", "group_by": "tipo"},
        ),
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=msg_source_id,
            title="Movimento diário da Mensageria",
            widget_type="line",
            span=2,
            position=4,
            query_json={"metric": "count", "group_by": "data", "date_bucket": "day"},
        ),
    ]


def _budget_widgets(dashboard_id: uuid.UUID, budget_source_id: uuid.UUID) -> list[CrmWidget]:
    return [
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=budget_source_id,
            title="Volume de lançamentos",
            widget_type="kpi",
            span=1,
            position=0,
            query_json={"metric": "sum", "value_field": "valor"},
        ),
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=budget_source_id,
            title="Receitas vs Despesas",
            widget_type="donut",
            span=1,
            position=1,
            query_json={"metric": "sum", "value_field": "valor", "group_by": "tipo"},
        ),
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=budget_source_id,
            title="Totais por categoria",
            widget_type="bar",
            span=2,
            position=2,
            query_json={"metric": "sum", "value_field": "valor", "group_by": "categoria"},
        ),
        CrmWidget(
            dashboard_id=dashboard_id,
            source_id=budget_source_id,
            title="Evolução mensal",
            widget_type="line",
            span=2,
            position=3,
            query_json={
                "metric": "sum",
                "value_field": "valor",
                "group_by": "data",
                "date_bucket": "month",
            },
        ),
    ]


_DASHBOARD_LOCK = threading.Lock()


def ensure_default_dashboard(db: Session, user_id: uuid.UUID) -> list[CrmDashboard]:
    crm_service.ensure_default_pipeline(db, user_id)
    all_sources = sources_service.ensure_native_sources(db, user_id)
    with _DASHBOARD_LOCK:
        dashboards = list(
            db.scalars(
                select(CrmDashboard)
                .where(CrmDashboard.user_id == user_id)
                .order_by(CrmDashboard.is_default.desc(), CrmDashboard.created_at.asc())
            ).all()
        )
        if dashboards:
            return dashboards

        crm_src = next((s for s in all_sources if s.kind == "native_crm"), None)
        contacts_src = next((s for s in all_sources if s.kind == "native_crm_contacts"), None)
        dash = CrmDashboard(
            user_id=user_id,
            name="Visão Geral CRM",
            description="Acompanhe funil, receita estimada, origens e últimos negócios.",
            is_default=True,
            default_range="all",
        )
        db.add(dash)
        db.flush()
        if crm_src is not None:
            for widget in _default_crm_widgets(
                dash.id, crm_src.id, contacts_src.id if contacts_src else None
            ):
                db.add(widget)
        db.commit()
        db.refresh(dash)
        return [dash]


def list_dashboards(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    dashboards = ensure_default_dashboard(db, user_id)
    out = []
    for d in dashboards:
        count = len(db.scalars(select(CrmWidget.id).where(CrmWidget.dashboard_id == d.id)).all())
        out.append(
            {
                "id": d.id,
                "name": d.name,
                "description": d.description,
                "is_default": d.is_default,
                "default_range": d.default_range,
                "widgets_count": count,
                "created_at": d.created_at,
                "updated_at": d.updated_at,
            }
        )
    return out


def get_dashboard(db: Session, user_id: uuid.UUID, dashboard_id: uuid.UUID) -> CrmDashboard:
    dash = db.scalar(
        select(CrmDashboard).where(CrmDashboard.id == dashboard_id, CrmDashboard.user_id == user_id)
    )
    if dash is None:
        raise AppError(404, "dashboard_not_found", "Painel não encontrado.")
    return dash


def create_dashboard(
    db: Session,
    user_id: uuid.UUID,
    *,
    name: str,
    description: str | None = None,
    template: str = "blank",
    source_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    clean_name = (name or "").strip()[:100]
    if not clean_name:
        raise AppError(400, "invalid_name", "Informe o nome do painel.")
    all_sources = sources_service.ensure_native_sources(db, user_id)
    dash = CrmDashboard(
        user_id=user_id,
        name=clean_name,
        description=(description or "").strip()[:240] or None,
        is_default=False,
        default_range="all",
    )
    db.add(dash)
    db.flush()

    if template == "crm_overview":
        crm_src = next((s for s in all_sources if s.kind == "native_crm"), None)
        contacts_src = next((s for s in all_sources if s.kind == "native_crm_contacts"), None)
        if crm_src:
            for w in _default_crm_widgets(
                dash.id, crm_src.id, contacts_src.id if contacts_src else None
            ):
                db.add(w)
    elif template == "messaging_overview":
        msg_src = next((s for s in all_sources if s.kind == "native_messaging"), None)
        if msg_src:
            for w in _messaging_widgets(dash.id, msg_src.id):
                db.add(w)
    elif template == "budget_overview":
        budget_src = next((s for s in all_sources if s.kind == "native_budget"), None)
        if budget_src:
            for w in _budget_widgets(dash.id, budget_src.id):
                db.add(w)
    elif template == "dataset" and source_id is not None:
        src = sources_service.get_source(db, user_id, source_id)
        schema = list(src.schema_json or [])
        num_col = next((c["name"] for c in schema if c.get("type") in {"currency", "number"}), None)
        cat_col = next((c["name"] for c in schema if c.get("type") == "text"), None)
        date_col = next((c["name"] for c in schema if c.get("type") == "date"), None)
        pos = 0
        db.add(
            CrmWidget(
                dashboard_id=dash.id,
                source_id=src.id,
                title=f"Total de registros · {src.name}",
                widget_type="kpi",
                span=1,
                position=pos,
                query_json={"metric": "count"},
            )
        )
        pos += 1
        if num_col:
            db.add(
                CrmWidget(
                    dashboard_id=dash.id,
                    source_id=src.id,
                    title=f"Soma de {num_col}",
                    widget_type="kpi",
                    span=1,
                    position=pos,
                    query_json={"metric": "sum", "value_field": num_col},
                )
            )
            pos += 1
        if cat_col:
            db.add(
                CrmWidget(
                    dashboard_id=dash.id,
                    source_id=src.id,
                    title=f"Distribuição por {cat_col}",
                    widget_type="bar",
                    span=1 if date_col else 2,
                    position=pos,
                    query_json={
                        "metric": "sum" if num_col else "count",
                        "value_field": num_col,
                        "group_by": cat_col,
                    },
                )
            )
            pos += 1
        if date_col:
            db.add(
                CrmWidget(
                    dashboard_id=dash.id,
                    source_id=src.id,
                    title=f"Evolução por {date_col}",
                    widget_type="line",
                    span=1 if cat_col else 2,
                    position=pos,
                    query_json={
                        "metric": "sum" if num_col else "count",
                        "value_field": num_col,
                        "group_by": date_col,
                        "date_bucket": "month",
                    },
                )
            )
            pos += 1
        db.add(
            CrmWidget(
                dashboard_id=dash.id,
                source_id=src.id,
                title=f"Prévia · {src.name}",
                widget_type="table",
                span=2,
                position=pos,
                query_json={"columns": [c["name"] for c in schema[:6]], "limit": 10},
            )
        )

    db.commit()
    return get_dashboard_view(db, user_id, dash.id)


def delete_dashboard(db: Session, user_id: uuid.UUID, dashboard_id: uuid.UUID) -> None:
    dash = get_dashboard(db, user_id, dashboard_id)
    db.execute(delete(CrmWidget).where(CrmWidget.dashboard_id == dash.id))
    db.delete(dash)
    db.commit()


def get_dashboard_view(
    db: Session,
    user_id: uuid.UUID,
    dashboard_id: uuid.UUID,
    *,
    date_range: str | None = None,
) -> dict[str, Any]:
    """Carrega o painel com os resultados já agregados de cada widget."""
    dash = get_dashboard(db, user_id, dashboard_id)
    active_range = date_range if date_range in DATE_RANGES else dash.default_range
    widgets = list(
        db.scalars(
            select(CrmWidget)
            .where(CrmWidget.dashboard_id == dash.id)
            .order_by(CrmWidget.position.asc(), CrmWidget.created_at.asc())
        ).all()
    )

    source_cache: dict[
        uuid.UUID, tuple[DataSource, list[dict[str, str]], list[dict[str, Any]]]
    ] = {}
    stage_order = [
        s.name
        for s in db.scalars(
            select(CrmStage)
            .join(CrmPipeline, CrmPipeline.id == CrmStage.pipeline_id)
            .where(CrmPipeline.user_id == user_id)
            .order_by(CrmStage.position.asc())
        ).all()
    ]

    rendered_widgets: list[dict[str, Any]] = []
    for w in widgets:
        source_name = None
        result: dict[str, Any] = {
            "widget_type": w.widget_type,
            "series": [],
            "value": 0,
            "rows": [],
        }
        if w.source_id is not None:
            if w.source_id not in source_cache:
                src = db.scalar(
                    select(DataSource).where(
                        DataSource.id == w.source_id, DataSource.user_id == user_id
                    )
                )
                if src is not None:
                    try:
                        schema, rows = sources_service.load_source_data(db, user_id, src)
                        source_cache[w.source_id] = (src, schema, rows)
                    except AppError:
                        result = {
                            **result,
                            "warnings": ["Esta fonte de dados está indisponível para a sua conta."],
                        }
            cached = source_cache.get(w.source_id)
            if cached is not None:
                src, schema, rows = cached
                source_name = src.name
                q = dict(w.query_json) if isinstance(w.query_json, dict) else {}
                if (
                    w.widget_type == "funnel"
                    and src.kind == "native_crm"
                    and "stage_order" not in q
                ):
                    q["stage_order"] = stage_order
                try:
                    result = query_engine.run_widget_query(
                        schema=schema,
                        rows=rows,
                        widget_type=w.widget_type,
                        query=q,
                        date_range=active_range,
                    )
                except (TypeError, ValueError, KeyError, AttributeError):
                    # Um cartão com consulta estragada não derruba o painel inteiro.
                    result = {
                        **result,
                        "warnings": [
                            "Não foi possível calcular este cartão. Revise a configuração dele."
                        ],
                    }

        rendered_widgets.append(
            {
                "id": w.id,
                "dashboard_id": w.dashboard_id,
                "source_id": w.source_id,
                "source_name": source_name,
                "title": w.title,
                "widget_type": w.widget_type,
                "span": w.span,
                "position": w.position,
                "query": dict(w.query_json or {}),
                "result": result,
            }
        )

    return {
        "id": dash.id,
        "name": dash.name,
        "description": dash.description,
        "is_default": dash.is_default,
        "default_range": dash.default_range,
        "active_range": active_range,
        "widgets": rendered_widgets,
    }


def add_widget(
    db: Session,
    user_id: uuid.UUID,
    dashboard_id: uuid.UUID,
    *,
    source_id: uuid.UUID,
    title: str,
    widget_type: str,
    span: int = 1,
    query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dash = get_dashboard(db, user_id, dashboard_id)
    sources_service.get_source(db, user_id, source_id)
    if widget_type not in WIDGET_TYPES:
        raise AppError(400, "invalid_widget_type", "Tipo de gráfico não suportado.")
    clean_title = (title or "").strip()[:100]
    if not clean_title:
        raise AppError(400, "invalid_title", "Informe um título para o cartão.")
    existing = list(
        db.scalars(select(CrmWidget.position).where(CrmWidget.dashboard_id == dash.id)).all()
    )
    next_pos = (max(existing) + 1) if existing else 0
    widget = CrmWidget(
        dashboard_id=dash.id,
        source_id=source_id,
        title=clean_title,
        widget_type=widget_type,
        span=2 if span == 2 else 1,
        position=next_pos,
        query_json=query or {},
    )
    db.add(widget)
    dash.updated_at = utcnow()
    db.commit()
    return get_dashboard_view(db, user_id, dash.id)


def update_widget(
    db: Session,
    user_id: uuid.UUID,
    widget_id: uuid.UUID,
    changes: dict[str, Any],
) -> dict[str, Any]:
    widget = db.get(CrmWidget, widget_id)
    if widget is None:
        raise AppError(404, "widget_not_found", "Widget não encontrado.")
    dash = get_dashboard(db, user_id, widget.dashboard_id)
    if "title" in changes and changes["title"]:
        widget.title = str(changes["title"]).strip()[:100]
    if "widget_type" in changes and changes["widget_type"] in WIDGET_TYPES:
        widget.widget_type = changes["widget_type"]
    if "span" in changes and changes["span"] in (1, 2):
        widget.span = changes["span"]
    if "position" in changes and changes["position"] is not None:
        widget.position = int(changes["position"])
    if "source_id" in changes and changes["source_id"] is not None:
        sources_service.get_source(db, user_id, changes["source_id"])
        widget.source_id = changes["source_id"]
    if "query" in changes and changes["query"] is not None:
        widget.query_json = dict(changes["query"])
    widget.updated_at = utcnow()
    dash.updated_at = utcnow()
    db.commit()
    return get_dashboard_view(db, user_id, dash.id)


def delete_widget(db: Session, user_id: uuid.UUID, widget_id: uuid.UUID) -> None:
    widget = db.get(CrmWidget, widget_id)
    if widget is None:
        raise AppError(404, "widget_not_found", "Widget não encontrado.")
    get_dashboard(db, user_id, widget.dashboard_id)
    db.delete(widget)
    db.commit()
