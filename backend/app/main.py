from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin, analysis, auth, budget, data, extras, health, market, money, planner
from app.core.config import DEFAULT_SECRET_KEY, get_settings
from app.core.errors import register_error_handlers
from app.core.rate_limit import client_ip
from app.core.request_context import RequestInfo, set_request_info

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "x-requested-with"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


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
    async def security(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Proteção contra CSRF: formulários de outros sites não conseguem enviar
        # cabeçalhos customizados, e o CORS bloqueia o fetch de origens não autorizadas.
        if (
            request.method not in SAFE_METHODS
            and request.url.path.startswith("/api/")
            and request.headers.get(CSRF_HEADER) != "fetch"
        ):
            response: Response = JSONResponse(
                {"error": "csrf", "message": "Requisição bloqueada por segurança."},
                status_code=403,
            )
        else:
            set_request_info(
                RequestInfo(
                    ip=client_ip(request),
                    user_agent=(request.headers.get("user-agent") or "")[:255] or None,
                )
            )
            response = await call_next(request)

        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        if request.url.path.startswith("/api/"):
            # Dados financeiros: nada de cache em navegador ou proxy.
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    register_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(budget.router, prefix="/api")
    app.include_router(analysis.router, prefix="/api")
    app.include_router(data.router, prefix="/api")
    app.include_router(planner.router, prefix="/api")
    app.include_router(market.router, prefix="/api")
    app.include_router(extras.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    app.include_router(money.router, prefix="/api")
    return app


app = create_app()
