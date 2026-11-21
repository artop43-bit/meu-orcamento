"""Extrator avançado de períodos (dias, semanas, meses, trimestres, semestres, anos, histórico)."""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.services.bot.contracts import PeriodSpec
from app.services.bot.lexicon import domain, intents
from app.services.bot.months import add_months, month_label, month_of, short_date, with_day

_THIS = r"(?:este|esse|neste|nesse|deste|desse|nesta|nessa|no|do)"
_MONTH_PATTERN = "|".join(sorted(domain.MONTH_NAMES_NORM, key=len, reverse=True))
_NUM_PATTERN = "|".join(sorted(domain.TEXT_NUMBERS, key=len, reverse=True))
_ALL_TIME_RE = re.compile(
    r"\b(?:"
    + "|".join(
        re.escape(t).replace(r"\ ", r"\s+")
        for t in sorted(intents.ALL_TIME_TRIGGERS, key=len, reverse=True)
    )
    + r")\b"
)
ALL_TIME_START = date(2000, 1, 1)


def _num(token: str) -> int:
    return int(token) if token.isdigit() else domain.TEXT_NUMBERS[token]


def _days_period(first: date, last: date, label: str, start_day: int) -> PeriodSpec:
    return PeriodSpec(
        start=month_of(first, start_day),
        end=month_of(last, start_day),
        label=label,
        explicit=True,
        day_start=first,
        day_end=last,
    )


def _cut(text: str, match: re.Match[str]) -> str:
    return " ".join((text[: match.start()] + " " + text[match.end() :]).split())


def _extract_all_time(
    text: str, current: date, today: date, start_day: int
) -> tuple[PeriodSpec, str] | None:
    if m := _ALL_TIME_RE.search(text):
        return (
            PeriodSpec(
                start=ALL_TIME_START,
                end=current,
                label="em todo o seu histórico",
                explicit=True,
                all_time=True,
            ),
            _cut(text, m),
        )
    return None


def _extract_month_range(
    text: str, current: date, today: date, start_day: int
) -> tuple[PeriodSpec, str] | None:
    if m := re.search(
        rf"\b(?:entre|de)\s+({_MONTH_PATTERN})(?:\s+(?:de\s+)?(20\d\d))?\s+(?:e|a|ate)\s+({_MONTH_PATTERN})(?:\s+(?:de\s+)?(20\d\d))?\b",
        text,
    ):
        y2 = int(m[4]) if m[4] else current.year
        m1_num = domain.MONTH_NAMES_NORM[m[1]]
        m2_num = domain.MONTH_NAMES_NORM[m[3]]
        y1 = int(m[2]) if m[2] else (y2 - 1 if m1_num > m2_num else y2)
        d1, d2 = date(y1, m1_num, 1), date(y2, m2_num, 1)
        if d1 > d2:
            d1, d2 = d2, d1
        return (
            PeriodSpec(
                start=d1,
                end=d2,
                label=f"entre {month_label(d1)} e {month_label(d2)}",
                explicit=True,
            ),
            _cut(text, m),
        )
    return None


def _extract_date_or_year_range(
    text: str, current: date, today: date, start_day: int
) -> tuple[PeriodSpec, str] | None:
    if m := re.search(
        r"\b(?:entre|de)\s+(\d{1,2})/(\d{1,2})(?:/(20\d\d))?\s+(?:e|a|ate)\s+(\d{1,2})/(\d{1,2})(?:/(20\d\d))?\b",
        text,
    ):
        try:
            y2 = int(m[6]) if m[6] else today.year
            y1 = int(m[3]) if m[3] else y2
            d1 = date(y1, int(m[2]), int(m[1]))
            d2 = date(y2, int(m[5]), int(m[4]))
            if d1 > d2:
                d1, d2 = d2, d1
            return (
                _days_period(d1, d2, f"entre {short_date(d1)} e {short_date(d2)}", start_day),
                _cut(text, m),
            )
        except ValueError:
            pass
    if m := re.search(r"\b(?:entre|de)\s+(20\d\d)\s+(?:e|a|ate)\s+(20\d\d)\b", text):
        y1, y2 = sorted((int(m[1]), int(m[2])))
        end = min(date(y2, 12, 1), current) if y2 == current.year else date(y2, 12, 1)
        return PeriodSpec(date(y1, 1, 1), end, f"entre {y1} e {y2}"), _cut(text, m)
    return None


def _extract_relative_days_and_weeks(
    text: str, current: date, today: date, start_day: int
) -> tuple[PeriodSpec, str] | None:
    if m := re.search(r"\b(?:de |desde )?(?:anteontem|antes de ontem|ante ontem)\b", text):
        d = today - timedelta(days=2)
        return _days_period(d, d, "anteontem", start_day), _cut(text, m)
    if m := re.search(r"\b(?:de )?ontem\b", text):
        d = today - timedelta(days=1)
        return _days_period(d, d, "ontem", start_day), _cut(text, m)
    if m := re.search(r"\b(?:de )?hoje\b", text):
        return _days_period(today, today, "hoje", start_day), _cut(text, m)
    if m := re.search(r"\b(?:n?a |d?a )?semana passada\b|\bultima semana\b", text):
        monday = today - timedelta(days=today.weekday() + 7)
        return _days_period(
            monday, monday + timedelta(days=6), "na semana passada", start_day
        ), _cut(text, m)
    if m := re.search(r"\b(?:n?es[st]a|d?es[st]a|na|da) semana\b", text):
        monday = today - timedelta(days=today.weekday())
        return _days_period(monday, today, "nesta semana", start_day), _cut(text, m)
    if m := re.search(r"\b(?:ultima quinzena|nos? ultimos? 15 dias)\b", text):
        return _days_period(
            today - timedelta(days=14), today, "nos últimos 15 dias", start_day
        ), _cut(text, m)
    if m := re.search(rf"\b(?:nos? )?ultimos?\s+(\d{{1,3}}|{_NUM_PATTERN})\s+dias\b", text):
        count = max(1, min(_num(m[1]), 730))
        return (
            _days_period(
                today - timedelta(days=count - 1), today, f"nos últimos {count} dias", start_day
            ),
            _cut(text, m),
        )
    if m := re.search(
        rf"\b(?:n?o |em |de )?(?:dia )?(\d{{1,2}})\s+de\s+({_MONTH_PATTERN})(?:\s+(?:de\s+)?(20\d\d))?\b",
        text,
    ):
        try:
            year = int(m[3]) if m[3] else today.year
            mon = domain.MONTH_NAMES_NORM[m[2]]
            d = date(year, mon, int(m[1]))
            if not m[3] and d > today:
                d = date(year - 1, mon, int(m[1]))
            return _days_period(d, d, f"em {short_date(d)}", start_day), _cut(text, m)
        except ValueError:
            pass
    if m := re.search(r"\b(?:n?o |em |de )?(?:dia )?(\d{1,2})/(\d{1,2})(?:/(20\d\d))?\b", text):
        try:
            year = int(m[3]) if m[3] else today.year
            d = date(year, int(m[2]), int(m[1]))
            if not m[3] and d > today:
                d = date(year - 1, int(m[2]), int(m[1]))
            return _days_period(d, d, f"em {short_date(d)}", start_day), _cut(text, m)
        except ValueError:
            pass
    if m := re.search(r"\b(?:n?o |em |de )?dia (\d{1,2})\b", text):
        number = int(m[1])
        if 1 <= number <= 31:
            mon = today.replace(day=1)
            if number > today.day:
                mon = add_months(mon, -1)
            d = with_day(mon, number)
            return _days_period(d, d, f"em {short_date(d)}", start_day), _cut(text, m)
    return None


def _extract_quarter_or_semester(
    text: str, current: date, today: date, start_day: int
) -> tuple[PeriodSpec, str] | None:
    if m := re.search(r"\b([1-4])[o°]?\s*trimestre(?:\s+(?:de\s+)?(20\d\d))?\b", text):
        q = int(m[1])
        y = int(m[2]) if m[2] else current.year
        start_m = (q - 1) * 3 + 1
        return (
            PeriodSpec(date(y, start_m, 1), date(y, start_m + 2, 1), f"no {q}º trimestre de {y}"),
            _cut(text, m),
        )
    if m := re.search(r"\b(?:n?este|n?esse|ultimo)\s+trimestre\b", text):
        return (
            PeriodSpec(add_months(current, -2), current, "nos últimos 3 meses"),
            _cut(text, m),
        )
    if m := re.search(r"\b([12])[o°]?\s*semestre(?:\s+(?:de\s+)?(20\d\d))?\b", text):
        s = int(m[1])
        y = int(m[2]) if m[2] else current.year
        start_m = 1 if s == 1 else 7
        return (
            PeriodSpec(date(y, start_m, 1), date(y, start_m + 5, 1), f"no {s}º semestre de {y}"),
            _cut(text, m),
        )
    return None


def _extract_relative_months_and_years(
    text: str, current: date, today: date, start_day: int
) -> tuple[PeriodSpec, str] | None:
    if m := re.search(rf"\b(?:nos? )?ultimos?\s+(\d{{1,2}}|{_NUM_PATTERN})\s+meses\b", text):
        count = max(1, min(_num(m[1]), 60))
        return (
            PeriodSpec(add_months(current, -(count - 1)), current, f"nos últimos {count} meses"),
            _cut(text, m),
        )
    if m := re.search(rf"\b(?:nos? )?ultimos?\s+(\d{{1,2}}|{_NUM_PATTERN})\s+anos\b", text):
        count = max(1, min(_num(m[1]), 10))
        start_y = current.year - (count - 1)
        return PeriodSpec(date(start_y, 1, 1), current, f"nos últimos {count} anos"), _cut(text, m)
    if m := re.search(r"\b(?:no |do )?(?:mes retrasado)\b", text):
        mon = add_months(current, -2)
        return PeriodSpec(mon, mon, f"em {month_label(mon)}"), _cut(text, m)
    if m := re.search(r"\b(?:no |do )?(?:mes passado|mes anterior|ultimo mes)\b", text):
        mon = add_months(current, -1)
        return PeriodSpec(mon, mon, f"em {month_label(mon)}"), _cut(text, m)
    if m := re.search(r"\b(?:no |do )?ano retrasado\b", text):
        y = current.year - 2
        return PeriodSpec(date(y, 1, 1), date(y, 12, 1), f"em {y}"), _cut(text, m)
    if m := re.search(r"\b(?:no |do )?ano passado\b", text):
        y = current.year - 1
        return PeriodSpec(date(y, 1, 1), date(y, 12, 1), f"em {y}"), _cut(text, m)
    if m := re.search(rf"\b{_THIS}\s+ano\b|\bano atual\b|\bnesse ano\b", text):
        return PeriodSpec(date(current.year, 1, 1), current, "neste ano"), _cut(text, m)
    if m := re.search(rf"\b{_THIS}\s+mes\b|\bmes atual\b", text):
        return PeriodSpec(current, current, "neste mês"), _cut(text, m)
    return None


def _extract_named_month_or_year(
    text: str, current: date, today: date, start_day: int
) -> tuple[PeriodSpec, str] | None:
    if m := re.search(
        rf"\b(?:em |de |no mes de )?({_MONTH_PATTERN})(?:\s+(?:de\s+)?(20\d\d))?\b", text
    ):
        num = domain.MONTH_NAMES_NORM[m[1]]
        year = int(m[2]) if m[2] else current.year - (1 if num > current.month else 0)
        mon = date(year, num, 1)
        return PeriodSpec(mon, mon, f"em {month_label(mon)}"), _cut(text, m)
    if m := re.search(r"\bdesde\s+(20\d\d)\b", text):
        y = int(m[1])
        return PeriodSpec(date(y, 1, 1), current, f"desde {y}"), _cut(text, m)
    if m := re.search(r"\b(?:em |de |no ano de |no ano |do ano de )?(20\d\d)\b", text):
        y = int(m[1])
        end = min(date(y, 12, 1), current) if y == current.year else date(y, 12, 1)
        return PeriodSpec(date(y, 1, 1), end, f"em {y}"), _cut(text, m)
    return None


_PERIOD_EXTRACTORS = (
    _extract_all_time,
    _extract_month_range,
    _extract_date_or_year_range,
    _extract_relative_days_and_weeks,
    _extract_quarter_or_semester,
    _extract_relative_months_and_years,
    _extract_named_month_or_year,
)


def extract_period(
    text: str, current: date, today: date, start_day: int = 1
) -> tuple[PeriodSpec | None, str]:
    """Extrai o primeiro período citado na frase e devolve o texto restante."""
    for matcher in _PERIOD_EXTRACTORS:
        if found := matcher(text, current, today, start_day):
            return found
    return None, text


def extract_periods(
    text: str, current: date, today: date, start_day: int = 1
) -> tuple[PeriodSpec | None, PeriodSpec | None, str]:
    p1, rest = extract_period(text, current, today, start_day)
    if p1 is None:
        return None, None, text
    p2, rest2 = extract_period(rest, current, today, start_day)
    return p1, p2, rest2


def default_month(current: date) -> PeriodSpec:
    return PeriodSpec(current, current, "neste mês", explicit=False)


def default_year(current: date) -> PeriodSpec:
    return PeriodSpec(date(current.year, 1, 1), current, "neste ano", explicit=False)


def default_all_time(current: date) -> PeriodSpec:
    return PeriodSpec(
        ALL_TIME_START, current, "em todo o seu histórico", explicit=False, all_time=True
    )
