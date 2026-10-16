import os

# Precisa vir antes de importar o app (as configurações são lidas na importação).
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "EMAIL_BACKEND": "memory",
        "SECRET_KEY": "chave-de-teste",
        "FRONTEND_URL": "http://web.local",
    }
)

import re  # noqa: E402
from collections.abc import Iterator  # noqa: E402

import pyotp  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402, F401
from app.core import email  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402

PASSWORD = "senha-forte-123"


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fks(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db() -> Iterator[Session]:
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    email.outbox.clear()
    with TestClient(app, headers={"X-Requested-With": "fetch"}) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def outbox() -> list[email.OutgoingEmail]:
    return email.outbox


def token_from(message: email.OutgoingEmail) -> str:
    match = re.search(r"token=([\w-]+)", message.body)
    assert match, f"nenhum link no e-mail: {message.body}"
    return match.group(1)


def create_verified_user(
    client: TestClient, outbox: list[email.OutgoingEmail], address: str = "ana@example.com"
) -> None:
    client.post("/api/auth/register", json={"email": address, "password": PASSWORD})
    token = token_from(outbox[-1])
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200


def login(client: TestClient, address: str = "ana@example.com", password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return client.post("/api/auth/login", json={"email": address, "password": password})


def enable_2fa(client: TestClient) -> tuple[pyotp.TOTP, list[str]]:
    setup = client.post("/api/auth/2fa/setup").json()
    otp = pyotp.TOTP(setup["secret"])
    response = client.post("/api/auth/2fa/enable", json={"code": otp.now()})
    assert response.status_code == 200, response.text
    return otp, response.json()["recovery_codes"]
