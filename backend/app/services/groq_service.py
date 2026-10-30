"""Groq integration: structured output (mode chosen per model), bounded retries, quota/budget guards.
Model capability source: Groq docs "Structured Outputs" (console.groq.com/docs/structured-outputs), checked 2026-10-25."""
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Protocol

from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.spreadsheet import WorkbookSpec
from app.services.ai_schema import AI_SPEC_SCHEMA, build_messages, parse_spec

log = logging.getLogger("sheetcraft.groq")

STRICT_MODELS = {"openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b", "meta-models/muse-spark-open"}
SCHEMA_MODELS = STRICT_MODELS | {"openai/gpt-oss-safeguard-20b"}  # best-effort json_schema


class SpecProvider(Protocol):
    async def generate_spec(self, prompt: str, language: str, max_rows: int) -> WorkbookSpec: ...


def choose_mode(model: str, preferred: str = "auto") -> str:
    if preferred != "auto":
        return preferred
    return "strict" if model in STRICT_MODELS else "best_effort" if model in SCHEMA_MODELS else "json_object"


def response_format(mode: str) -> dict:
    if mode == "json_object":
        return {"type": "json_object"}
    return {"type": "json_schema", "json_schema": {"name": "workbook_spec", "strict": mode == "strict", "schema": AI_SPEC_SCHEMA}}


def _unavailable(msg="The AI service is currently unavailable.") -> AppError:
    return AppError(503, "ai_unavailable", msg)


def _quota(wait: int, msg: str) -> AppError:
    wait = max(1, min(int(wait), 86_400))
    return AppError(429, "ai_quota", msg, headers={"Retry-After": str(wait)}, extra={"retry_after": wait})


class GroqService:
    def __init__(self, settings: Settings, client=None, clock=time.monotonic):
        self.s, self._client, self.clock = settings, client, clock
        self.blocked_until = 0.0
        self._day, self._used = None, 0
        self._downgraded: set[str] = set()
        self.usage = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0}

    # ---- guards -------------------------------------------------------------------------------
    def _get_client(self):
        if self._client is None:
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=self.s.groq_api_key, timeout=self.s.groq_timeout_s, max_retries=0)
        return self._client

    def _guard(self) -> None:
        now = self.clock()
        if now < self.blocked_until:
            raise _quota(self.blocked_until - now, "The AI quota is exhausted. Please try again later.")
        utc = datetime.now(UTC)
        if utc.date() != self._day:
            self._day, self._used = utc.date(), 0
        if self._used >= self.s.ai_daily_budget:
            nxt = (utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            raise _quota((nxt - utc).total_seconds() + 1, "The daily AI usage budget has been reached. Please try again later.")
        self._used += 1
        self.usage["requests"] += 1

    # ---- error classification -----------------------------------------------------------------
    def _classify(self, exc: Exception) -> str:
        """Return 'retry' | 'timeout' | 'downgrade' | 'fallback' | 'invalid'; raise AppError for terminal errors."""
        import groq
        if isinstance(exc, groq.RateLimitError):
            try:
                wait = int(float(exc.response.headers.get("retry-after", 60)))
            except (ValueError, AttributeError):
                wait = 60
            wait = max(1, min(wait, 86_400))
            self.blocked_until = self.clock() + wait  # stop calling Groq until quota returns
            log.warning("groq rate limited; blocking %ss", wait)
            raise _quota(wait, "The AI quota is exhausted. Please try again later.")
        if isinstance(exc, (groq.AuthenticationError, groq.PermissionDeniedError)):
            log.error("groq auth/permission error (check GROQ_API_KEY)")
            raise _unavailable()
        if isinstance(exc, groq.APITimeoutError):
            return "timeout"
        if isinstance(exc, groq.APIConnectionError):
            return "retry"
        if isinstance(exc, groq.NotFoundError):
            return "fallback"
        if isinstance(exc, groq.BadRequestError):
            msg = str(exc).lower()
            if "does not support response format" in msg or ("json_schema" in msg and "support" in msg):
                return "downgrade"
            if "json_validate_failed" in msg or "does not match the expected schema" in msg or "failed to generate json" in msg:
                return "invalid"
            log.error("groq rejected request: 400")
            raise _unavailable("The AI service rejected the request.")
        if isinstance(exc, groq.APIStatusError) and exc.status_code >= 500:
            return "retry"
        log.error("groq unexpected error type=%s", type(exc).__name__)
        raise _unavailable()

    # ---- main ---------------------------------------------------------------------------------
    async def generate_spec(self, prompt: str, language: str, max_rows: int) -> WorkbookSpec:
        s = self.s
        if not s.groq_api_key:
            raise _unavailable("The AI service is not configured.")
        client, model = self._get_client(), s.groq_model
        attempts, hint, last, downgraded_once = 1 + max(0, s.groq_max_retries), None, "retry", False
        while attempts > 0:
            mode = "json_object" if model in self._downgraded else choose_mode(model, s.groq_structured_mode)
            msgs = build_messages(prompt, language, max_rows, s.max_cols, s.max_sheets, mode == "json_object", hint)
            self._guard()
            try:
                resp = await client.chat.completions.create(
                    model=model, messages=msgs, temperature=s.groq_temperature, max_tokens=s.groq_max_tokens,
                    response_format=response_format(mode))
            except Exception as exc:  # classified below; terminal ones raise AppError
                if isinstance(exc, AppError):
                    raise
                kind = self._classify(exc)
                if kind == "downgrade" and not downgraded_once:
                    self._downgraded.add(model)
                    downgraded_once = True
                    continue  # free correction, not counted as an attempt
                if kind == "fallback":
                    if s.groq_fallback_model and model != s.groq_fallback_model:
                        model = s.groq_fallback_model
                        continue
                    raise _unavailable() from None
                last = kind if kind in ("timeout", "retry") else last
                hint = "service error" if kind != "invalid" else "schema mismatch"
                attempts -= 1
                continue
            self._record_usage(model, resp)
            content, finish = None, None
            try:
                ch = resp.choices[0]
                content, finish = ch.message.content, getattr(ch, "finish_reason", None)
            except (AttributeError, IndexError, TypeError):
                pass
            try:
                if finish == "length":
                    raise ValueError("output truncated")
                return parse_spec(content)
            except ValidationError as e:
                err = e.errors()[0] if e.errors() else {}
                hint = f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('msg', 'invalid')}"[:140]
            except ValueError as e:
                hint = ("not valid JSON" if isinstance(e, json.JSONDecodeError) else str(e))[:100]
            last = "invalid"
            attempts -= 1
        log.warning("groq output unusable after retries (last=%s)", last)
        if last == "timeout":
            raise AppError(504, "timeout", "The AI service timed out.")
        if last == "invalid":
            raise AppError(422, "invalid_spec", "The AI returned an invalid specification. Please rephrase your request and try again.")
        raise _unavailable()

    def _record_usage(self, model: str, resp) -> None:
        u = getattr(resp, "usage", None)
        p, c = int(getattr(u, "prompt_tokens", 0) or 0), int(getattr(u, "completion_tokens", 0) or 0)
        self.usage["prompt_tokens"] += p
        self.usage["completion_tokens"] += c
        log.info("groq_usage model=%s prompt_tokens=%d completion_tokens=%d", model, p, c)  # counts only
