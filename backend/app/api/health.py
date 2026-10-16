from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Verifica se a API está no ar."""
    return {"status": "ok"}


@router.get("/health/db")
def health_db(response: Response, db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """Verifica se a API consegue falar com o banco de dados."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "database": "unreachable"}
    return {"status": "ok", "database": "ok"}
