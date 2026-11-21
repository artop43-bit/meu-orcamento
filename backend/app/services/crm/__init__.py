"""Serviços da solução Dashboard & CRM (funil, contatos, PDF/CSV/APIs, painéis e pontes do Hub)."""

from app.services.crm import (
    api_connector,
    crm,
    csv_reader,
    dashboards,
    hub_bridge,
    parsing,
    pdf_reader,
    query_engine,
    sources,
)

__all__ = [
    "api_connector",
    "crm",
    "csv_reader",
    "dashboards",
    "hub_bridge",
    "parsing",
    "pdf_reader",
    "query_engine",
    "sources",
]
