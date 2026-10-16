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

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {"error": "validation_error", "message": _validation_message(exc)},
            status_code=422,
        )
