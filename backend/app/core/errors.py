from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Erro de negócio com mensagem pronta para mostrar ao usuário."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _validation_message(exc: RequestValidationError) -> str:
    for error in exc.errors():
        field = str(error["loc"][-1]) if error.get("loc") else ""
        if "password" in field and error["type"] == "string_too_short":
            return f"A senha precisa ter pelo menos {error['ctx']['min_length']} caracteres."
        if "password" in field and error["type"] == "string_too_long":
            return "A senha é longa demais."
        if field == "email":
            return "Informe um e-mail válido."
    return "Verifique os dados informados."


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            {"error": exc.code, "message": exc.message}, status_code=exc.status_code
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {"error": "validation_error", "message": _validation_message(exc)},
            status_code=422,
        )
