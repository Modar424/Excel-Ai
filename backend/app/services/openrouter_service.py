"""OpenRouter provider: rotates over FREE models; a busy/failing model is skipped (per-model cooldown) and the next one runs.
Limits source: OpenRouter docs (api/reference/limits, faq), read 2026-10-28: ':free' models = 20 req/min per account and
50 req/day (1000 after buying >= $10 credits once); negative balance -> 402 even on free models. Live behaviour (error bodies,
/models schema) is implemented from the documented OpenAI-compatible API and NOT yet verified against the real service."""
import asyncio
import json
import logging
import time
from collections import deque
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.spreadsheet import WorkbookSpec
from app.services.ai_schema import build_messages, parse_spec

log = logging.getLogger("sheetcraft.openrouter")

COOLDOWN_BUSY, COOLDOWN_GONE, COOLDOWN_BAD, DISCOVERY_TTL = 60, 900, 300, 3600


class _Fail(Exception):
    def __init__(self, kind: str):
        self.kind = kind


def _unavailable(msg="The AI service is currently unavailable.") -> AppError:
    return AppError(503, "ai_unavailable", msg)


def _quota(wait: float, msg: str) -> AppError:
    wait = max(1, min(int(wait), 86_400))
    return AppError(429, "ai_quota", msg, headers={"Retry-After": str(wait)}, extra={"retry_after": wait})


def _is_free(m: dict) -> bool:
    pr = m.get("pricing") or {}
    return str(m.get("id", "")).endswith(":free") or (str(pr.get("prompt")) in ("0", "0.0") and str(pr.get("completion")) in ("0", "0.0"))


class OpenRouterService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None, clock=time.monotonic):
        self.s, self._client, self.clock = settings, client, clock
        self.blocked_until = 0.0                    # account-wide stop (daily limit / no balance)
        self.cooldown: dict[str, float] = {}        # model -> usable again at (monotonic)
        self.latency: dict[str, float] = {}         # learned success latency (EWMA) per model
        self.streak: dict[str, int] = {}            # consecutive unusable outputs per model
        self._plain: set[str] = set()               # models that reject response_format
        self._day, self._used = None, 0
        self._minute: deque[float] = deque()
        self._disc: list[str] = []
        self._disc_at = -1e9
        self.usage = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0}
        self.last_model: str | None = None

    # ---- plumbing ----------------------------------------------------------------------------
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.s.openrouter_timeout_s)
        return self._client

    def _headers(self) -> dict:
        h = {"Authorization": f"Bearer {self.s.openrouter_api_key}", "Content-Type": "application/json", "X-Title": self.s.openrouter_app_title}
        if self.s.openrouter_site_url:
            h["HTTP-Referer"] = self.s.openrouter_site_url
        return h

    def _guard(self) -> None:
        now = self.clock()
        if now < self.blocked_until:
            raise _quota(self.blocked_until - now, "The AI quota is exhausted. Please try again later.")
        while self._minute and now - self._minute[0] > 60:
            self._minute.popleft()
        if len(self._minute) >= self.s.openrouter_rpm:
            raise _quota(61 - (now - self._minute[0]), "The AI service is busy. Please try again in a minute.")
        utc = datetime.now(UTC)
        if utc.date() != self._day:
            self._day, self._used = utc.date(), 0
        if self._used >= self.s.openrouter_daily_budget:
            nxt = (utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            raise _quota((nxt - utc).total_seconds() + 1, "The daily AI usage budget has been reached. Please try again later.")
        self._used += 1
        self._minute.append(now)
        self.usage["requests"] += 1

    # ---- model list --------------------------------------------------------------------------
    async def _discover(self) -> list[str]:
        if not self.s.openrouter_auto_discover:
            return []
        now = self.clock()
        if now - self._disc_at < DISCOVERY_TTL:
            return self._disc
        self._disc_at = now  # also throttles failures
        try:
            r = await self._http().get(self.s.openrouter_base_url.rstrip("/") + "/models", headers=self._headers(), timeout=8)
            r.raise_for_status()
            found = []
            for m in r.json().get("data", []):
                params = m.get("supported_parameters") or []
                if _is_free(m) and ("response_format" in params or "structured_outputs" in params) and int(m.get("context_length") or 0) >= 16_000:
                    found.append((int(m.get("context_length") or 0), m["id"]))
            self._disc = [i for _, i in sorted(found, reverse=True)][:12]
        except Exception as e:  # noqa: BLE001 - discovery is best effort
            log.warning("model discovery failed: %s", type(e).__name__)
        return self._disc

    async def _candidates(self) -> list[str]:
        cfg = [m.strip() for m in self.s.openrouter_models.split(",") if m.strip()]
        out: list[str] = []
        for m in cfg + await self._discover():
            if m not in out:
                out.append(m)
        now = self.clock()
        ready = [m for m in out if self.cooldown.get(m, 0) <= now]
        ready.sort(key=lambda m: self.latency.get(m, 12.0))  # stable: unknown models keep configured order; proven fast ones first
        return ready or out  # if everything is cooling down, still try (state may have changed)

    # ---- error handling ----------------------------------------------------------------------
    def _bench(self, model: str, secs: int) -> None:
        self.cooldown[model] = self.clock() + secs

    def _handle_error(self, model: str, status: int, body: dict | None, headers) -> str:
        """Returns 'next' to try another model; raises AppError for account-wide problems."""
        err = (body or {}).get("error") if isinstance(body, dict) else None
        msg = str((err or {}).get("message", "") if isinstance(err, dict) else err or "").lower()
        code = status
        if status == 200 and isinstance(err, dict):  # OpenRouter may return errors inside a 200 body
            try:
                code = int(err.get("code") or 0)
            except (TypeError, ValueError):
                code = 0
        if code in (401, 403):
            log.error("openrouter auth/permission error (check OPENROUTER_API_KEY)")
            raise _unavailable()
        if code == 402:
            log.error("openrouter 402: insufficient/negative credit balance")
            raise _unavailable("The AI service is currently unavailable.")
        if code == 429:
            if "per-day" in msg or "per day" in msg or "free-models-per-day" in msg:  # account-wide daily cap: other models won't help
                wait = 3600.0
                try:
                    reset = int(float(headers.get("x-ratelimit-reset", 0)))
                    wait = max(1.0, reset / 1000 - time.time()) if reset > 1e11 else max(1.0, float(reset))
                except (TypeError, ValueError):
                    nxt = (datetime.now(UTC) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    wait = (nxt - datetime.now(UTC)).total_seconds()
                self.blocked_until = self.clock() + wait
                log.warning("openrouter daily free limit reached; blocking %ss", int(wait))
                raise _quota(wait, "The AI quota is exhausted. Please try again later.")
            self._bench(model, COOLDOWN_BUSY)  # this model/provider is busy: try the next one
            return "next"
        if code in (404, 410):
            self._bench(model, COOLDOWN_GONE)  # model removed/renamed
            return "next"
        if code == 400:
            self._bench(model, COOLDOWN_BAD)
            return "next"
        self._bench(model, COOLDOWN_BUSY)  # 5xx, 408, provider errors
        return "next"

    # ---- one model, one attempt ----------------------------------------------------------------
    async def _attempt(self, model: str, prompt: str, language: str, max_rows: int) -> WorkbookSpec:
        """Runs ONE model. Returns a spec, raises _Fail(kind) for per-model problems or AppError for account-wide ones."""
        s = self.s
        url = s.openrouter_base_url.rstrip("/") + "/chat/completions"
        msgs = build_messages(prompt, language, max_rows, s.max_cols, s.max_sheets, True, None)
        body = {"model": model, "messages": msgs, "temperature": s.openrouter_temperature, "max_tokens": s.openrouter_max_tokens}
        if model not in self._plain:
            body["response_format"] = {"type": "json_object"}
        t0 = self.clock()
        for _ in range(2):  # 2nd pass only to retry once without response_format
            self._guard()
            try:
                r = await self._http().post(url, headers=self._headers(), json=body, timeout=s.openrouter_timeout_s)
            except httpx.TimeoutException:
                self._bench(model, COOLDOWN_BUSY); raise _Fail("timeout") from None
            except httpx.HTTPError:
                self._bench(model, COOLDOWN_BUSY); raise _Fail("unavailable") from None
            try:
                data = r.json()
            except ValueError:
                data = None
            is_err = r.status_code != 200 or (isinstance(data, dict) and "error" in data and not data.get("choices"))
            if is_err:
                em = json.dumps((data or {}).get("error", ""))[:300].lower() if isinstance(data, dict) else ""
                if r.status_code == 400 and "response_format" in body and any(k in em for k in ("response_format", "json", "structured")):
                    self._plain.add(model); body.pop("response_format", None); continue
                self._handle_error(model, r.status_code, data, r.headers)
                raise _Fail("unavailable")
            break
        self._record(model, data)
        try:
            ch = data["choices"][0]
            content, finish = ch["message"].get("content"), ch.get("finish_reason")
        except (KeyError, IndexError, TypeError, AttributeError):
            content, finish = None, None
        try:
            if finish == "length":
                raise ValueError("output truncated")
            spec = parse_spec(content)
        except (ValueError, ValidationError):
            self.streak[model] = self.streak.get(model, 0) + 1
            if self.streak[model] >= 3:
                self._bench(model, COOLDOWN_BAD)
            raise _Fail("invalid") from None
        self.streak[model] = 0
        lat = self.clock() - t0
        self.latency[model] = lat if model not in self.latency else 0.6 * self.latency[model] + 0.4 * lat  # learn who is fast
        self.last_model = model
        return spec

    # ---- main: staggered parallel race ---------------------------------------------------------
    async def generate_spec(self, prompt: str, language: str, max_rows: int) -> WorkbookSpec:
        """Start the best model; if it fails at once start the next immediately, if it is merely slow start the next after
        `hedge_delay`. First valid result wins, the others are cancelled."""
        s = self.s
        if not s.openrouter_api_key:
            raise _unavailable("The AI service is not configured.")
        queue = await self._candidates()
        running: dict[asyncio.Task, str] = {}
        started, last = 0, "unavailable"

        def launch() -> bool:
            nonlocal started
            if started >= s.openrouter_max_attempts or len(running) >= s.openrouter_parallel or not queue:
                return False
            m = queue.pop(0)
            running[asyncio.ensure_future(self._attempt(m, prompt, language, max_rows))] = m
            started += 1
            return True

        try:
            launch()
            while running:
                done, _ = await asyncio.wait(running, timeout=s.openrouter_hedge_delay_s, return_when=asyncio.FIRST_COMPLETED)
                if not done:          # everything running is slow -> add one more racer
                    launch()
                    continue
                failed = False
                for task in done:
                    running.pop(task)
                    try:
                        return task.result()
                    except _Fail as f:
                        failed = True
                        if not (f.kind == "unavailable" and last == "invalid"):
                            last = f.kind
                    # AppError (daily limit, auth, 402, local budget/RPM guard) is account-wide: propagates, `finally` cancels the rest
                if failed and not running:  # fast failover: nothing left running -> start the next model at once
                    launch()
        finally:
            for task in running:
                task.cancel()
            if running:
                await asyncio.gather(*running, return_exceptions=True)
        log.warning("openrouter: no model produced a usable result (last=%s, started=%d)", last, started)
        if last == "timeout":
            raise AppError(504, "timeout", "The AI service timed out.")
        if last == "invalid":
            raise AppError(422, "invalid_spec", "The AI returned an invalid specification. Please rephrase your request and try again.")
        raise _unavailable("All free AI models are busy right now. Please try again in a minute.")

    def _record(self, model: str, data: dict) -> None:
        u = (data or {}).get("usage") or {}
        p, c = int(u.get("prompt_tokens", 0) or 0), int(u.get("completion_tokens", 0) or 0)
        self.usage["prompt_tokens"] += p
        self.usage["completion_tokens"] += c
        log.info("openrouter_usage model=%s prompt_tokens=%d completion_tokens=%d", model, p, c)  # counts only
