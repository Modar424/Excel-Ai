import time
from datetime import date, timedelta
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.spreadsheet import (
    CalcSpec,
    ColumnSpec,
    GenRule,
    SheetSpec,
    WorkbookSpec,
)
from app.services import calculation_service
from app.services.excel_service import build_workbook
from app.services.spreadsheet_service import validate_spec
from tests.conftest import MockProvider, make_client
from tests.lo import SOFFICE, recalc

needs_lo = pytest.mark.skipif(not SOFFICE, reason="LibreOffice not installed")
S = Settings(_env_file=None)


def C(name, t="text"):
    return ColumnSpec(name=name, type=t)


def calc(label, kind, **kw):
    return CalcSpec(label=label, kind=kind, **kw)


def wbspec(*sheets, rtl=False, title="Test"):
    return WorkbookSpec(title=title, sheets=list(sheets), rtl=rtl)


def load(r):
    return load_workbook(BytesIO(r.data))


def summary_map(ws):
    """label -> computed value for rows with two cells."""
    return {row[0]: row[1] for row in ws.iter_rows(values_only=True) if row[0] is not None}


# ---------------------------------------------------------------------------------------------- large data
def test_3000_rows_blank_template_with_rules():
    sh = SheetSpec(title="Inventory", columns=[C("ID", "integer"), C("Date", "date"), C("Category"), C("Qty", "integer"), C("Price", "currency")],
                   row_count=3000, generation_rules=[
                       GenRule(column="ID", kind="sequence", start="1", step=1),
                       GenRule(column="Date", kind="date_sequence", start="2026-01-01", step=1),
                       GenRule(column="Category", kind="cycle", values=["A", "B", "C"])],
                   calculations=[calc("Rows", "counta", column="ID"), calc("Value", "sum", column="Qty")])
    spec = validate_spec(wbspec(sh), S, 3000)
    t = time.perf_counter()
    r = build_workbook(spec, S)
    dt = time.perf_counter() - t
    assert r.rows == 3000 and not r.warnings and dt < 10
    wb = load(r)
    ws = wb["Inventory"]
    assert ws.max_row == 3001 and ws.freeze_panes == "A2"
    assert ws["A2"].value == 1 and ws["A3001"].value == 3000 and ws["C4"].value == "C" and ws["C5"].value == "A"
    assert ws["B2"].value.date() == date(2026, 1, 1) and ws["B3001"].value.date() == date(2026, 1, 1) + timedelta(days=2999)
    assert ws["B3001"].number_format == "yyyy-mm-dd" and ws["D2"].value is None
    assert ws.tables["Table1"].ref == "A1:E3001"
    assert r.styles < 30 and len(r.data) < 400_000


def test_40_columns_x_5000_rows_uses_write_only():
    cols = [C(f"Col {i}", "integer" if i % 2 else "text") for i in range(40)]
    sh = SheetSpec(title="Wide", columns=cols, row_count=5000, generation_rules=[
        GenRule(column="Col 1", kind="sequence", start="1", step=1), GenRule(column="Col 39", kind="sequence", start="10", step=2)])
    spec = validate_spec(wbspec(sh), S, 5000)
    t = time.perf_counter()
    r = build_workbook(spec, S)
    assert r.write_only and r.rows == 5000 and time.perf_counter() - t < 30
    ws = load_workbook(BytesIO(r.data), read_only=True)["Wide"]
    rows = list(ws.iter_rows(values_only=True))
    assert len(rows) == 5001 and len(rows[0]) == 40 and rows[0][39] == "Col 39"
    assert rows[1][1] == 1 and rows[5000][39] == 10 + 2 * 4999


def test_limits_reject_oversize_workbook():
    sh = SheetSpec(title="X", columns=[C(f"c{i}") for i in range(41)], row_count=5000)
    with pytest.raises(AppError) as e:
        validate_spec(wbspec(sh), Settings(_env_file=None, max_cols=60), 5000)
    assert e.value.code == "invalid_spec" and "too large" in e.value.message


def test_write_only_and_normal_mode_produce_same_cells():
    sh = SheetSpec(title="D", columns=[C("n", "integer"), C("t"), C("d", "date"), C("p", "percent")],
                   rows=[[1, "=evil", "2026-02-03", "15%"], ["x", "ok", "bad date", 0.5]], row_count=5,
                   generation_rules=[GenRule(column="n", kind="sequence", start="100", step=5)])
    spec = validate_spec(wbspec(sh), S, 100)
    a = load(build_workbook(spec, S))["D"]
    b = load(build_workbook(validate_spec(wbspec(sh.model_copy(deep=True)), S, 100), Settings(_env_file=None, writeonly_cells_threshold=1)))["D"]
    assert build_workbook(spec, Settings(_env_file=None, writeonly_cells_threshold=1)).write_only
    va = [[c.value for c in r] for r in a.iter_rows()]
    vb = [[c.value for c in r] for r in b.iter_rows()]
    assert va == vb and va[1][3] == 0.15 and va[1][2].date() == date(2026, 2, 3) and va[2][2] == "bad date"


# ---------------------------------------------------------------------------------------------- safety
@pytest.mark.parametrize("threshold", [10**9, 1])
def test_formula_like_text_never_becomes_formula(threshold):
    evil = ["=1+1", "+cmd|' /C calc'!A0", "@SUM(1)", "-2+3", "=HYPERLINK(\"http://x\",\"y\")", "\t=1"]
    sh = SheetSpec(title="Safe", columns=[C("=H1"), C("Name")], rows=[[e, e] for e in evil],
                   calculations=[calc("=1+1", "counta", column="Name")], notes=["=2+2"])
    r = build_workbook(validate_spec(wbspec(sh), S, 100), Settings(_env_file=None, writeonly_cells_threshold=threshold))
    wb = load(r)
    ws = wb["Safe"]
    assert ws["A1"].data_type == "s" and ws["A1"].value == "=H1"
    for i, e in enumerate(evil, 2):
        for col in "AB":
            assert ws[f"{col}{i}"].data_type == "s" and ws[f"{col}{i}"].value == e
    sm = wb["Summary"]
    assert sm["A3"].data_type == "s" and sm["B4"].data_type == "f"  # label text, calc formula
    assert not any(c.data_type == "f" for row in sm.iter_rows() for c in row[:1])


def test_policy_rejection_skips_formula_and_warns(monkeypatch):
    monkeypatch.setattr(calculation_service, "build_formula", lambda *a, **k: ('HYPERLINK("http://x","y")', "#,##0"))
    sh = SheetSpec(title="D", columns=[C("a")], rows=[["1"]], calculations=[calc("Bad", "counta", column="a")])
    r = build_workbook(validate_spec(wbspec(sh), S, 10), S)
    assert any("rejected by policy" in w for w in r.warnings)
    ws = load(r)["Summary"]
    assert not any(c.data_type == "f" for row in ws.iter_rows() for c in row)


def test_bad_rules_and_calcs_become_warnings_not_failures():
    sh = SheetSpec(title="D", columns=[C("a", "integer"), C("b")], row_count=3, generation_rules=[
        GenRule(column="zzz", kind="sequence"), GenRule(column="a", kind="sequence", start="abc"),
        GenRule(column="b", kind="cycle", values=[]), GenRule(column="b", kind="date_sequence", start="not-a-date")],
        calculations=[calc("x", "sum", column="nope"), calc("y", "sumif", column="a"), calc("z", "unique_count", column="a", group_by="b", group_values=["q"]),
                      calc("ok", "counta", column="a")])
    r = build_workbook(validate_spec(wbspec(sh), S, 10), S)
    assert len(r.warnings) == 7
    ws = load(r)["Summary"]
    texts = [row[0].value for row in ws.iter_rows() if row[0].value]
    assert "ok" in texts and any("Calculation skipped" in t for t in texts)


def test_arabic_rtl_workbook():
    sh = SheetSpec(title="الموظفين", columns=[C("الاسم"), C("الراتب", "currency")], rows=[["أحمد", 100]],
                   calculations=[calc("إجمالي الرواتب", "sum", column="الراتب")])
    wb = load(build_workbook(validate_spec(wbspec(sh, rtl=True, title="جدول"), S, 10), S))
    assert wb.sheetnames == ["الموظفين", "الملخص"] and wb["الموظفين"].sheet_view.rightToLeft
    assert wb["الملخص"]["A4"].value == "إجمالي الرواتب"


# ---------------------------------------------------------------------------------------------- real recalculation (LibreOffice)
@needs_lo
def test_employee_example_values_match_python():
    data = [("Ann", "Sales", 5000, "Active"), ("Bob", "Sales", 4000, "Inactive"), ("Cy", "IT", 6000, "Active"),
            ("Di", "IT", "n/a", "Active"), ("Eve", "HR", 7000, "Active"), ("Fay", "HR", None, "Inactive")]
    sh = SheetSpec(title="Employees", columns=[C("Name"), C("Department"), C("Salary", "currency"), C("Status")], rows=[list(r) for r in data],
                   calculations=[calc("Total employees", "counta", column="Name"), calc("Total salary", "sum", column="Salary"),
                                 calc("Average salary", "average", column="Salary"), calc("Active employees", "countif", column="Status", criteria="Active"),
                                 calc("Max salary", "max", column="Salary"), calc("Min salary", "min", column="Salary"),
                                 calc("Per department", "counta", column="Name", group_by="Department", group_values=["Sales", "IT", "HR"]),
                                 calc("Salary per department", "sum", column="Salary", group_by="Department", group_values=["Sales", "IT", "HR"]),
                                 calc("Avg per dept", "average", column="Salary", group_by="Department", group_values=["Sales", "IT", "HR"]),
                                 calc("Active per dept", "countifs", column="Name", group_by="Department", group_values=["Sales", "IT"], criteria_column="Status", criteria="Active"),
                                 calc("Share active", "ratio", column="Status", criteria="Active"),
                                 calc("Distinct depts", "unique_count", column="Department")])
    ws = recalc(build_workbook(validate_spec(wbspec(sh), S, 100), S).data)["Summary"]
    rows = [r for r in ws.iter_rows(values_only=True)]
    flat = {r[0]: r[1] for r in rows if r[0] is not None}
    nums = [r[2] for r in data if isinstance(r[2], (int, float))]
    assert flat["Total employees"] == 6 and flat["Total salary"] == sum(nums) == 22000
    assert flat["Average salary"] == pytest.approx(sum(nums) / len(nums)) and flat["Max salary"] == 7000 and flat["Min salary"] == 4000
    assert flat["Active employees"] == 4 and flat["Share active"] == pytest.approx(4 / 6) and flat["Distinct depts"] == 3
    seq = [r for r in rows if r[0] in ("Sales", "IT", "HR")]  # 4 blocks of group rows in order
    exp_count = [2, 2, 2]
    exp_sum = [9000, 6000, 7000]
    exp_avg = [4500, 6000, 7000]
    exp_active = [1, 2]
    got = [r[1] for r in seq]
    assert got == exp_count + exp_sum + exp_avg + exp_active


@needs_lo
def test_grades_criteria_ratio_minmax_by_group():
    data = [("A", "Math", 90), ("B", "Math", 40), ("C", "Math", 55), ("D", "Sci", 30), ("E", "Sci", 80), ("F", "Sci", "absent")]
    sh = SheetSpec(title="Grades", columns=[C("Student"), C("Subject"), C("Score", "integer")], rows=[list(r) for r in data],
                   calculations=[calc("Pass rate", "ratio", column="Score", criteria=">=50"),
                                 calc("Passed", "countif", column="Score", criteria=">=50"),
                                 calc("Failed", "countif", column="Score", criteria="<50"),
                                 calc("Top per subject", "max", column="Score", group_by="Subject", group_values=["Math", "Sci"]),
                                 calc("Low per subject", "min", column="Score", group_by="Subject", group_values=["Math", "Sci"]),
                                 calc("Pass per subject", "ratio", column="Score", group_by="Subject", group_values=["Math", "Sci"], criteria=">=50"),
                                 calc("Avg passing", "averageif", column="Score", criteria=">=50"),
                                 calc("Sum passing Math", "sumif", column="Score", criteria="Math", criteria_column="Subject")])
    ws = recalc(build_workbook(validate_spec(wbspec(sh), S, 100), S).data)["Summary"]
    rows = list(ws.iter_rows(values_only=True))
    flat = {r[0]: r[1] for r in rows if r[0] is not None}
    assert flat["Passed"] == 3 and flat["Failed"] == 2 and flat["Pass rate"] == pytest.approx(3 / 5)
    assert flat["Avg passing"] == pytest.approx((90 + 55 + 80) / 3) and flat["Sum passing Math"] == 185
    grp = [r[1] for r in rows if r[0] in ("Math", "Sci")]
    assert grp[:2] == [90, 80] and grp[2:4] == [40, 30] and grp[4] == pytest.approx(2 / 3) and grp[5] == pytest.approx(1 / 3)  # Sci: 1 of 3 rows


@needs_lo
def test_blank_templates_produce_no_errors_and_div_by_zero_is_blank():
    sh = SheetSpec(title="T", columns=[C("Name"), C("Dept"), C("Salary", "currency"), C("Status")], row_count=100,
                   calculations=[calc("n", "counta", column="Name"), calc("sum", "sum", column="Salary"), calc("avg", "average", column="Salary"),
                                 calc("min", "min", column="Salary"), calc("max", "max", column="Salary"), calc("active", "countif", column="Status", criteria="Active"),
                                 calc("rate", "ratio", column="Status", criteria="Active"), calc("avgif", "averageif", column="Salary", criteria="x", criteria_column="Dept"),
                                 calc("uniq", "unique_count", column="Dept"),
                                 calc("by dept", "counta", column="Name", group_by="Dept"), calc("avg dept", "average", column="Salary", group_by="Dept")])
    ws = recalc(build_workbook(validate_spec(wbspec(sh), S, 100), S).data)["Summary"]
    vals = [c for row in ws.iter_rows(values_only=True) for c in row[1:] if c is not None and c != "Value"]
    assert not [v for v in vals if isinstance(v, str) and (v.startswith("#") or v.startswith("Err"))]
    flat = {r[0]: r[1] for r in ws.iter_rows(values_only=True) if r[0]}
    assert flat["n"] == 0 and flat["sum"] == 0 and flat["active"] == 0 and flat["uniq"] == 0
    assert flat["avg"] in (None, "") and flat["rate"] in (None, "") and flat["min"] in (None, "")


@needs_lo
def test_user_group_labels_drive_formulas_in_blank_template():
    """Blank group rows reference column A: typing a department name makes the formula work."""
    sh = SheetSpec(title="T", columns=[C("Name"), C("Dept")], rows=[["a", "X"], ["b", "X"], ["c", "Y"]],
                   calculations=[calc("by", "counta", column="Name", group_by="Dept")])
    wb = load(build_workbook(validate_spec(wbspec(sh), S, 100), S))
    ws = wb["Summary"]
    assert ws["A5"].value is None and ws["B5"].value.startswith("=IF($A5=")
    ws["A5"].value, ws["A6"].value = "X", "Y"
    buf = BytesIO()
    wb.save(buf)
    out = recalc(buf.getvalue())["Summary"]
    assert out["B5"].value == 2 and out["B6"].value == 1 and out["B7"].value in (None, "")


@needs_lo
def test_criteria_injection_wildcards_and_odd_sheet_names():
    sh = SheetSpec(title="Bob's data", columns=[C("Name"), C("N", "integer")],
                   rows=[["a*", 1], ["abc", 2], ['x"); =HYPERLINK("http://e","c")', 3], ["=1+1", 4]],
                   calculations=[calc("star", "countif", column="Name", criteria="a*"), calc("quote", "countif", column="Name", criteria='x"); =HYPERLINK("http://e","c")'),
                                 calc("formula text", "countif", column="Name", criteria="=1+1"), calc("sum", "sum", column="N")])
    r = build_workbook(validate_spec(wbspec(sh), S, 100), S)
    assert not r.warnings
    flat = summary_map(recalc(r.data)["Summary"])
    assert flat["star"] == 1 and flat["quote"] == 1 and flat["sum"] == 10 and flat["formula text"] in (0, 1)


@needs_lo
def test_3000_rows_summary_recalculates_correctly():
    sh = SheetSpec(title="Data", columns=[C("ID", "integer"), C("Cat"), C("Amount", "decimal")], row_count=3000, generation_rules=[
        GenRule(column="ID", kind="sequence", start="1", step=1), GenRule(column="Cat", kind="cycle", values=["A", "B", "C"]),
        GenRule(column="Amount", kind="sequence", start="0.5", step=0.5)],
        calculations=[calc("rows", "count", column="ID"), calc("total", "sum", column="Amount"), calc("A rows", "countif", column="Cat", criteria="A"),
                      calc("distinct ids", "unique_count", column="ID"), calc("per cat", "sum", column="Amount", group_by="Cat", group_values=["A", "B", "C"])])
    t = time.perf_counter()
    r = build_workbook(validate_spec(wbspec(sh), S, 3000), S)
    gen_s = time.perf_counter() - t
    ws = recalc(r.data)["Summary"]
    flat = summary_map(ws)
    amounts = [0.5 + 0.5 * i for i in range(3000)]
    assert gen_s < 10 and flat["rows"] == 3000 and flat["total"] == pytest.approx(sum(amounts)) and flat["A rows"] == 1000 and flat["distinct ids"] == 3000
    per = [row[1] for row in ws.iter_rows(values_only=True) if row[0] in ("A", "B", "C")]
    assert per == [pytest.approx(sum(amounts[i::3])) for i in range(3)]


# ---------------------------------------------------------------------------------------------- API
def test_api_generates_3000_row_workbook_end_to_end():
    sh = SheetSpec(title="Attendance", columns=[C("No", "integer"), C("Name"), C("Date", "date"), C("Status")], row_count=3000,
                   generation_rules=[GenRule(column="No", kind="sequence", start="1", step=1)],
                   calculations=[calc("Present", "countif", column="Status", criteria="Present")])
    c = make_client(MockProvider(wbspec(sh, title="Attendance")))
    r = c.post("/api/v1/spreadsheets/generate", json={"prompt": "attendance template 3000 rows", "language": "en", "max_rows": 3000})
    assert r.status_code == 200 and r.headers["x-rows-generated"] == "3000" and "x-warnings" not in r.headers
    wb = load_workbook(BytesIO(r.content))
    assert wb["Attendance"].max_row == 3001 and wb.sheetnames == ["Attendance", "Summary"]


def test_api_rejects_rows_over_cap():
    sh = SheetSpec(title="X", columns=[C("a")], row_count=10**6)
    c = make_client(MockProvider(wbspec(sh)))
    r = c.post("/api/v1/spreadsheets/generate", json={"prompt": "hello sheet", "max_rows": 500})
    assert r.status_code == 200 and r.headers["x-rows-generated"] == "500"  # row_count clamped to the request cap
