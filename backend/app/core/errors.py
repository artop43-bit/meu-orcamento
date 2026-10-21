from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Erro de negócio com mensagem pronta para mostrar ao usuário."""

    def __init__(
        self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def _record_server_error(request: Request, exc: Exception) -> None:
    import logging
    import traceback

    from app.db.session import get_db
    from app.services import errors

    logging.getLogger("app").exception("Erro inesperado em %s", request.url.path, exc_info=exc)
    # Usa a mesma fábrica de sessões da API (nos testes, a sessão de teste).
    factory = request.app.dependency_overrides.get(get_db, get_db)
    session = factory()
    try:
        db = next(session)
        frames = traceback.format_exception(type(exc), exc, exc.__traceback__)
        errors.record(
            db,
            source="api",
            name=type(exc).__name__,
            message=str(exc),
            path=f"{request.method} {request.url.path}",
            user_agent=request.headers.get("user-agent"),
            release=None,
            detail="".join(frames[-6:]),
        )
    except Exception:  # o registro nunca pode derrubar a resposta
        logging.getLogger("app").warning("Não foi possível registrar o erro no painel.")
    finally:
        session.close()


def _validation_message(exc: RequestValidationError) -> str:
    for error in exc.errors():
        field = str(error["loc"][-1]) if error.get("loc") else ""
        if "password" in field and error["type"] == "string_too_short":
            return f"A senha precisa ter pelo menos {error['ctx']['min_length']} caracteres."
        if "password" in field and error["type"] == "string_too_long":
            return "A senha é longa demais."
        if field == "email":
            return "Informe um e-mail válido."
        if "amount" in field and error["type"] == "greater_than":
            return "O valor precisa ser maior que zero."
        if error["type"] == "decimal_max_places":
            return "Use no máximo 2 casas decimais."
        if error["type"] in ("decimal_max_digits", "decimal_whole_digits"):
            return "Valor alto demais."
        if field in ("description", "name") and error["type"] == "string_too_short":
            return "Informe uma descrição." if field == "description" else "Informe um nome."
        if field == "installments":
            return "O número de parcelas deve ser entre 2 e 120."
        if "Data inválida" in str(error.get("msg", "")) or (
            error["type"] == "string_pattern_mismatch" and "month" in field
        ):
            return "Data inválida: use um ano entre 2000 e 2100."
        if error["type"] in ("date_from_datetime_parsing", "date_parsing"):
            return "Data inválida. Use o formato dd/mm/aaaa."
        if field == "accept_terms":
            return "Para criar a conta, aceite os Termos de uso e a Política de privacidade."
    return "Verifique os dados informados."


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            {"error": exc.code, "message": exc.message},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        """Erro inesperado: registra no painel de erros (v1.3) e responde sem detalhes técnicos."""
        _record_server_error(request, exc)
        return JSONResponse(
            {
                "error": "internal_error",
                "message": "Erro inesperado no servidor. O problema foi registrado; tente de novo.",
            },
            status_code=500,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {"error": "validation_error", "message": _validation_message(exc)},
            status_code=422,
        )
