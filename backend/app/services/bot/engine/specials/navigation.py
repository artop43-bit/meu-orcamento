"""Navegação determinística ('onde encontro / como acesso X tela?')."""

from __future__ import annotations

import re
from typing import Any

from app.services.bot.lexicon import core, navigation
from app.services.bot.text_utils import normalize


def navigate(text: str) -> dict[str, Any] | None:
    place_words = {w for _, _, keys in navigation.PLACES for w in keys.split()}
    nav_stop = (
        core.COMMON_STOPWORDS
        | {
            "encontro",
            "encontrar",
            "acho",
            "achar",
            "fica",
            "ficam",
            "vejo",
            "ver",
            "posso",
            "faco",
            "fazer",
            "mudo",
            "mudar",
            "altero",
            "alterar",
            "troco",
            "trocar",
            "crio",
            "criar",
            "cadastro",
            "adiciono",
        }
    ) - place_words
    words = [
        w for w in re.split(r"[^a-z0-9/]+", normalize(text)) if len(w) >= 3 and w not in nav_stop
    ]
    found: list[tuple[int, str, str]] = []
    for label, path, keys in navigation.PLACES:
        terms = keys.split()
        score = 0
        for w in words:
            if w in terms:
                score += 3
            elif len(w) >= 5 and any(t.startswith(w[:5]) for t in terms):
                score += 1
        if score:
            found.append((score, label, path))
    if not found:
        return None
    found.sort(key=lambda t: -t[0])
    best = found[0][0]
    top = [f for f in found if f[0] >= best - 1][:3]
    first = top[0]
    return {
        "intent": "navigate",
        "answer": f"Fica em {first[1]}."
        if len(top) == 1
        else f"Pode ser em {first[1]} ou nestes lugares:",
        "items": [],
        "links": [{"label": label, "to": path} for _, label, path in top],
        "suggestions": [],
    }
