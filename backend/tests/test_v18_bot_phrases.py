"""v1.8: jeitos diferentes de perguntar ao bot sobre empréstimos a amigos."""

import pytest
from fastapi.testclient import TestClient

from tests.test_data import user  # noqa: F401  (fixture)

PERSON = [
    "quanto o João ainda me deve?",
    "o joão me deve quanto?",
    "quanto joao me deve",
    "quanto falta o João me pagar do empréstimo?",
    "Quanto o joao silva me deve ainda",
]
GENERAL = ["quem me deve?", "quem está me devendo", "quanto me devem?"]
PROFIT = [
    "quanto lucrei com empréstimos?",
    "quanto de juros já recebi?",
    "quanto rendeu meus empréstimos",
]


@pytest.mark.parametrize("question", PERSON + GENERAL + PROFIT)
def test_phrases(user: TestClient, question: str) -> None:  # noqa: F811
    user.post(
        "/api/friend-loans",
        json={
            "person": "João Silva",
            "principal": "1000",
            "first_due": "2030-02-10",
            "mode": "total",
            "rate": "20",
            "count": 12,
        },
    )
    out = user.post("/api/ask", json={"question": question}).json()
    assert out["intent"] == "friend_loans", (question, out)
    if question in PERSON:
        assert "ainda te deve R$ 1.200,00" in out["answer"], out["answer"]
    elif question in PROFIT:
        assert "R$ 200,00" in out["answer"], out["answer"]
    else:
        assert "Te devem R$ 1.200,00" in out["answer"], out["answer"]
