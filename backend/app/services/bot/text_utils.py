"""Utilitários de texto, formatação em Real e pontuação lexical/fuzzy (100% Python padrão)."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from decimal import Decimal

from app.core.money import brl as _core_brl


def plain(text: str) -> str:
    """Minúsculas sem acento, preservando datas, valores e pontuação."""
    norm = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in norm if not unicodedata.combining(ch))


def normalize(text: str) -> str:
    """Minúsculas, sem acento e apenas [a-z0-9&] separados por espaço simples."""
    text = plain(text)
    return " ".join(part for part in re.split(r"[^a-z0-9&]+", text) if part)


def tokenize(text: str) -> list[str]:
    norm = normalize(text)
    return [tok for tok in norm.split() if tok]


def cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def brl(value: Decimal) -> str:
    return _core_brl(value, abs_val=True)


def signed_brl(value: Decimal) -> str:
    return ("−" if value < 0 else "") + brl(value)


def pct(part: Decimal, whole: Decimal) -> str:
    if not whole:
        return "0,0%"
    return f"{part / whole * 100:.1f}".replace(".", ",") + "%"


def within_one(a: str, b: str) -> bool:
    """Distância de edição <= 1 (troca, falta, sobra ou transposição adjacente)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return (
            len(diff) == 2
            and diff[1] == diff[0] + 1
            and a[diff[0]] == b[diff[1]]
            and a[diff[1]] == b[diff[0]]
        )
    short, long = (a, b) if la < lb else (b, a)
    i = 0
    while i < len(short) and short[i] == long[i]:
        i += 1
    return short[i:] == long[i + 1 :]


def trigrams(text: str) -> set[str]:
    padded = f"  {text} "
    return {padded[i : i + 3] for i in range(max(0, len(padded) - 2))}


def dice_trigram(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = trigrams(a), trigrams(b)
    if not ta or not tb:
        return 0.0
    return 2.0 * len(ta & tb) / (len(ta) + len(tb))


class BM25Index:
    """Índice BM25 leve em memória sobre documentos curtos do usuário."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = docs
        self.k1 = k1
        self.b = b
        self.n = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.n) if self.n else 1.0
        self.doc_freqs: Counter[str] = Counter()
        self.term_freqs: list[Counter[str]] = []
        for doc in docs:
            tf = Counter(doc)
            self.term_freqs.append(tf)
            for term in tf:
                self.doc_freqs[term] += 1

    def idf(self, term: str) -> float:
        df = self.doc_freqs.get(term, 0)
        return math.log(1.0 + (self.n - df + 0.5) / (df + 0.5))

    def score(self, query_tokens: list[str], doc_idx: int) -> float:
        if not self.n or doc_idx >= self.n:
            return 0.0
        doc = self.docs[doc_idx]
        if not doc:
            return 0.0
        tf = self.term_freqs[doc_idx]
        dl = len(doc)
        total = 0.0
        for q in query_tokens:
            freq = tf.get(q, 0)
            if not freq:
                continue
            idf = self.idf(q)
            denom = freq + self.k1 * (1.0 - self.b + self.b * (dl / self.avgdl))
            total += idf * (freq * (self.k1 + 1.0)) / denom
        return total
