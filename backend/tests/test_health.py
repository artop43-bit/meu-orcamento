from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_unreachable_returns_503() -> None:
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise ConnectionError("db down")

    app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        response = client.get("/api/health/db")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["database"] == "unreachable"
