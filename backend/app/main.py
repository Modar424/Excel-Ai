import asyncio
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import RateLimiter
from app.services.groq_service import GroqService
from app.services.mock_provider import MockProvider
from app.services.openrouter_service import OpenRouterService

log = logging.getLogger("sheetcraft")


def _err(request: Request, status: int, code: str, message: str, headers=None, extra=None) -> JSONResponse:
    rid = getattr(request.state, "request_id", "-")
    body = {"error": {"code": code, "message": message, "request_id": rid, **(extra or {})}}
    return JSONResponse(body, status_code=status, headers={**(headers or {}), "X-Request-Id": rid})


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    app = FastAPI(title="SheetCraft AI API", version=s.app_version)
    app.state.settings = s
    app.state.limiter = RateLimiter(s.rate_limit_per_min)
    app.state.build_sem = asyncio.Semaphore(max(1, s.max_concurrent_builds))
    if s.ai_provider == "mock":
        log.warning("AI_PROVIDER=mock: deterministic fake AI for local testing only")
        app.state.provider = MockProvider()
    else:
        app.state.provider = GroqService(s) if s.ai_provider == "groq" else OpenRouterService(s)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex[:12]
        if request.method == "POST":
            length = request.headers.get("content-length")
            if length is None:
                return _err(request, 411, "length_required", "Content-Length header is required.")
            if not length.isdigit() or int(length) > s.max_request_bytes:
                return _err(request, 413, "payload_too_large", "Request body is too large.")
        response = await call_next(request)
        response.headers.setdefault("X-Request-Id", request.state.request_id)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        if not request.url.path.startswith(("/docs", "/redoc")):  # Swagger UI needs scripts; the API itself serves no HTML
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        return response

    # added last => outermost, so error responses from `guard` also carry CORS headers
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_list, allow_methods=["GET", "POST", "OPTIONS"],
                       allow_headers=["Content-Type"], max_age=600,
                       expose_headers=["Content-Disposition", "X-Rows-Generated", "X-Warnings", "X-Preview", "X-Request-Id", "Retry-After"])

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return _err(request, exc.status, exc.code, exc.message, exc.headers, exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []) if p != "body") or "request"
        return _err(request, 400, "invalid_request", f"Invalid value for '{field}'.")  # never echoes input

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _err(request, exc.status_code, code, "Request could not be processed.")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.error("unhandled error rid=%s type=%s", getattr(request.state, "request_id", "-"), type(exc).__name__)
        return _err(request, 500, "internal_error", "Unexpected server error.")

    app.include_router(router)
    return app


app = create_app()
