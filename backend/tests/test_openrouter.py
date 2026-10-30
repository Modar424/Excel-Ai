import json

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.services.openrouter_service import OpenRouterService

GOOD = {"title": "Employees", "rtl": False, "sheets": [{
    "title": "Data", "columns": [{"name": "Name", "type": "text"}, {"name": "Salary", "type": "currency"}],
    "rows": [], "row_count": 30, "generation_rules": [], "calculations": [], "notes": [], "synthetic": False}]}


def ok(content=None):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(GOOD) if content is None else content}, "finish_reason": "stop"}],
                                     "usage": {"prompt_tokens": 400, "completion_tokens": 200}})


def err(status, msg="x", headers=None):
    return httpx.Response(status, json={"error": {"code": status, "message": msg}}, headers=headers or {})


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def make(script, models="a:free,b:free,c:free", **kw):
    """script: list of responses/exceptions or a callable(request)->response."""
    calls = []

    def handler(req: httpx.Request):
        body = json.loads(req.content) if req.content else {}
        calls.append((req.url.path, body))
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        item = script(body) if callable(script) else script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    s = Settings(_env_file=None, openrouter_api_key="k", openrouter_models=models, openrouter_auto_discover=False, **kw)
    clock = Clock()
    svc = OpenRouterService(s, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), clock=clock)
    return svc, calls, clock


async def gen(svc):
    return await svc.generate_spec("employees table", "en", 100)


async def test_first_model_works():
    svc, calls, _ = make([ok()])
    spec = await gen(svc)
    assert spec.sheets[0].title == "Data" and svc.last_model == "a:free" and len(calls) == 1
    assert calls[0][1]["response_format"] == {"type": "json_object"}


async def test_busy_model_skipped_next_runs_and_cooldown_applies():
    svc, calls, clock = make([err(429, "provider rate limited"), ok()])
    await gen(svc)
    assert [c[1]["model"] for c in calls] == ["a:free", "b:free"] and svc.last_model == "b:free"
    calls.clear(); svc._client._transport.handler  # noqa: B018
    svc2 = svc
    svc2._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: ok()))
    await gen(svc2)  # 'a' still cooling down -> starts with 'b'
    assert svc2.last_model == "b:free"
    clock.t += 61
    await gen(svc2)
    assert svc2.last_model == "b:free"  # 'a' usable again, but 'b' has proven fast so it stays first
    assert "a:free" in await svc2._candidates()


@pytest.mark.parametrize("bad", [err(500), err(404, "no such model"), err(400, "bad"), httpx.ReadTimeout("t"), ok("not json"), ok("")])
async def test_any_failure_falls_through(bad):
    svc, calls, _ = make([bad, ok()])
    await gen(svc)
    assert svc.last_model == "b:free"


async def test_error_inside_200_body_is_handled():
    svc, _, _ = make([httpx.Response(200, json={"error": {"code": 429, "message": "upstream busy"}}), ok()])
    await gen(svc)
    assert svc.last_model == "b:free"


async def test_daily_limit_stops_everything():
    svc, calls, _ = make([err(429, "Rate limit exceeded: free-models-per-day", {"x-ratelimit-reset": "120"})])
    with pytest.raises(AppError) as e:
        await gen(svc)
    assert e.value.status == 429 and len(calls) == 1  # did NOT burn the other models
    with pytest.raises(AppError):
        await gen(svc)
    assert len(calls) == 1  # blocked locally, no new HTTP call


@pytest.mark.parametrize("status", [401, 402, 403])
async def test_auth_and_credit_errors_are_503(status):
    svc, calls, _ = make([err(status)])
    with pytest.raises(AppError) as e:
        await gen(svc)
    assert e.value.status == 503 and len(calls) == 1


async def test_all_models_busy_gives_friendly_503_and_respects_max_attempts():
    svc, calls, _ = make(lambda b: err(429), models="a:free,b:free,c:free,d:free,e:free", openrouter_max_attempts=3)
    with pytest.raises(AppError) as e:
        await gen(svc)
    assert e.value.status == 503 and len(calls) == 3


async def test_invalid_output_everywhere_is_422():
    svc, _, _ = make(lambda b: ok("{}"))
    with pytest.raises(AppError) as e:
        await gen(svc)
    assert e.value.status == 422


async def test_model_without_response_format_retried_plain_once_then_remembered():
    svc, calls, _ = make([err(400, "this model does not support response_format"), ok()])
    await gen(svc)
    assert svc.last_model == "a:free" and "response_format" not in calls[1][1]
    assert "a:free" in svc._plain
    svc._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: ok()))
    await gen(svc)


async def test_daily_budget_and_rpm_guards():
    svc, calls, clock = make(lambda b: ok(), openrouter_daily_budget=2, openrouter_rpm=10)
    await gen(svc); await gen(svc)
    with pytest.raises(AppError) as e:
        await gen(svc)
    assert e.value.status == 429 and len(calls) == 2
    svc, calls, clock = make(lambda b: ok(), openrouter_rpm=2)
    await gen(svc); await gen(svc)
    with pytest.raises(AppError):
        await gen(svc)
    clock.t += 61
    await gen(svc)


async def test_not_configured():
    s = Settings(_env_file=None, openrouter_api_key="")
    with pytest.raises(AppError) as e:
        await OpenRouterService(s).generate_spec("x", "en", 10)
    assert e.value.status == 503


async def test_auto_discovery_adds_free_structured_models_and_dedupes():
    data = {"data": [
        {"id": "x/big:free", "context_length": 131072, "supported_parameters": ["response_format"], "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "x/small:free", "context_length": 4096, "supported_parameters": ["response_format"], "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "x/paid", "context_length": 200000, "supported_parameters": ["response_format"], "pricing": {"prompt": "0.001", "completion": "0.002"}},
        {"id": "x/nojson:free", "context_length": 65536, "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "a:free", "context_length": 32000, "supported_parameters": ["response_format"], "pricing": {"prompt": "0", "completion": "0"}}]}

    def handler(req):
        return httpx.Response(200, json=data) if req.url.path.endswith("/models") else ok()
    s = Settings(_env_file=None, openrouter_api_key="k", openrouter_models="a:free", openrouter_auto_discover=True)
    svc = OpenRouterService(s, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await svc._candidates() == ["a:free", "x/big:free"]


# ---- staggered parallel race (speed) ----------------------------------------------------------
import asyncio  # noqa: E402
import time  # noqa: E402


def make_async(handler, models="a:free,b:free,c:free", **kw):
    s = Settings(_env_file=None, openrouter_api_key="k", openrouter_models=models, openrouter_auto_discover=False, **kw)
    return OpenRouterService(s, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_slow_model_does_not_block_next_one_starts_after_hedge_delay():
    started, cancelled = [], []

    async def handler(req):
        m = json.loads(req.content)["model"]
        started.append(m)
        if m == "a:free":
            try:
                await asyncio.sleep(30)  # hung free model
            except asyncio.CancelledError:
                cancelled.append(m); raise
        return ok()
    svc = make_async(handler, openrouter_hedge_delay_s=0.1)
    t0 = time.monotonic()
    await gen(svc)
    assert time.monotonic() - t0 < 2 and svc.last_model == "b:free"
    assert started == ["a:free", "b:free"] and cancelled == ["a:free"]  # the loser is cancelled


async def test_fast_model_means_single_request():
    calls = []

    def handler(req):
        calls.append(1); return ok()
    await gen(make_async(handler, openrouter_hedge_delay_s=0.1))
    assert len(calls) == 1  # no wasted quota when the first model answers quickly


async def test_parallel_cap_and_attempt_cap():
    live, peak, total = 0, 0, 0

    async def handler(req):
        nonlocal live, peak, total
        live += 1; total += 1; peak = max(peak, live)
        try:
            await asyncio.sleep(0.3)
            return err(503)
        finally:
            live -= 1
    svc = make_async(handler, models="a:free,b:free,c:free,d:free,e:free,f:free", openrouter_hedge_delay_s=0.05,
                     openrouter_parallel=2, openrouter_max_attempts=4)
    with pytest.raises(AppError):
        await gen(svc)
    assert peak <= 2 and total == 4


async def test_daily_limit_cancels_racers_immediately():
    async def handler(req):
        m = json.loads(req.content)["model"]
        if m == "a:free":
            await asyncio.sleep(30)
        return err(429, "Rate limit exceeded: free-models-per-day")
    svc = make_async(handler, openrouter_hedge_delay_s=0.05)
    t0 = time.monotonic()
    with pytest.raises(AppError) as e:
        await gen(svc)
    assert e.value.status == 429 and time.monotonic() - t0 < 2


async def test_learned_speed_reorders_models():
    svc, _, _ = make([ok(), ok()], models="a:free,b:free")
    svc.latency.update({"a:free": 9.0, "b:free": 1.0})
    assert (await svc._candidates())[0] == "b:free"
