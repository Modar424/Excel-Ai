"""Workbook engine (openpyxl). One code path for normal and write-only mode: rows are appended as plain values
or WriteOnlyCell objects carrying a few shared, pre-built style arrays (no per-cell style objects).
Formulas come only from calculation_service and are re-checked by formula_policy. Text never becomes a formula."""
import math
import re
import warnings as pywarnings
from copy import copy
from dataclasses import dataclass, field
from datetime import date, timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.filters import AutoFilter
from openpyxl.worksheet.table import Table, TableColumn, TableStyleInfo

from app.core.config import Settings
from app.schemas.spreadsheet import GenRule, WorkbookSpec
from app.services.calculation_service import (
    FMT,
    NUM_TYPES,
    Col,
    SheetInfo,
    plan_summary,
)
from app.services.formula_policy import FormulaError, validate_formula
from app.services.spreadsheet_service import sheet_name

_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")  # not allowed in XML; openpyxl raises on them


def clean(v):
    return _ILLEGAL.sub("", v) if isinstance(v, str) else v


_DANGER = ("=", "+", "-", "@", "\t", "\r")
_MAX_TEXT = 32_000
_MAX_NUM = 1e300  # Excel cannot store magnitudes near float max
PREVIEW_ROWS = 8
_WIDTH = {"text": 24, "date": 14, "currency": 16, "decimal": 14, "integer": 12, "percent": 12, "boolean": 12}
LABELS = {
    "en": {"summary": "Summary", "notes": "Notes", "value": "Value",
           "synthetic": "Sample/synthetic data: not real records."},
    "ar": {"summary": "الملخص", "notes": "ملاحظات", "value": "القيمة",
           "synthetic": "بيانات تجريبية/اصطناعية وليست سجلات حقيقية."},
}


class GenError(ValueError):
    pass


@dataclass
class BuildResult:
    data: bytes
    rows: int
    warnings: list[str] = field(default_factory=list)
    write_only: bool = False
    styles: int = 0
    preview: list[dict] = field(default_factory=list)


# ---- value handling ---------------------------------------------------------------------------------
def coerce(v, t: str):
    r = _coerce(v, t)
    return clean(r)[:_MAX_TEXT] if isinstance(r, str) else r


def _coerce(v, t: str):
    if v is None or v == "":
        return None
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) >= _MAX_NUM:
        return str(v)  # beyond Excel's range (any column type): keep as text
    if t in NUM_TYPES:
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, (int, float)):
            return v if abs(v) < _MAX_NUM else str(v)  # beyond Excel's range: keep as text
        if isinstance(v, str):
            s = v.strip().replace(",", "")
            pct = s.endswith("%")
            try:
                f = float(s.rstrip("%"))
            except ValueError:
                return v  # stays text; SUM etc. ignore it
            if not math.isfinite(f) or abs(f) >= _MAX_NUM:
                return v
            if pct:
                f /= 100
            return int(f) if (t == "integer" and f.is_integer()) else f
    elif t == "date" and isinstance(v, str):
        try:
            return date.fromisoformat(v.strip()[:10])
        except ValueError:
            return v
    elif t == "boolean" and isinstance(v, str) and v.strip().lower() in ("true", "false"):
        return v.strip().lower() == "true"
    return clean(v)[:_MAX_TEXT] if isinstance(v, str) else v


def gen_values(rule: GenRule, n: int, ctype: str, today: date) -> list:
    k = rule.kind
    if k == "sequence":
        try:
            start = float(rule.start) if rule.start not in (None, "") else 1.0
        except ValueError:
            raise GenError("invalid sequence start") from None
        step = 1.0 if rule.step is None else float(rule.step)
        if abs(start) + n * abs(step) > 1e14:
            raise GenError("sequence too large")
        if start.is_integer() and step.is_integer():
            s0, st = int(start), int(step)
            return [s0 + i * st for i in range(n)]
        return [round(start + i * step, 10) for i in range(n)]
    if k == "constant":
        return [coerce(rule.start, ctype)] * n
    if k == "date_sequence":
        try:
            d0 = date.fromisoformat(rule.start.strip()[:10]) if rule.start else today
            step = int(rule.step or 1)
            if d0.year < 1900:
                raise GenError("date before 1900")
            return [d0 + timedelta(days=i * step) for i in range(n)]
        except (ValueError, OverflowError):
            raise GenError("invalid date sequence") from None
    if k == "cycle":
        vals = [coerce(v, ctype) for v in rule.values]
        if not vals:
            raise GenError("cycle needs values")
        return [vals[i % len(vals)] for i in range(n)]
    raise GenError("unsupported rule")


# ---- styles -----------------------------------------------------------------------------------------
class Styler:
    def __init__(self, ws):
        def mk(**kw):
            c = WriteOnlyCell(ws)
            for k, v in kw.items():
                setattr(c, k, v)
            return copy(c._style)

        thin = Side(style="thin", color="D0D7E8")
        b = Border(left=thin, right=thin, top=thin, bottom=thin)
        fill = lambda rgb: PatternFill("solid", fgColor=rgb)  # noqa: E731
        self.head = mk(font=Font(bold=True, color="FFFFFF"), fill=fill("315BE8"), border=b,
                       alignment=Alignment(horizontal="center", vertical="center", wrap_text=True))
        self.by_type = {t: mk(number_format=f) for t, f in FMT.items()}
        self.title = mk(font=Font(bold=True, size=14, color="10243E"))
        self.section = mk(font=Font(bold=True, color="FFFFFF"), fill=fill("10243E"))
        self.sub = mk(font=Font(bold=True), fill=fill("E8EEFF"), border=b)
        self.label = mk(border=b)
        self.input = mk(fill=fill("FFF8DC"), border=b)
        self.note = mk(font=Font(italic=True, color="71809C"), alignment=Alignment(wrap_text=True, vertical="top"))
        self.val = {f: mk(border=b, number_format=f) for f in {*FMT.values(), "0.0%"}}


def mkcell(ws, value, style=None, text=False):
    value = clean(value)
    c = WriteOnlyCell(ws, value=value)
    if text and isinstance(value, str):
        c.data_type = "s"  # force literal text (a leading '=' must never become a formula)
    if style is not None:
        c._style = copy(style)
    return c


# ---- build ------------------------------------------------------------------------------------------
def build_workbook(spec: WorkbookSpec, s: Settings | None = None, today: date | None = None) -> BuildResult:
    s = s or Settings(_env_file=None)
    today = today or date.today()
    warnings: list[str] = []
    total_rows = sum(len(sh.rows) + sh.row_count for sh in spec.sheets)
    cells = sum((len(sh.rows) + sh.row_count) * len(sh.columns) for sh in spec.sheets)
    write_only = cells > s.writeonly_cells_threshold
    wb = Workbook(write_only=write_only)
    if not write_only:
        wb.remove(wb.active)
    wb.properties.title, wb.properties.creator = spec.title[:200], "SheetCraft AI"
    wb.calculation.fullCalcOnLoad = True
    labels = LABELS["ar" if spec.rtl else "en"]
    styler: Styler | None = None
    infos: list[SheetInfo] = []
    previews: list[dict] = []

    for si, sh in enumerate(spec.sheets):
        ws = wb.create_sheet(sh.title)
        styler = styler or Styler(ws)
        ws.sheet_view.rightToLeft = spec.rtl
        ncols, n_gen = len(sh.columns), sh.row_count
        total = len(sh.rows) + n_gen
        last_row = max(2, total + 1)
        cols = [Col(c.name, c.type, get_column_letter(j)) for j, c in enumerate(sh.columns, 1)]
        infos.append(SheetInfo(sh.title, cols, last_row))
        for c in cols:
            ws.column_dimensions[c.letter].width = min(40, max(_WIDTH.get(c.type, 14), len(c.name) + 4))
        ws.freeze_panes = "A2"
        stl = [styler.by_type.get(c.type) for c in cols]

        def cellify(v, j, ws=ws, stl=stl):
            if v is None:
                return None
            if isinstance(v, str):
                return mkcell(ws, v, stl[j], True) if v[:1] in _DANGER else v
            return mkcell(ws, v, stl[j]) if stl[j] is not None else v

        ws.append([mkcell(ws, c.name, styler.head, True) for c in cols])
        for r in sh.rows:
            ws.append([cellify(coerce(v, cols[j].type), j) for j, v in enumerate(r)])
        gen: list[list | None] = [None] * ncols
        for rule in sh.generation_rules:
            col = next((j for j, c in enumerate(cols) if c.name.lower() == rule.column.strip().lower()), None)
            if col is None:
                warnings.append(f"Generation rule skipped ({sh.title}): unknown column '{rule.column}'")
                continue
            try:
                gen[col] = gen_values(rule, n_gen, cols[col].type, today)
            except GenError as e:
                warnings.append(f"Generation rule skipped ({sh.title} / {rule.column}): {e}")
        active = [(j, g) for j, g in enumerate(gen) if g is not None]
        sample = [[coerce(v, cols[j].type) for j, v in enumerate(r)] for r in sh.rows[:PREVIEW_ROWS]]
        for i in range(min(n_gen, max(0, PREVIEW_ROWS - len(sample)))):
            sample.append([gen[j][i] if gen[j] is not None else None for j in range(ncols)])
        previews.append({"name": sh.title, "columns": [c.name for c in cols], "rows": sample, "total_rows": total,
                         "total_cols": ncols, "synthetic": sh.synthetic, "calcs": [c.label for c in sh.calculations]})
        for i in range(n_gen):
            row: list = [None] * ncols
            for j, g in active:
                row[j] = cellify(g[i], j)
            ws.append(row)
        ref = f"A1:{get_column_letter(ncols)}{last_row}"
        t = Table(displayName=f"Table{si + 1}", ref=ref)
        t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        t.tableColumns = [TableColumn(id=j, name=c.name) for j, c in enumerate(cols, 1)]
        t.autoFilter = AutoFilter(ref=ref)
        with pywarnings.catch_warnings():
            pywarnings.simplefilter("ignore", UserWarning)  # write-only notice; columns are set manually above
            ws.add_table(t)

    # ---- summary sheet (aggregate formulas over the prepared ranges) ----
    has_content = any(sh.calculations or sh.notes or sh.synthetic for sh in spec.sheets) or warnings
    if has_content and styler:
        used = {sh.title.lower() for sh in spec.sheets}
        plan = plan_summary([(infos[i], sh.calculations, sh.notes, sh.synthetic) for i, sh in enumerate(spec.sheets)],
                            spec.title, labels, warnings)
        kept = {r.label for r in plan.rows if r.style in ("calc", "sub")}
        for pv, sh in zip(previews, spec.sheets, strict=True):
            pv["calcs"] = [c.label for c in sh.calculations if c.label in kept]
        warnings = plan.warnings  # includes skipped-calculation warnings; later policy warnings append here
        ws = wb.create_sheet(sheet_name(labels["summary"], used, len(spec.sheets)))
        ws.sheet_view.rightToLeft = spec.rtl
        ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 38, 22
        names, r = {sh.title for sh in spec.sheets}, 1
        for row in plan.rows:
            if row.style == "blank":
                ws.append([])
            elif row.style == "title":
                ws.append([mkcell(ws, row.label, styler.title, True)])
            elif row.style == "section":
                ws.append([mkcell(ws, row.label, styler.section, True), mkcell(ws, None, styler.section)])
            elif row.style == "sub":
                ws.append([mkcell(ws, row.label, styler.sub, True), mkcell(ws, labels["value"], styler.sub, True)])
            elif row.style == "note":
                ws.append([mkcell(ws, row.label, styler.note, True)])
            else:  # calc | group
                f = row.formula.replace("{R}", str(r))
                try:
                    validate_formula(f, names)
                except FormulaError as e:
                    warnings.append(f"Formula rejected by policy ({row.label}): {e}")
                    r += 1
                    ws.append([mkcell(ws, row.label, styler.label, True)])
                    continue
                lab = styler.input if row.style == "group" else styler.label
                ws.append([mkcell(ws, row.label or None, lab, True), mkcell(ws, f, styler.val[row.fmt or "#,##0"])])
            r += 1

    buf = BytesIO()
    wb.save(buf)
    return BuildResult(buf.getvalue(), total_rows, warnings, write_only, len(wb._cell_styles), previews)
