"""Phase 9: duplicate_count, missing_count, date_span_days, avg_days_between (values verified by LibreOffice)."""
import pytest

from app.services import ai_schema, formula_policy
from app.services.calculation_service import CalcError, Col, SheetInfo, build_formula
from app.services.excel_service import build_workbook
from app.services.spreadsheet_service import validate_spec
from app.schemas.spreadsheet import CalcSpec, SheetSpec
from tests.lo import recalc
from tests.test_engine import S, C, calc, needs_lo, wbspec

NEW = ["duplicate_count", "missing_count", "date_span_days", "avg_days_between"]
INFO = SheetInfo("T", [Col("Id", "text", "A"), Col("Start", "date", "B"), Col("End", "date", "C"), Col("Qty", "integer", "D")], 50)


def test_ai_schema_lists_new_kinds():
    assert all(k in ai_schema.CALC_KINDS for k in NEW)
    enum = ai_schema.AI_SPEC_SCHEMA["properties"]["sheets"]["items"]["properties"]["calculations"]["items"]["properties"]["kind"]["enum"]
    assert all(k in enum for k in NEW)


@pytest.mark.parametrize("kind,kw", [("duplicate_count", {"column": "Id"}), ("missing_count", {"column": "Qty"}),
                                      ("date_span_days", {"column": "Start"}),
                                      ("avg_days_between", {"column": "Start", "criteria_column": "End"})])
def test_formulas_pass_policy(kind, kw):
    f, _fmt = build_formula(CalcSpec(label="x", kind=kind, **kw), INFO, False)
    formula_policy.validate_formula("=" + f, {"T"})


@pytest.mark.parametrize("kind,kw", [("date_span_days", {"column": "Qty"}), ("date_span_days", {}),
                                      ("avg_days_between", {"column": "Start"}),
                                      ("avg_days_between", {"column": "Start", "criteria_column": "Id"}),
                                      ("duplicate_count", {"column": "nope"}), ("missing_count", {"column": "Id", "group_by": "Id"})])
def test_invalid_use_is_rejected(kind, kw):
    with pytest.raises(CalcError):
        build_formula(CalcSpec(label="x", kind=kind, **kw), INFO, bool(kw.get("group_by")))


@needs_lo
def test_values_match_python():
    rows = [["a", "2026-01-01", "2026-01-11", 5], ["b", "2026-01-05", "2026-01-06", None], ["a", "2026-02-01", None, 7],
            ["c", None, "2026-03-01", 7], ["", "2026-01-20", "2026-01-30", None]]
    sh = SheetSpec(title="T", columns=[C("Id"), C("Start", "date"), C("End", "date"), C("Qty", "integer")], rows=rows,
                   calculations=[calc("dups", "duplicate_count", column="Id"), calc("dups qty", "duplicate_count", column="Qty"),
                                 calc("missing qty", "missing_count", column="Qty"), calc("missing end", "missing_count", column="End"),
                                 calc("span", "date_span_days", column="Start"),
                                 calc("avg days", "avg_days_between", column="Start", criteria_column="End")])
    ws = recalc(build_workbook(validate_spec(wbspec(sh), S, 100), S).data)["Summary"]
    flat = {r[0]: r[1] for r in ws.iter_rows(values_only=True) if r[0]}
    assert flat["dups"] == 1           # 'a' twice; the empty Id is ignored
    assert flat["dups qty"] == 1       # 7 twice
    assert flat["missing qty"] == 2 and flat["missing end"] == 1
    assert flat["span"] == 31          # 2026-01-01 .. 2026-02-01
    assert flat["avg days"] == pytest.approx((10 + 1 + 10) / 3)  # only rows with both dates


@needs_lo
def test_blank_template_has_no_errors():
    sh = SheetSpec(title="T", columns=[C("Id"), C("Start", "date"), C("End", "date")], row_count=20,
                   calculations=[calc("d", "duplicate_count", column="Id"), calc("m", "missing_count", column="Id"),
                                 calc("s", "date_span_days", column="Start"), calc("a", "avg_days_between", column="Start", criteria_column="End")])
    ws = recalc(build_workbook(validate_spec(wbspec(sh), S, 100), S).data)["Summary"]
    flat = {r[0]: r[1] for r in ws.iter_rows(values_only=True) if r[0]}
    assert flat["d"] == 0 and flat["m"] == 20 and flat["s"] in (None, "") and flat["a"] in (None, "")
    assert not [v for r in ws.iter_rows(values_only=True) for v in r if isinstance(v, str) and v.startswith(("#", "Err"))]
