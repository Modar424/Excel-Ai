"""Deterministic fake AI for local end-to-end testing and UI demos (AI_PROVIDER=mock). NOT for public deployment.
Test triggers inside the prompt: __quota__ (429), __invalid__ (422), __down__ (503), __slow__ (3 s delay), __wide__ (40 fully populated columns, load testing)."""
import asyncio

from app.core.errors import AppError
from app.schemas.spreadsheet import (
    CalcSpec,
    ColumnSpec,
    GenRule,
    SheetSpec,
    WorkbookSpec,
)

_T = {
    "ar": dict(title="جدول الموظفين", sheet="الموظفين", cols=["الرقم", "الاسم", "القسم", "الراتب", "الحالة الوظيفية"], active="نشط",
               calcs=["إجمالي الموظفين", "إجمالي الرواتب", "متوسط الراتب", "عدد الموظفين النشطين", "عدد الموظفين في كل قسم"],
               inv_title="جدول المخزون", inv_sheet="المخزون", inv_cols=["الرقم", "المنتج", "الكمية", "سعر الوحدة"],
               inv_calcs=["عدد الأصناف", "إجمالي الكمية"]),
    "en": dict(title="Employees", sheet="Employees", cols=["No", "Name", "Department", "Salary", "Status"], active="Active",
               calcs=["Total employees", "Total salary", "Average salary", "Active employees", "Employees per department"],
               inv_title="Inventory", inv_sheet="Inventory", inv_cols=["No", "Product", "Quantity", "Unit price"],
               inv_calcs=["Item count", "Total quantity"]),
}


class MockProvider:
    async def generate_spec(self, prompt: str, language: str, max_rows: int) -> WorkbookSpec:
        p = prompt.lower()
        if "__quota__" in p:
            raise AppError(429, "ai_quota", "The AI quota is exhausted.", headers={"Retry-After": "42"}, extra={"retry_after": 42})
        if "__invalid__" in p:
            raise AppError(422, "invalid_spec", "The AI returned an invalid specification.")
        if "__down__" in p:
            raise AppError(503, "ai_unavailable", "The AI service is currently unavailable.")
        if "__slow__" in p:
            await asyncio.sleep(3)
        if "__wide__" in p:
            kinds = ["integer", "text", "decimal", "date", "currency"]
            cols = [ColumnSpec(name=f"Col {i + 1}", type=kinds[i % 5]) for i in range(40)]
            rules = [GenRule(column=c.name, kind={"integer": "sequence", "decimal": "sequence", "currency": "sequence", "date": "date_sequence",
                                                  "text": "cycle"}[c.type], start="2026-01-01" if c.type == "date" else "1", step=1, values=["A", "B", "C"]) for c in cols]
            return WorkbookSpec(title="Wide", sheets=[SheetSpec(title="Wide", columns=cols, row_count=max_rows, generation_rules=rules,
                                calculations=[CalcSpec(label="Total", kind="sum", column="Col 3")])])
        ar, t = language == "ar", _T["ar" if language == "ar" else "en"]
        rows = max(1, max_rows)
        if "مخزون" in p or "inventory" in p:
            c = t["inv_cols"]
            sh = SheetSpec(title=t["inv_sheet"], columns=[ColumnSpec(name=c[0], type="integer"), ColumnSpec(name=c[1]),
                                                           ColumnSpec(name=c[2], type="integer"), ColumnSpec(name=c[3], type="currency")],
                           row_count=rows, generation_rules=[GenRule(column=c[0], kind="sequence", start="1", step=1)],
                           calculations=[CalcSpec(label=t["inv_calcs"][0], kind="counta", column=c[1]),
                                         CalcSpec(label=t["inv_calcs"][1], kind="sum", column=c[2])])
            return WorkbookSpec(title=t["inv_title"], sheets=[sh], rtl=ar)
        c = t["cols"]
        sh = SheetSpec(title=t["sheet"], columns=[ColumnSpec(name=c[0], type="integer"), ColumnSpec(name=c[1]), ColumnSpec(name=c[2]),
                                                   ColumnSpec(name=c[3], type="currency"), ColumnSpec(name=c[4])],
                       row_count=rows, generation_rules=[GenRule(column=c[0], kind="sequence", start="1", step=1)],
                       calculations=[CalcSpec(label=t["calcs"][0], kind="counta", column=c[1]),
                                     CalcSpec(label=t["calcs"][1], kind="sum", column=c[3]),
                                     CalcSpec(label=t["calcs"][2], kind="average", column=c[3]),
                                     CalcSpec(label=t["calcs"][3], kind="countif", column=c[4], criteria=t["active"]),
                                     CalcSpec(label=t["calcs"][4], kind="counta", column=c[1], group_by=c[2])])
        return WorkbookSpec(title=t["title"], sheets=[sh], rtl=ar)
