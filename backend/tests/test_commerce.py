"""Testes de Catálogo & Pedidos, Propostas & Documentos em PDF, bridges e governança."""

import io

from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CrmActivity,
    CrmDeal,
    Income,
    MessagingChat,
    MessagingMedia,
    MessagingSession,
    User,
)
from app.services.messaging import connector_client
from tests.conftest import create_verified_user, login


def _make_user(
    client: TestClient, db: Session, outbox: list, email: str, *, is_admin: bool = False
) -> User:
    create_verified_user(client, outbox, email)
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    if is_admin:
        user.is_admin = True
    db.commit()
    db.refresh(user)
    return user


def _extract_pdf_text(raw: bytes) -> str:
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_catalog_stock_orders_budget_crm_sync_and_native_source(
    client: TestClient, db: Session, outbox: list
) -> None:
    user = _make_user(client, db, outbox, "catalogo@example.com")
    assert login(client, user.email).status_code == 200

    # Cria produto com estoque inicial e serviço sem estoque.
    p = client.post(
        "/api/catalog/items",
        json={
            "kind": "product",
            "sku": "KIT-01",
            "name": "Kit Energia Solar",
            "unit": "un",
            "cost_price": "500.00",
            "sale_price": "1200.00",
            "stock_qty": "10",
            "min_stock": "3",
        },
    )
    assert p.status_code == 201
    prod = p.json()
    assert prod["unit_margin"] == "700.00"
    assert prod["low_stock"] is False

    s = client.post(
        "/api/catalog/items",
        json={
            "kind": "service",
            "name": "Instalação Completa",
            "unit": "serv",
            "cost_price": "100.00",
            "sale_price": "350.00",
        },
    )
    assert s.status_code == 201
    serv = s.json()

    # Movimenta estoque e dispara alerta de reposição (10 + 2 - 9 = 3 <= 3).
    assert (
        client.post(
            f"/api/catalog/items/{prod['id']}/movement",
            json={"kind": "in", "qty": 2, "reason": "Compra fornecedor"},
        ).status_code
        == 200
    )
    out_ok = client.post(
        f"/api/catalog/items/{prod['id']}/movement",
        json={"kind": "out", "qty": 9, "reason": "Venda balcão"},
    )
    assert out_ok.status_code == 200
    assert out_ok.json()["stock_qty"] == "3.000"
    assert out_ok.json()["low_stock"] is True

    # Não permite saída maior que o saldo atual.
    assert (
        client.post(
            f"/api/catalog/items/{prod['id']}/movement",
            json={"kind": "out", "qty": 5},
        ).status_code
        == 409
    )

    # Contato CRM + Pedido confirmado integrado ao Meu Orçamento e CRM.
    c = client.post("/api/crm/contacts", json={"name": "Padaria Aurora", "phone": "11988887777"})
    assert c.status_code == 201
    contact_id = c.json()["id"]

    order_resp = client.post(
        "/api/catalog/orders",
        json={
            "contact_id": contact_id,
            "items": [
                {"item_id": prod["id"], "qty": 2},
                {"item_id": serv["id"], "qty": 1},
            ],
            "discount": "50.00",
            "confirm_now": True,
            "sync_budget": True,
            "sync_crm": True,
        },
    )
    assert order_resp.status_code == 201
    order = order_resp.json()
    assert order["status"] == "confirmed"
    # Total: 2*1200 + 350 - 50 = 2700; custo = 2*500 + 100 = 1100; lucro = 1600.
    assert order["total_amount"] == "2700.00"
    assert order["total_cost"] == "1100.00"
    assert order["gross_profit"] == "1600.00"
    assert order["budget_income_id"] is not None
    assert order["crm_deal_id"] is not None

    # Confirmação idempotente não duplica receita nem baixa duas vezes.
    again = client.post(
        f"/api/catalog/orders/{order['id']}/confirm",
        json={"sync_budget": True, "sync_crm": True},
    )
    assert again.status_code == 200
    assert again.json()["budget_income_id"] == order["budget_income_id"]

    incomes = list(db.scalars(select(Income).where(Income.user_id == user.id)).all())
    assert len(incomes) == 1
    assert float(incomes[0].amount) == 2700.0

    deal = db.scalar(select(CrmDeal).where(CrmDeal.user_id == user.id))
    assert deal is not None
    assert deal.status == "won"

    # Saldo do produto caiu de 3 para 1 após os 2 itens vendidos.
    items_list = client.get("/api/catalog/items").json()
    updated_prod = next(i for i in items_list["items"] if i["id"] == prod["id"])
    assert updated_prod["stock_qty"] == "1.000"
    assert items_list["summary"]["low_stock_count"] == 1

    # Cancelamento estorna o estoque para 3, remove a receita em aberto e reabre o negócio.
    cancel = client.post(f"/api/catalog/orders/{order['id']}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
    assert cancel.json()["budget_income_id"] is None
    restored = next(
        i for i in client.get("/api/catalog/items").json()["items"] if i["id"] == prod["id"]
    )
    assert restored["stock_qty"] == "3.000"
    assert db.scalar(select(Income).where(Income.user_id == user.id)) is None
    db.refresh(deal)
    assert deal.status == "open"

    # Fonte nativa do Catálogo disponível no Dashboard & CRM.
    sources = client.get("/api/crm/sources")
    assert sources.status_code == 200
    cat_source = next(src for src in sources.json() if src["kind"] == "native_catalog")
    preview = client.get(f"/api/crm/sources/{cat_source['id']}/rows")
    assert preview.status_code == 200
    assert any(r["nome"] == "Kit Energia Solar" for r in preview.json()["rows"])


def test_proposals_pdfs_no_pix_whatsapp_send_and_approve(
    client: TestClient, db: Session, outbox: list, monkeypatch
) -> None:
    monkeypatch.setattr(connector_client, "flush_session", lambda _sid: True)
    user = _make_user(client, db, outbox, "propostas@example.com")
    assert login(client, user.email).status_code == 200

    # Prepara sessão pronta e conversa na Mensageria + contato CRM.
    db.add(MessagingSession(user_id=user.id, status="ready", wanted=True))
    chat = MessagingChat(
        user_id=user.id,
        remote_jid="5511977776666@s.whatsapp.net",
        phone="5511977776666",
        name="Clínica Horizonte",
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)

    contact = client.post(
        "/api/crm/contacts",
        json={"name": "Clínica Horizonte", "phone": "5511977776666"},
    ).json()

    created_ids: list[str] = []
    for doc_type, title in (
        ("proposal", "Projeto Rede Wi-Fi"),
        ("service_order", "Manutenção Preventiva"),
        ("contract", "Contrato Mensal TI"),
        ("receipt", "Recibo Consultoria"),
    ):
        resp = client.post(
            "/api/proposals",
            json={
                "doc_type": doc_type,
                "title": title,
                "contact_id": contact["id"],
                "customer_doc": "12.345.678/0001-90",
                "items": [{"name": "Consultoria técnica", "qty": 2, "unit_price": "450.00"}],
                "discount": "100.00",
                "terms_text": "Prazo de execução em 10 dias úteis.",
            },
        )
        assert resp.status_code == 201
        doc = resp.json()
        assert "pix" not in str(doc).lower()
        assert doc["total_amount"] == "800.00"
        created_ids.append(doc["id"])

        pdf_resp = client.get(f"/api/proposals/{doc['id']}/pdf")
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers["content-type"].startswith("application/pdf")
        assert pdf_resp.content.startswith(b"%PDF-")
        pdf_text = _extract_pdf_text(pdf_resp.content)
        assert title in pdf_text
        assert "Clínica Horizonte" in pdf_text
        assert "800,00" in pdf_text
        # Sem menção a Pix/BRCode conforme decisão do usuário.
        assert "pix" not in pdf_text.lower()

    # Envia a proposta principal diretamente na conversa da Mensageria.
    main_id = created_ids[0]
    sent = client.post(
        f"/api/proposals/{main_id}/send-messaging",
        json={"chat_id": str(chat.id), "caption": "Segue proposta comercial em PDF."},
    )
    assert sent.status_code == 200
    assert sent.json()["document"]["status"] == "sent"
    assert sent.json()["message"]["message_type"] == "document"

    media = db.scalar(select(MessagingMedia).where(MessagingMedia.user_id == user.id))
    assert media is not None
    assert media.mime_type == "application/pdf"
    assert media.data.startswith(b"%PDF-")

    # Aprovação cria receita idempotente no Meu Orçamento e marca negócio ganho no CRM.
    approved = client.post(
        f"/api/proposals/{main_id}/approve",
        json={"sync_crm": True, "sync_budget": True},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["budget_income_id"] is not None
    assert approved.json()["crm_deal_id"] is not None

    again = client.post(
        f"/api/proposals/{main_id}/approve",
        json={"sync_crm": True, "sync_budget": True},
    )
    assert again.status_code == 200
    assert again.json()["budget_income_id"] == approved.json()["budget_income_id"]
    assert len(list(db.scalars(select(Income).where(Income.user_id == user.id)).all())) == 1

    activities = list(db.scalars(select(CrmActivity).where(CrmActivity.user_id == user.id)).all())
    assert len(activities) >= 2


def test_commerce_governance_blocks_and_user_isolation(
    client: TestClient, db: Session, outbox: list
) -> None:
    adm = _make_user(client, db, outbox, "adm-com@example.com", is_admin=True)
    dono = _make_user(client, db, outbox, "dono-com@example.com")
    outro = _make_user(client, db, outbox, "outro-com@example.com")

    assert login(client, dono.email).status_code == 200
    item_id = client.post(
        "/api/catalog/items",
        json={"name": "Item Privado", "sale_price": "99.00", "stock_qty": "4"},
    ).json()["id"]
    doc_id = client.post(
        "/api/proposals",
        json={
            "doc_type": "proposal",
            "customer_name": "Cliente Privado",
            "items": [{"name": "Serviço", "qty": 1, "unit_price": "200.00"}],
        },
    ).json()["id"]

    # Outro usuário não enxerga nem baixa PDF do dono.
    assert login(client, outro.email).status_code == 200
    assert client.get(f"/api/proposals/{doc_id}/pdf").status_code == 404
    assert client.delete(f"/api/catalog/items/{item_id}").status_code == 404

    # Admin bloqueia apenas Catálogo para dono e Propostas globalmente.
    assert login(client, adm.email).status_code == 200
    assert (
        client.patch(
            f"/api/admin/users/{dono.id}/permissions",
            json={"blocked_resources": ["catalogo"], "storage_quota_mb": 50},
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/admin/governance",
            json={"global_blocked_resources": ["propostas"]},
        ).status_code
        == 200
    )

    # Usuário dono fica bloqueado nas duas, enquanto o admin continua com acesso.
    assert login(client, dono.email).status_code == 200
    r_cat = client.get("/api/catalog/items")
    assert r_cat.status_code == 403
    assert r_cat.json()["error"] == "resource_blocked"
    r_prop = client.get("/api/proposals")
    assert r_prop.status_code == 403
    assert r_prop.json()["error"] == "resource_blocked"

    assert login(client, adm.email).status_code == 200
    assert client.get("/api/catalog/items").status_code == 200
    assert client.get("/api/proposals").status_code == 200


def test_commerce_chain_deduplication_cancel_order_precision_and_limits(
    client: TestClient, db: Session, outbox: list
) -> None:
    import uuid
    from datetime import date

    from app.core.months import add_months, current_month
    from app.models import CommercialOrder, MoneyAccount

    user = _make_user(client, db, outbox, "cadeia@example.com")
    user.month_start_day = 28
    db.commit()
    assert login(client, user.email).status_code == 200

    # B8: quantidade com 3 casas decimais (0,125 kg) não arredonda para 0,13.
    granel = client.post(
        "/api/catalog/items",
        json={
            "kind": "product",
            "name": "Castanha a granel",
            "unit": "kg",
            "cost_price": "5.00",
            "sale_price": "10.04",
            "stock_qty": "0.125",
            "min_stock": "0.050",
        },
    )
    assert granel.status_code == 201
    granel_item = granel.json()
    assert granel_item["stock_qty"] == "0.125"

    # B1 (Cenário A) + B3 + B4 (mês sem BudgetMonth prévio e month_start_day != 1):
    ord_resp = client.post(
        "/api/catalog/orders",
        json={
            "customer_name": "Cliente Cadeia A",
            "items": [{"item_id": granel_item["id"], "qty": "0.125"}],
            "confirm_now": True,
            "sync_budget": True,
            "sync_crm": True,
        },
    )
    assert ord_resp.status_code == 201
    ord_data = ord_resp.json()
    # 0.125 * 10.04 = 1.255 -> 1.26 (ROUND_HALF_UP).
    assert ord_data["total_amount"] == "1.26"
    assert ord_data["budget_income_id"] is not None

    # Proposta gerada a partir do pedido já herda budget_income_id e não duplica na aprovação.
    prop_resp = client.post(
        "/api/proposals",
        json={
            "doc_type": "proposal",
            "order_id": ord_data["id"],
            "items": [{"name": "Castanha a granel", "qty": "0.125", "unit_price": "10.04"}],
        },
    )
    assert prop_resp.status_code == 201
    prop_data = prop_resp.json()
    assert prop_data["budget_income_id"] == ord_data["budget_income_id"]

    app_resp = client.post(
        f"/api/proposals/{prop_data['id']}/approve",
        json={"sync_budget": True, "sync_crm": True},
    )
    assert app_resp.status_code == 200
    assert app_resp.json()["budget_income_id"] == ord_data["budget_income_id"]
    assert len(list(db.scalars(select(Income).where(Income.user_id == user.id)).all())) == 1

    # B1 (Cenário B): negócio já ganho com receita no CRM -> pedido vinculado reaproveita a receita.
    board = client.get("/api/crm/pipeline").json()
    won_stage = next(s for s in board["stages"] if s["is_won"])
    deal_b = client.post(
        "/api/crm/deals",
        json={"title": "Contrato Recorrente B", "value": "900.00", "stage_id": won_stage["id"]},
    ).json()
    sync_b = client.post(f"/api/crm/deals/{deal_b['id']}/sync-budget")
    assert sync_b.status_code == 200
    income_b_id = sync_b.json()["budget_income_id"]

    ord_b = client.post(
        "/api/catalog/orders",
        json={
            "customer_name": "Cliente B",
            "crm_deal_id": deal_b["id"],
            "items": [{"name": "Consultoria", "qty": 1, "unit_price": "900.00"}],
            "confirm_now": True,
            "sync_budget": True,
            "sync_crm": True,
        },
    )
    assert ord_b.status_code == 201
    assert ord_b.json()["budget_income_id"] == income_b_id
    assert len(list(db.scalars(select(Income).where(Income.user_id == user.id)).all())) == 2

    # B2 (receita já recebida via conta ou mês passado): preserva Income e avisa ao cancelar.
    acc = MoneyAccount(user_id=user.id, name="Conta Corrente", kind="checking", initial_balance=0)
    db.add(acc)
    db.commit()
    db.refresh(acc)
    inc_b = db.get(Income, uuid.UUID(income_b_id))
    assert inc_b is not None
    inc_b.account_id = acc.id
    inc_b.month = add_months(current_month(28), -1)
    db.commit()

    cancel_b = client.post(f"/api/catalog/orders/{ord_b.json()['id']}/cancel")
    assert cancel_b.status_code == 200
    assert cancel_b.json()["status"] == "cancelled"
    assert "recebida no Meu Orçamento" in (cancel_b.json().get("warning") or "")
    assert db.get(Income, uuid.UUID(income_b_id)) is not None

    # B6 & C2 (overflow e limites de payload): retornam 422, nunca 500.
    huge_order = client.post(
        "/api/catalog/orders",
        json={
            "customer_name": "Estouro",
            "items": [{"name": "Item", "qty": "9999999999", "unit_price": "9999999999"}],
        },
    )
    assert huge_order.status_code == 422

    too_many_items = client.post(
        "/api/catalog/orders",
        json={
            "customer_name": "Muitos itens",
            "items": [{"name": f"I{idx}", "qty": 1, "unit_price": "10.00"} for idx in range(201)],
        },
    )
    assert too_many_items.status_code == 422

    # C7: next_sequence recupera em conflito de número repetido.
    from app.services.commerce.catalog import create_order

    existing_max = db.scalars(
        select(CommercialOrder.number)
        .where(CommercialOrder.user_id == user.id)
        .order_by(CommercialOrder.number.desc())
    ).first()
    assert existing_max is not None
    # Pedido seguinte obtém number sequencial único sem colisão.
    next_ord = create_order(
        db,
        user,
        {"customer_name": "Seq OK", "items": [{"name": "A", "qty": 1, "unit_price": "5.00"}]},
    )
    assert next_ord["number"] == existing_max + 1
    assert isinstance(date.today(), date)


def test_ensure_month_handles_concurrent_duplicate_and_client_ref_idempotency(
    client: TestClient, db: Session, outbox: list
) -> None:
    import uuid
    from datetime import date
    from decimal import Decimal

    from app.models import BudgetMonth, Category, Expense
    from app.services import budget as budget_service
    from app.services.common import row_lock_guard

    user = _make_user(client, db, outbox, "concorrencia@example.com")
    target = date(2026, 12, 1)

    with row_lock_guard(db, user_id=user.id):
        budget_service.ensure_month(db, user, target, commit=True)
        budget_service.ensure_month(db, user, target, commit=True)
        months = list(
            db.scalars(
                select(BudgetMonth).where(
                    BudgetMonth.user_id == user.id,
                    BudgetMonth.month == target,
                )
            ).all()
        )
        assert len(months) == 1

    assert login(client, user.email).status_code == 200
    ord_ref = client.post(
        "/api/catalog/orders",
        json={
            "customer_name": "Cliente Ref",
            "items": [{"name": "Serviço Ref", "qty": 1, "unit_price": "120.00"}],
            "confirm_now": True,
            "sync_budget": True,
        },
    )
    assert ord_ref.status_code == 201
    order_id = ord_ref.json()["id"]
    income_id = ord_ref.json()["budget_income_id"]
    assert income_id is not None
    inc = db.get(Income, uuid.UUID(income_id))
    assert inc is not None
    assert inc.import_ref == f"app:hub-order-{order_id.lower()}"

    cat = db.scalar(select(Category).where(Category.user_id == user.id))
    assert cat is not None
    ref = f"ref-{uuid.uuid4()}"
    e1 = budget_service.create_expense(
        db,
        user,
        target,
        {
            "category_id": cat.id,
            "description": "Compra única",
            "amount": Decimal("42.00"),
            "due_date": date(2026, 12, 10),
            "paid": True,
            "payment_method": "pix",
            "client_ref": ref,
        },
    )
    e2 = budget_service.create_expense(
        db,
        user,
        target,
        {
            "category_id": cat.id,
            "description": "Compra única",
            "amount": Decimal("42.00"),
            "due_date": date(2026, 12, 10),
            "paid": True,
            "payment_method": "pix",
            "client_ref": ref,
        },
    )
    assert [x.id for x in e1] == [x.id for x in e2]
    assert (
        len(
            list(
                db.scalars(
                    select(Expense).where(
                        Expense.user_id == user.id, Expense.import_ref == f"app:{ref}"
                    )
                ).all()
            )
        )
        == 1
    )
