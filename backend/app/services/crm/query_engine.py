"""Motor de consulta e agregação para widgets de Dashboards Personalizados."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.core.months import today_local
from app.services.crm.parsing import parse_date, parse_number

_LAST_DAYS = {"7d": 7, "30d": 30, "90d": 90}


def _in_range(raw_date: object, date_range: str, today: date) -> bool:
    """Com filtro de período, linha sem data (ou com data ilegível) fica de fora."""
    if date_range == "all":
        return True
    parsed = parse_date(raw_date) if raw_date not in (None, "") else None
    if not parsed:
        return False
    d = date.fromisoformat(parsed)
    if date_range in _LAST_DAYS:
        return today - timedelta(days=_LAST_DAYS[date_range] - 1) <= d <= today
    if date_range == "month":
        return d.year == today.year and d.month == today.month
    if date_range == "year":
        return d.year == today.year
    return True


def _int_option(query: dict[str, Any], key: str, default: int, warnings: list[str]) -> int:
    raw = query.get(key)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError, OverflowError):
        warnings.append(f"O limite '{raw}' não é um número; usando {default}.")
        return default


def _field_option(query: dict[str, Any], key: str, warnings: list[str]) -> str | None:
    raw = query.get(key)
    if raw in (None, ""):
        return None
    if isinstance(raw, str):
        return raw
    warnings.append(f"O campo '{key}' foi ignorado porque não é um nome de coluna.")
    return None


def _filters_option(query: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    raw = query.get("filters")
    if raw in (None, "", []):
        return []
    if not isinstance(raw, list):
        warnings.append("Os filtros foram ignorados porque não estão no formato de lista.")
        return []
    valid = [flt for flt in raw if isinstance(flt, dict) and isinstance(flt.get("field"), str)]
    if len(valid) != len(raw):
        warnings.append("Alguns filtros mal formados foram ignorados.")
    return valid


def _bucket_date(raw: object, bucket: str) -> str:
    iso = parse_date(raw)
    if not iso:
        return str(raw or "Sem data")
    if bucket == "month":
        return iso[:7]
    if bucket == "week":
        d = date.fromisoformat(iso)
        start = d - timedelta(days=d.weekday())
        return start.isoformat()
    return iso


def _matches_filters(row: dict[str, Any], filters: list[dict[str, Any]]) -> bool:
    for flt in filters:
        field = flt.get("field")
        op = flt.get("op", "eq")
        expected = flt.get("value")
        if not field or expected in (None, ""):
            continue
        actual = row.get(field)
        if op == "eq" and str(actual or "").strip().lower() != str(expected).strip().lower():
            return False
        if op == "neq" and str(actual or "").strip().lower() == str(expected).strip().lower():
            return False
        if op == "contains" and str(expected).strip().lower() not in str(actual or "").lower():
            return False
    return True


def _aggregate(values: list[float], metric: str, row_count: int) -> float:
    if metric == "count":
        return float(row_count)
    if not values:
        return 0.0
    if metric == "sum":
        return round(sum(values), 2)
    if metric == "avg":
        return round(sum(values) / len(values), 2)
    if metric == "min":
        return round(min(values), 2)
    if metric == "max":
        return round(max(values), 2)
    return float(row_count)


def run_widget_query(
    *,
    schema: list[dict[str, str]],
    rows: list[dict[str, Any]],
    widget_type: str,
    query: dict[str, Any],
    date_range: str = "all",
    today: date | None = None,
) -> dict[str, Any]:
    """Executa agregação determinística sobre qualquer DataSource (nativa, PDF, CSV ou API).

    Opções mal formadas na consulta não derrubam o painel: são ignoradas e viram `warnings`.
    """
    ref_today = today or today_local()
    col_types = {col["name"]: col.get("type", "text") for col in schema}
    if not isinstance(query, dict):
        query = {}
    warnings: list[str] = []

    date_field = _field_option(query, "date_field", warnings)
    if not date_field:
        date_field = next((c["name"] for c in schema if c.get("type") == "date"), None)

    filters = _filters_option(query, warnings)
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if date_range != "all" and not _in_range(
            row.get(date_field) if date_field else None, date_range, ref_today
        ):
            continue
        if filters and not _matches_filters(row, filters):
            continue
        filtered.append(row)

    metric = str(query.get("metric") or "count")
    value_field = _field_option(query, "value_field", warnings)
    if not value_field and metric != "count":
        value_field = next(
            (c["name"] for c in schema if c.get("type") in {"currency", "number"}),
            None,
        )
    value_format = "number"
    if metric != "count" and value_field and col_types.get(value_field) == "currency":
        value_format = "currency"

    if widget_type == "table":
        limit = max(1, min(_int_option(query, "limit", 12, warnings), 100))
        chosen = query.get("columns")
        if not isinstance(chosen, list):
            chosen = [c["name"] for c in schema[:6]]
        cols = [c for c in schema if c["name"] in chosen] or schema[:6]
        return _with_warnings(
            {
                "widget_type": "table",
                "columns": cols,
                "rows": filtered[:limit],
                "total_rows": len(filtered),
            },
            warnings,
        )

    if widget_type == "kpi":
        nums: list[float] = []
        if value_field:
            for row in filtered:
                parsed = parse_number(row.get(value_field))
                if parsed is not None:
                    nums.append(float(parsed))
        val = _aggregate(nums, metric, len(filtered))
        return _with_warnings(
            {
                "widget_type": "kpi",
                "value": val,
                "format": value_format,
                "count": len(filtered),
            },
            warnings,
        )

    group_by = _field_option(query, "group_by", warnings)
    if not group_by:
        if widget_type == "line" and date_field:
            group_by = date_field
        else:
            group_by = next(
                (c["name"] for c in schema if c.get("type") in {"text", "date"}),
                schema[0]["name"] if schema else None,
            )

    date_bucket = str(query.get("date_bucket") or ("month" if widget_type == "line" else "day"))
    is_date_group = bool(group_by and col_types.get(group_by) == "date")
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    order_seen: list[str] = []

    for row in filtered:
        raw_key = row.get(group_by) if group_by else "Total"
        if is_date_group and raw_key:
            label = _bucket_date(raw_key, date_bucket)
        else:
            label = str(raw_key).strip() if raw_key not in (None, "") else "Sem categoria"
        if label not in buckets:
            order_seen.append(label)
        buckets[label].append(row)

    series: list[dict[str, Any]] = []
    for label in order_seen:
        group_rows = buckets[label]
        nums = []
        if value_field:
            for row in group_rows:
                parsed = parse_number(row.get(value_field))
                if parsed is not None:
                    nums.append(float(parsed))
        series.append(
            {
                "label": label,
                "value": _aggregate(nums, metric, len(group_rows)),
                "count": len(group_rows),
            }
        )

    limit = max(1, min(_int_option(query, "limit", 12, warnings), 50))
    if widget_type == "line":
        series.sort(key=lambda item: item["label"])
        series = series[-limit:]
    elif widget_type == "funnel":
        stage_order = query.get("stage_order")
        if isinstance(stage_order, list) and stage_order:
            rank = {str(name): idx for idx, name in enumerate(stage_order)}
            series.sort(key=lambda item: rank.get(item["label"], 999))
        else:
            series.sort(key=lambda item: item["value"], reverse=True)
        series = series[:limit]
    else:
        series.sort(key=lambda item: item["value"], reverse=True)
        series = series[:limit]

    total = round(sum(item["value"] for item in series), 2)
    return _with_warnings(
        {
            "widget_type": widget_type,
            "format": value_format,
            "series": series,
            "total": total,
            "count": len(filtered),
        },
        warnings,
    )


def _with_warnings(result: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    if warnings:
        result["warnings"] = warnings
    return result
