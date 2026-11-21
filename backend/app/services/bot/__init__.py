"""Motor composicional local do Tire sua dúvida (sem custo, sem serviço externo, sem IA).

Integrado a partir do laboratório `meu-orcamento-bot`: combina extração multi-filtro,
localizador universal BM25/fuzzy, guarda de finalidade (`out_of_scope`), correção
ortográfica protegida e navegação atualizada do Hub de Soluções.
"""

from app.services.bot.engine.responder import SUGGESTIONS, answer

__all__ = ["SUGGESTIONS", "answer"]
