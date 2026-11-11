"""Velocidade das telas com usuários reais (v1.7.5).

O navegador mede quanto cada tela levou para abrir e a pior travada, e manda só isso: o nome da
tela (de uma lista fixa) e os milissegundos. O servidor soma por dia e por tela. Nada identifica
a pessoa, o aparelho ou o endereço: é uma estatística anônima (LGPD, art. 12).
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.months import today_local
from app.models import PerfDaily

SCREENS = {
    "orcamento", "calendario", "cartoes", "contas", "revisar", "busca", "mensagens", "dividas",
    "divisoes", "metas", "historico", "analises", "investimentos", "ajustes", "relatorio",
    "admin", "outras",
}  # fmt: skip
SLOW_MS = 2500
MAX_MS = 60_000
RETENTION_DAYS = 90


def record(db: Session, samples: list[dict[str, Any]]) -> int:
    today = today_local()
    totals: dict[str, dict[str, int]] = {}
    for sample in samples[:20]:
        screen = sample.get("screen")
        load = int(sample.get("load_ms") or 0)
        frame = int(sample.get("frame_ms") or 0)
        if screen not in SCREENS or not 0 < load <= MAX_MS:
            continue
        t = totals.setdefault(
            str(screen), {"count": 0, "total": 0, "max": 0, "slow": 0, "frame": 0}
        )
        t["count"] += 1
        t["total"] += load
        t["max"] = max(t["max"], load)
        t["slow"] += 1 if load > SLOW_MS else 0
        t["frame"] += max(0, min(frame, 5000))
    for screen, t in totals.items():
        for attempt in range(2):
            row = db.get(PerfDaily, (today, screen))
            if row is None:
                row = PerfDaily(
                    day=today, screen=screen, count=0, total_ms=0, max_ms=0, slow=0, frame_ms=0
                )
                db.add(row)
            row.count += t["count"]
            row.total_ms += t["total"]
            row.max_ms = max(row.max_ms, t["max"])
            row.slow += t["slow"]
            row.frame_ms += t["frame"]
            try:
                db.commit()
                break
            except IntegrityError:  # outra requisição criou a linha do dia ao mesmo tempo
                db.rollback()
                if attempt:
                    raise
    return sum(t["count"] for t in totals.values())


def summary(db: Session, days: int = 7) -> list[dict[str, Any]]:
    since = today_local() - timedelta(days=days - 1)
    totals: dict[str, dict[str, int]] = {}
    for row in db.scalars(select(PerfDaily).where(PerfDaily.day >= since)):
        t = totals.setdefault(row.screen, {"count": 0, "total": 0, "max": 0, "slow": 0, "frame": 0})
        t["count"] += row.count
        t["total"] += row.total_ms
        t["max"] = max(t["max"], row.max_ms)
        t["slow"] += row.slow
        t["frame"] += row.frame_ms
    out = [
        {
            "screen": screen,
            "count": t["count"],
            "average_ms": round(t["total"] / t["count"]),
            "max_ms": t["max"],
            "slow_pct": round(t["slow"] / t["count"] * 100, 1),
            "frame_ms": round(t["frame"] / t["count"]),
        }
        for screen, t in totals.items()
        if t["count"]
    ]
    return sorted(out, key=lambda r: -r["average_ms"])


def cleanup(db: Session) -> int:
    limit = today_local() - timedelta(days=RETENTION_DAYS)
    return db.execute(delete(PerfDaily).where(PerfDaily.day < limit)).rowcount
