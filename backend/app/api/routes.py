import asyncio

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import content_disposition
from app.schemas.spreadsheet import GenerateRequest
from app.services.excel_service import build_workbook
from app.services.groq_service import SpecProvider
from app.services.preview import encode_preview
from app.services.spreadsheet_service import validate_spec

router = APIRouter()
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_spec_provider(request: Request) -> SpecProvider:
    return request.app.state.provider  # singleton (keeps quota/budget state); tests override this dependency


def client_ip(request: Request, s: Settings) -> str:
    if s.trust_proxy:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _guarded_build(request: Request, spec, s: Settings):
    """At most `max_concurrent_builds` run at once. The slot is released only when the worker thread really
    finishes (even if the request already timed out), so timeouts cannot pile up memory."""
    sem: asyncio.Semaphore = request.app.state.build_sem
    try:
        await asyncio.wait_for(sem.acquire(), s.generation_timeout_s)
    except TimeoutError:
        raise AppError(503, "busy", "The server is busy. Please try again shortly.", headers={"Retry-After": "5"},
                       extra={"retry_after": 5}) from None
    fut = asyncio.ensure_future(run_in_threadpool(build_workbook, spec, s))

    def _done(f: asyncio.Future) -> None:
        sem.release()
        if not f.cancelled():
            f.exception()  # mark retrieved

    fut.add_done_callback(_done)
    return await asyncio.wait_for(asyncio.shield(fut), s.generation_timeout_s)


@router.get("/health", tags=["meta"])
async def health(s: Settings = Depends(get_settings_dep)):
    return {"status": "ok", "version": s.app_version, "ai": s.ai_provider}


@router.post("/api/v1/spreadsheets/generate", tags=["spreadsheets"], response_class=Response,
             responses={200: {"content": {XLSX: {}}, "description": "Excel workbook"}})
async def generate(req: GenerateRequest, request: Request, s: Settings = Depends(get_settings_dep),
                   provider: SpecProvider = Depends(get_spec_provider)):
    if len(req.prompt) > s.max_prompt_chars:
        raise AppError(400, "invalid_request", f"Prompt is too long (max {s.max_prompt_chars} characters).")
    rows_cap = req.max_rows or s.default_rows
    if rows_cap > s.max_rows:
        raise AppError(400, "invalid_request", f"max_rows must be between 1 and {s.max_rows}.")
    wait = request.app.state.limiter.check(client_ip(request, s))
    if wait:
        raise AppError(429, "rate_limited", "Too many requests. Please try again shortly.",
                       headers={"Retry-After": str(wait)}, extra={"retry_after": wait})
    try:
        spec = await asyncio.wait_for(provider.generate_spec(req.prompt, req.language, rows_cap), s.ai_total_timeout_s)
    except TimeoutError:
        raise AppError(504, "timeout", "The AI service timed out.") from None
    spec = validate_spec(spec, s, rows_cap)
    try:
        built = await _guarded_build(request, spec, s)
    except TimeoutError:
        raise AppError(504, "timeout", "Workbook generation timed out.") from None
    headers = {"Content-Disposition": content_disposition(spec.title), "X-Rows-Generated": str(built.rows),
               "Cache-Control": "no-store"}
    if built.warnings:
        headers["X-Warnings"] = str(len(built.warnings))  # details are written to the workbook's Notes section
    pv = encode_preview(built.preview, s.preview_max_bytes)
    if pv:
        headers["X-Preview"] = pv  # small base64(JSON) sample so the UI needs no second AI call
    return Response(content=built.data, media_type=XLSX, headers=headers)
