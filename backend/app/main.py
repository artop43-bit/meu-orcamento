from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, budget, health
from app.core.config import DEFAULT_SECRET_KEY, get_settings
from app.core.errors import register_error_handlers

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "x-requested-with"


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.is_production and settings.secret_key == DEFAULT_SECRET_KEY:
        raise RuntimeError("Defina SECRET_KEY antes de rodar em produção.")

    app = FastAPI(
        title="Meu Orçamento API",
        version="0.1.0",
        # Documentação interativa só fora de produção.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Content-Type", "X-Requested-With"],
    )

    @app.middleware("http")
    async def require_csrf_header(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Proteção contra CSRF: formulários de outros sites não conseguem enviar
        # cabeçalhos customizados, e o CORS bloqueia o fetch de origens não autorizadas.
        if (
            request.method not in SAFE_METHODS
            and request.url.path.startswith("/api/")
            and request.headers.get(CSRF_HEADER) != "fetch"
        ):
            return JSONResponse(
                {"error": "csrf", "message": "Requisição bloqueada por segurança."},
                status_code=403,
            )
        return await call_next(request)

    register_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(budget.router, prefix="/api")
    return app


app = create_app()
