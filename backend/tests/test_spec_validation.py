import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.spreadsheet import ColumnSpec, SheetSpec, WorkbookSpec
from app.services.excel_service import build_workbook
from app.services.spreadsheet_service import sheet_name, validate_spec
from tests.conftest import MockProvider, make_client

S = Settings(_env_file=None, max_cols=5, max_sheets=2, max_header_len=10)


def spec(cols=("A", "B"), rows=(), title="T", n=1):
    return WorkbookSpec(title="W", sheets=[SheetSpec(title=title, columns=[ColumnSpec(name=c) for c in cols], rows=[list(r) for r in rows])] * n)


def test_ok():
    assert validate_spec(spec(rows=[(1, 2)]), S, 100).sheets[0].title == "T"


@pytest.mark.parametrize("sp", [
    spec(cols=("A", "B", "C", "D", "E", "F")),          # too many columns
    spec(cols=("a", "A")),                                # duplicate headers (case-insens.)
    spec(cols=("x" * 11,)),                               # header too long
    spec(cols=("  ",)),                                   # blank header
    spec(rows=[(1,), (2,)]),                              # row/column mismatch
    spec(rows=[(1, 2)] * 11),                             # too many rows for cap=10
    spec(n=3),                                            # too many sheets
])
def test_rejections(sp):
    with pytest.raises(AppError) as e:
        validate_spec(sp, S, 10)
    assert e.value.status == 422 and e.value.code == "invalid_spec"


def test_sheet_names_sanitised_unique():
    used = set()
    assert sheet_name("a/b:c*?[x]", used, 0) == "a b c   x"
    assert sheet_name("A B C   X", used, 1).endswith(" 2")
    assert sheet_name("", used, 2) == "Sheet3"
    assert len(sheet_name("z" * 80, set(), 0)) == 31


def test_row_count_clamped():
    sp = spec(rows=[(1, 2)])
    sp.sheets[0].row_count = 10**6
    assert validate_spec(sp, S, 10).sheets[0].row_count == 9


def test_many_columns_valid_letters():
    s = Settings(_env_file=None, max_cols=40)
    sp = spec(cols=[f"C{i}" for i in range(40)], rows=[list(range(40))])
    r = build_workbook(validate_spec(sp, s, 10), s)
    assert r.rows == 1 and len(r.data) > 1000


def test_invalid_spec_from_ai_returns_422():
    c = make_client(MockProvider(spec(cols=("A", "A"))))
    r = c.post("/api/v1/spreadsheets/generate", json={"prompt": "hello there"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_spec"
