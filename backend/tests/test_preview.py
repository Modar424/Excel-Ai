import base64
import json

from app.services.mock_provider import MockProvider
from app.services.preview import encode_preview
from tests.conftest import make_client

URL = "/api/v1/spreadsheets/generate"


def decode(h):
    return json.loads(base64.b64decode(h).decode("utf-8"))


def mock_client(**kw):
    return make_client(MockProvider(), **kw)


def test_preview_header_arabic_3000_rows():
    r = mock_client().post(URL, json={"prompt": "أنشئ جدولًا للموظفين", "language": "ar", "max_rows": 3000})
    assert r.status_code == 200 and r.headers["x-rows-generated"] == "3000"
    pv = decode(r.headers["x-preview"])["sheets"][0]
    assert pv["name"] == "الموظفين" and pv["columns"][3] == "الراتب" and pv["total_rows"] == 3000 and pv["total_cols"] == 5
    assert pv["rows"][0][0] == 1 and pv["rows"][7][0] == 8 and len(pv["rows"]) == 8 and pv["rows"][0][1] == ""  # blank template, no invented people
    assert "إجمالي الرواتب" in pv["calcs"]
    assert len(r.headers["x-preview"]) < 8000


def test_preview_english_inventory_and_exposed_header():
    c = mock_client()
    r = c.post(URL, json={"prompt": "inventory sheet", "language": "en", "max_rows": 100}, headers={"Origin": "http://localhost:5173"})
    assert decode(r.headers["x-preview"])["sheets"][0]["name"] == "Inventory"
    assert "x-preview" in r.headers["access-control-expose-headers"].lower()


def test_preview_budget_shrinks_and_can_be_dropped():
    sheets = [{"name": f"S{i}", "columns": [f"col{j}" * 5 for j in range(40)], "rows": [["x" * 80] * 40] * 8,
               "total_rows": 9, "total_cols": 40, "synthetic": False, "calcs": ["c" * 100] * 20} for i in range(5)]
    h = encode_preview(sheets, 4500)
    d = decode(h)
    assert len(base64.b64decode(h)) <= 4500 and len(d["sheets"]) <= 3 and len(d["sheets"][0]["columns"]) <= 12
    assert encode_preview(sheets, 50) is None and encode_preview([], 4500) is None


def test_preview_dates_and_numbers_are_json_safe():
    from datetime import date
    sh = [{"name": "A", "columns": ["d", "n", "f", "b"], "rows": [[date(2026, 1, 2), 3, 1.23456789, True]], "total_rows": 1,
           "total_cols": 4, "synthetic": True, "calcs": []}]
    row = decode(encode_preview(sh))["sheets"][0]["rows"][0]
    assert row == ["2026-01-02", 3, 1.234568, "TRUE"]


def test_mock_triggers_and_health_reports_provider():
    c = mock_client()
    assert c.get("/health").json()["ai"] == "openrouter"  # Settings default; mock only via provider override in tests
    assert c.post(URL, json={"prompt": "x __quota__"}).status_code == 429
    assert c.post(URL, json={"prompt": "x __invalid__"}).status_code == 422
    assert c.post(URL, json={"prompt": "x __down__"}).status_code == 503


def test_ai_provider_mock_setting_wires_mock():
    c = mock_client(ai_provider="mock")
    assert c.get("/health").json()["ai"] == "mock"
