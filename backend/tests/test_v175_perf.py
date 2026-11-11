"""v1.7.5: desempenho — imagens em WebP, consultas ao banco contadas e métricas anônimas."""

import io
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from app.services import files
from tests.conftest import create_verified_user, login
from tests.test_analysis import MONTH, expense, income
from tests.test_budget import Outbox


@pytest.fixture
def user(client: TestClient, outbox: Outbox) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def photo(fmt: str, size: tuple[int, int] = (1200, 900)) -> bytes:
    image = Image.effect_noise(size, 40).convert("RGB")
    out = io.BytesIO()
    image.save(out, fmt, quality=95)
    return out.getvalue()


def test_uploads_are_stored_as_webp_and_smaller() -> None:
    raw = photo("JPEG")
    data, content_type, width, height = files.prepare(raw, "receipt")
    assert content_type == "image/webp" and len(data) < len(raw)
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "WEBP" and (width, height) == image.size
    # PNG com transparência continua transparente (sem perda).
    logo = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    logo.putpixel((10, 10), (255, 0, 0, 255))
    out = io.BytesIO()
    logo.save(out, "PNG")
    data, content_type, _, _ = files.prepare(out.getvalue(), "avatar")
    assert content_type == "image/webp"
    with Image.open(io.BytesIO(data)) as image:
        assert image.convert("RGBA").getpixel((10, 10)) == (255, 0, 0, 255)
        assert image.convert("RGBA").getpixel((0, 0))[3] == 0


@contextmanager
def count_queries(engine: Engine) -> Iterator[list[str]]:
    seen: list[str] = []

    def before(_conn, _cursor, statement, *_args) -> None:  # type: ignore[no-untyped-def]
        if statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", before)


# Telas principais: o número de consultas não pode crescer com a quantidade de lançamentos
# (o clássico "uma consulta para cada item da lista").
SCREENS = [
    f"/api/months/{MONTH}",
    f"/api/analysis/insights?month={MONTH}",
    f"/api/analysis/trends?until={MONTH}&months=12",
    f"/api/alerts?month={MONTH}",
    f"/api/daily?month={MONTH}",
    f"/api/analysis/pace?month={MONTH}",
    "/api/cards",
    "/api/goals",
    "/api/recurring",
    "/api/search?q=conta",
]


def test_query_count_does_not_grow_with_the_number_of_entries(
    user: TestClient, engine: Engine
) -> None:
    user.get(f"/api/months/{MONTH}")
    income(user, "5000")
    for _ in range(5):
        expense(user, "10", "Alimentação")

    def measure() -> dict[str, int]:
        out = {}
        for path in SCREENS:
            with count_queries(engine) as seen:
                response = user.get(path)
            assert response.status_code == 200, (path, response.text)
            out[path] = len(seen)
        return out

    small = measure()
    for index in range(40):
        expense(user, "10", ("Alimentação", "Transporte", "Lazer", "Saúde")[index % 4])
    large = measure()
    grew = {p: (small[p], large[p]) for p in SCREENS if large[p] > small[p] + 3}
    assert not grew, f"consultas cresceram com os lançamentos: {grew}"
    assert max(large.values()) <= 60, large


def test_screen_speed_is_stored_as_anonymous_totals(
    user: TestClient, client: TestClient, outbox: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "admin_emails", "admin@example.com")
    samples = [
        {"screen": "orcamento", "load_ms": 400, "frame_ms": 20},
        {"screen": "orcamento", "load_ms": 3000, "frame_ms": 60},
        {"screen": "analises", "load_ms": 900},
        {"screen": "tela-inventada", "load_ms": 100},  # fora da lista fixa: ignorada
    ]
    assert user.post("/api/perf", json={"samples": samples}).status_code == 204
    assert (
        user.post("/api/perf", json={"samples": [{"screen": "x", "load_ms": 0}]}).status_code == 422
    )
    # Só a administração vê; conta comum não.
    assert user.get("/api/admin/perf").status_code == 403
    user.post("/api/auth/logout")
    create_verified_user(client, outbox, "admin@example.com")
    login(client, "admin@example.com")
    rows = {r["screen"]: r for r in client.get("/api/admin/perf").json()}
    assert set(rows) == {"orcamento", "analises"}
    assert rows["orcamento"] == {
        "screen": "orcamento",
        "count": 2,
        "average_ms": 1700,
        "max_ms": 3000,
        "slow_pct": 50.0,
        "frame_ms": 40,
    }


def test_periods_summary_for_the_dashboard(user: TestClient) -> None:
    from datetime import date as day

    from app.core.months import format_month, today_local

    today = today_local()
    month = format_month(today.replace(day=1))
    previous = format_month((today.replace(day=1) - day.resolution).replace(day=1))
    user.get(f"/api/months/{month}")
    user.get(f"/api/months/{previous}")
    expense(user, "40", "Alimentação", month=month, due_date=today.isoformat())
    expense(user, "60", "Transporte", month=month, due_date=today.replace(day=1).isoformat())
    expense(user, "500", "Alimentação", month=previous, due_date=f"{previous}-01")
    out = user.get(f"/api/analysis/periods?month={month}").json()
    assert out["today"] == "40.00" and out["month"] == "100.00"
    assert float(out["week"]) in (40.0, 100.0)  # o dia 1 pode cair na mesma semana
    assert float(out["year"]) >= 100.0 and out["previous"] == "500.00"
    # O gasto do dia 1 do mês anterior entra no "mesmo trecho" em qualquer dia de hoje.
    assert out["previous_same_days"] == "500.00"
    assert [c["total"] for c in out["previous_by_category"]] == ["500.00"]
