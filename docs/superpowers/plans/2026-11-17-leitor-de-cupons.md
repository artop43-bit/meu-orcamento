# Leitor de cupons no lugar do Tesseract — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objetivo:** trocar o motor do "Ler comprovante (foto)" (Tesseract + regex) pela biblioteca
`leitor-comprovantes` (repositório `artop43-bit/Leitor-de-cupons`), mantendo a tela, a API e o
boleto funcionando exatamente como hoje.

**Arquitetura:** `backend/app/services/ocr.py` continua sendo a única porta de entrada. Ele chama
o leitor novo (instância única, criada na primeira leitura) e converte o `ResultadoComprovante`
no mesmo `Reading` de hoje. O boleto continua no código atual (`_find_boleto`), aplicado sobre o
texto que o leitor extraiu. As regex atuais viram plano B quando o leitor não acha total/itens.

**Stack:** FastAPI, Python 3.12, uv, `leitor-comprovantes` (RapidOCR/ONNX, OpenCV, PyMuPDF).

**Spec:** a conversa de 17/11/2026 (análise do repositório Leitor-de-cupons, seção "Cuidados para
integrar").

## Restrições globais

- A resposta de `POST /api/receipts/read` (`ReceiptReading`: kind, amount, date, description,
  items) não muda. O frontend não muda.
- Tudo local, sem serviço externo nem custo (regras 4 e 6 de "Regras de trabalho com o Claude").
- Uma leitura por vez no servidor (o `_LOCK = threading.Semaphore(1)` atual fica).
- Itens: no máximo 30 (`MAX_ITEMS`), e a lista só vale com 2 ou mais itens (regra da v1.5).
- Nome do item e do estabelecimento: `.title()` e no máximo 60 caracteres (igual hoje).
- Dependência fixada no commit `cd4be97b37a2b5876cc18a7df4687a2de974a675` (ou numa tag `v0.1.0`
  criada nesse commit).
- **Fora do escopo** (só sugestões, não entram sem pedido): ler PDF, mostrar a confiança ou os
  avisos da auditoria na tela, parcelamento, QR Code.

## Foco da revisão

1. **Foto real de celular no servidor ARM de 0,5 OCPU:** a leitura precisa terminar em tempo
   razoável (meta: menos de 40 s, o limite atual). Medir na VM depois do deploy; se passar, avisar
   antes de anunciar a versão.
2. **Leitor travado ou lento:** sem `subprocess`, não há mais o `timeout` de 40 s. O semáforo
   espera até 60 s e devolve `ocr_busy` (igual hoje); uma leitura travada prende a fila.
   Aceito nesta versão, registrado em Pendências.
3. **Erro interno do leitor** (imagem estranha, exceção do OpenCV/ONNX): tem que virar o 422
   `ocr_failed` de hoje, nunca 500. Teste na Tarefa 2.
4. **Cupom em que o leitor erra o total, mas a regex atual acerta:** plano B por campo (Tarefa 2).
5. **Primeira leitura depois do deploy** carrega os modelos (alguns segundos a mais). Aceito.

---

### Tarefa 1: Dependência e imagem Docker

**Arquivos:**
- Modificar: `backend/pyproject.toml` (lista `dependencies`)
- Modificar: `backend/uv.lock` (gerado)
- Modificar: `backend/Dockerfile:13-16`

- [ ] **Passo 1:** em `dependencies`, adicionar
  `"leitor-comprovantes @ git+https://github.com/artop43-bit/Leitor-de-cupons@cd4be97b37a2b5876cc18a7df4687a2de974a675"`.
- [ ] **Passo 2:** rodar `cd backend && uv lock`. Esperado: lock atualizado com
  `leitor-comprovantes`, `rapidocr-onnxruntime`, `onnxruntime`, `opencv-python`, `pymupdf`, e
  rodas `aarch64` disponíveis para `onnxruntime` e `opencv-python` (conferir no lock).
- [ ] **Passo 3:** no Dockerfile, trocar `tesseract-ocr tesseract-ocr-por` por
  `git libgl1 libglib2.0-0` (git para o uv baixar a dependência; libgl/glib porque o RapidOCR
  puxa o `opencv-python` com interface gráfica). Atualizar o comentário da linha 13.
- [ ] **Passo 4:** `docker build backend` local. Esperado: build ok; anotar o tamanho da imagem
  antes e depois (vai para o changelog/Pendências).
- [ ] **Passo 5:** commit `v1.6.0: leitor de cupons como dependência`.

### Tarefa 2: `ocr.py` usando o leitor

**Arquivos:**
- Modificar: `backend/app/services/ocr.py`
- Criar: `backend/tests/test_v16.py`
- Modificar: `backend/tests/test_v13.py:126,137`, `backend/tests/test_v15.py:101` (monkeypatch)

**Interfaces:**
- Consome: `leitor_comprovantes.LeitorComprovantes` (`.ler(bytes, tipo="imagem")`,
  `.ler_texto(str)`), `ResultadoComprovante` (campos `valor_total`, `data_hora: str | None`,
  `estabelecimento`, `itens[].descricao`, `itens[].valor_total`, `texto_extraido`).
- Produz (em `app.services.ocr`):
  - `available() -> bool` — `importlib.util.find_spec("leitor_comprovantes") is not None`.
  - `extract(image: bytes) -> ResultadoComprovante` — semáforo + `_leitor().ler(image, tipo="imagem")`;
    qualquer exceção do leitor → `AppError(422, "ocr_failed", <mesma mensagem de hoje>)`.
  - `from_result(result: ResultadoComprovante, today: date | None = None) -> Reading`.
  - `read(raw: bytes) -> Reading` — `files.prepare(raw, "receipt")` (validação de hoje), depois
    `from_result(extract(raw))`. Sai `read_text`, `_prepare` e o `subprocess`; `parse(text)` fica.

Regras de `from_result` (por campo, com plano B nas regex de hoje sobre `texto_extraido`):
1. `_find_boleto(texto)` acha boleto → devolve ele (igual hoje).
2. `amount = result.valor_total or _amount(texto)`.
3. `date = _date(result.data_hora or "", today) or _date(texto, today)`.
4. `description = estabelecimento limpo (.title()[:60]) or _description(texto)`.
5. `items` = itens do leitor com `valor_total > 0` e nome com 3+ letras, nome limpo como hoje;
   se o leitor não achar itens, `_items(texto)`. Aplicar `MAX_ITEMS` e o mínimo de 2.
6. `kind = "cupom" if amount or date else "desconhecido"`.

- [ ] **Passo 1: testes que falham**, em `test_v16.py` (sem carregar modelo: usar
  `LeitorComprovantes().ler_texto(...)`, que roda só o parser):

```python
from tests.test_v13 import CUPOM
from tests.test_v15 import NFCE

def leitura(texto): return LeitorComprovantes().ler_texto(texto)

def test_cupom_pelo_leitor_mantem_total_data_e_loja():
    r = ocr.from_result(leitura(CUPOM), today=date(2026, 10, 21))
    assert (r.kind, r.amount, r.date) == ("cupom", Decimal("44.88"), date(2026, 10, 20))
    assert r.description == "Supermercado Bom Preco Ltda"

def test_nfce_pelo_leitor_lista_cada_produto():
    r = ocr.from_result(leitura(NFCE), today=date(2026, 10, 21))
    assert r.amount == Decimal("43.39")
    assert [(i.description, i.amount) for i in r.items] == [
        ("Arroz Tipo 1 5Kg", Decimal("27.90")),
        ("Pastel De Queijo", Decimal("13.00")),
        ("Detergente Limpol 500Ml", Decimal("3.49")),
    ]

def test_boleto_continua_valendo():
    line = "23790.12345 60000.123456 78901.234567 8 12450000123456"
    r = ocr.from_result(leitura(f"Banco\nLinha digitável\n{line}\n"), today=date(2025, 10, 1))
    assert (r.kind, r.amount, r.date) == ("boleto", Decimal("1234.56"), date(2025, 10, 25))

def test_um_produto_so_nao_vira_lista():
    r = ocr.from_result(leitura("PADARIA\nPAO FRANCES 0,512 KG 9,20\nTOTAL 9,20\n"))
    assert r.items == []

def test_erro_do_leitor_vira_422(user, monkeypatch):
    # _leitor() devolve um objeto cujo .ler levanta RuntimeError
    ...  # POST /api/receipts/read → 422 e code "ocr_failed"
```

  Se o leitor der um resultado diferente do da v1.5 nesses textos (ex.: nome do item), **não
  ajustar o teste**: anotar a diferença e avisar o Arthur antes de seguir.
- [ ] **Passo 2:** `cd backend && uv run pytest tests/test_v16.py -v`. Esperado: FALHA
  (`from_result` não existe).
- [ ] **Passo 3:** implementar `available`, `extract`, `from_result`, `read` e `_leitor()`
  (instância única criada sob um `threading.Lock`) em `ocr.py`; atualizar a docstring do módulo
  (RapidOCR em vez de Tesseract).
- [ ] **Passo 4:** nos testes de endpoint da v1.3/v1.5, trocar
  `monkeypatch.setattr(ocr, "read_text", lambda raw: TEXTO)` por
  `monkeypatch.setattr(ocr, "extract", lambda raw: leitura(TEXTO))`.
- [ ] **Passo 5:** `uv run pytest && uv run ruff check . && uv run ruff format --check .`.
  Esperado: tudo verde.
- [ ] **Passo 6: teste com foto de verdade (local):** um teste `test_foto_real_de_cupom` que gera
  um PNG de cupom com Pillow (como `_criar_imagem_cupom_real` nos testes do leitor) e chama
  `ocr.read(png)` sem monkeypatch. Esperado: `amount` correto. Marcar `@pytest.mark.slow` só se
  passar de 20 s no CI.
- [ ] **Passo 7:** commit `v1.6.0: leitura de cupom pelo leitor novo`.

### Tarefa 3: Teste com cupons reais e versão

**Arquivos:**
- Criar: `changelog/2026-11-XX_v1.6.0.txt`
- Modificar: `frontend/src/release.ts`, `frontend/src/lib/releases.ts`

- [ ] **Passo 1:** ler 3 a 5 fotos reais de cupom (o Arthur manda, ou fotos já anexadas em
  despesas no ambiente local) com o motor antigo e o novo; montar uma tabela total/data/itens
  antigo × novo e mandar para o Arthur. Seguir só se o novo empatar ou ganhar.
- [ ] **Passo 2:** e2e local (`backend/e2e`) passando, fotos da tela de "Ler comprovante"
  (desktop e celular).
- [ ] **Passo 3:** changelog, `release.ts` e `releases.ts` no padrão de "Fluxo de versão e
  publicação" (horário estimado ≈ 56 min depois da abertura do PR).
- [ ] **Passo 4:** PR → CI → merge → Deploy, monitorando de 10 em 10 min e avisando no celular.
- [ ] **Passo 5:** na VM, ler uma foto real pelo site e anotar o tempo (Foco da revisão, item 1).
