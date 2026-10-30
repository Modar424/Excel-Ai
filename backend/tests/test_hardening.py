import asyncio
import threading
import time

import httpx
import pytest

from app.core.config import Settings
from app.main import create_app
from app.services import excel_service
from app.services.mock_provider import MockProvider
from tests.conftest import make_client

URL = "/api/v1/spreadsheets/generate"


def test_security_headers_on_api_and_docs():
    c = make_client(MockProvider())
    r = c.post(URL, json={"prompt": "inventory sheet", "max_rows": 5})
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "no-store" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    d = c.get("/docs")
    assert d.status_code == 200 and "content-security-policy" not in d.headers  # Swagger UI needs scripts
    assert c.get("/health").headers["x-content-type-options"] == "nosniff"


def test_prompt_control_and_bidi_chars_are_stripped():
    seen = {}

    class Spy(MockProvider):
        async def generate_spec(self, prompt, language, max_rows):
            seen["p"] = prompt
            return await super().generate_spec(prompt, language, max_rows)

    c = make_client(Spy())
    r = c.post(URL, json={"prompt": "inv\x00ent\x07ory\u202e sheet\u2066", "max_rows": 3})
    assert r.status_code == 200 and seen["p"] == "inventory sheet"
    assert c.post(URL, json={"prompt": "\x00\x01\x02\x03"}).status_code == 400  # nothing left after sanitising


@pytest.mark.asyncio
async def test_concurrent_builds_are_capped(monkeypatch):
    state = {"now": 0, "max": 0}
    lock = threading.Lock()
    real = excel_service.build_workbook

    def slow(spec, s=None, today=None):
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        time.sleep(0.15)
        try:
            return real(spec, s, today)
        finally:
            with lock:
                state["now"] -= 1

    monkeypatch.setattr("app.api.routes.build_workbook", slow)
    app = create_app(Settings(_env_file=None, groq_api_key="x", rate_limit_per_min=1000, max_concurrent_builds=2, ai_provider="mock"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        rs = await asyncio.gather(*[c.post(URL, json={"prompt": "inventory", "max_rows": 20}) for _ in range(8)])
    assert [r.status_code for r in rs] == [200] * 8 and state["max"] == 2


@pytest.mark.asyncio
async def test_busy_503_and_slot_released_after_timeout(monkeypatch):
    real = excel_service.build_workbook
    delay = {"s": 0.6}

    def slow(spec, s=None, today=None):
        time.sleep(delay["s"])
        return real(spec, s, today)

    monkeypatch.setattr("app.api.routes.build_workbook", slow)
    app = create_app(Settings(_env_file=None, groq_api_key="x", rate_limit_per_min=1000, max_concurrent_builds=1,
                              generation_timeout_s=0.2, ai_provider="mock"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        a, b = await asyncio.gather(c.post(URL, json={"prompt": "inventory", "max_rows": 5}),
                                    c.post(URL, json={"prompt": "inventory", "max_rows": 5}))
        assert sorted([a.status_code, b.status_code]) == [503, 504]
        busy = a if a.status_code == 503 else b
        assert busy.json()["error"]["code"] == "busy" and busy.headers["retry-after"] == "5"
        await asyncio.sleep(0.8)  # worker thread finished -> slot released
        delay["s"] = 0
        assert (await c.post(URL, json={"prompt": "inventory", "max_rows": 5})).status_code == 200


def test_cors_rejects_other_headers_and_origins():
    c = make_client(MockProvider())
    r = c.options(URL, headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                                "Access-Control-Request-Headers": "authorization,x-api-key"})
    assert r.status_code == 400 or "authorization" not in r.headers.get("access-control-allow-headers", "").lower()
