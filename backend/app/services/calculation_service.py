"""Whitelisted calculation kinds -> Excel formula templates. The model chooses a `kind`; this module builds the
formula text. Ranges cover the prepared data rows (rows + row_count); formulas never use eval or user-supplied syntax."""
import re
from dataclasses import dataclass, field

from app.schemas.spreadsheet import CalcSpec

NUM_TYPES = {"integer", "decimal", "currency", "percent"}
FMT = {"integer": "#,##0", "decimal": "#,##0.00", "currency": "#,##0.00", "percent": "0.0%", "date": "yyyy-mm-dd"}
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_NUM = re.compile(r"^-?\d+(\.\d+)?$")
_CMP = re.compile(r"^(>=|<=|<>|>|<|=)\s*(.*)$", re.S)


class CalcError(ValueError):
    pass


@dataclass
class Col:
    name: str
    type: str
    letter: str


@dataclass
class SheetInfo:
    title: str
    cols: list[Col]
    last_row: int  # last row covered by formulas (>= 2)

    def find(self, name: str | None) -> Col | None:
        if not name:
            return None
        n = name.strip().lower()
        return next((c for c in self.cols if c.name.lower() == n), None)


@dataclass
class SumRow:
    style: str  # title | section | sub | calc | group | note | blank
    label: str = ""
    formula: str | None = None  # may contain {R} = own row number
    fmt: str | None = None


def qsheet(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def rng(info: SheetInfo, col: Col) -> str:
    return f"{qsheet(info.title)}!${col.letter}$2:${col.letter}${info.last_row}"


def _wild(s: str) -> str:
    return re.sub(r"([~*?])", r"~\1", s)


def crit_expr(text: str) -> str:
    """Build a safe COUNTIF-style criterion literal from user/AI text."""
    t = _CTRL.sub("", str(text)).strip()
    if not t or len(t) > 250:
        raise CalcError("invalid criteria")
    if _NUM.match(t):
        return t
    m = _CMP.match(t)
    if m:
        op, val = m.group(1), m.group(2).strip()
        if not val and op not in ("<>", "="):
            raise CalcError("invalid criteria")
        lit = op + (val if _NUM.match(val) else _wild(val))
    else:
        lit = _wild(t)
    return '"' + lit.replace('"', '""') + '"'


def _cnt(info: SheetInfo, col: Col) -> str:
    return f"{'COUNT' if col.type in NUM_TYPES else 'COUNTA'}({rng(info, col)})"


def build_formula(c: CalcSpec, info: SheetInfo, grouped: bool) -> tuple[str, str]:
    """Return (formula with optional {R}, number format). Raises CalcError if unsupported/incomplete."""
    v = info.find(c.column)
    if c.column and not v:
        raise CalcError(f"unknown column '{c.column}'")
    crit_col = info.find(c.criteria_column) if c.criteria_column else v
    if c.criteria_column and not crit_col:
        raise CalcError(f"unknown column '{c.criteria_column}'")
    k = c.kind
    first = info.cols[0]
    vfmt = FMT.get(v.type, "#,##0") if v else "#,##0"
    avg_fmt = "#,##0.00"
    needs_crit = k in ("countif", "countifs", "sumif", "averageif", "ratio")
    crit = crit_expr(c.criteria) if (needs_crit and c.criteria) else None
    if needs_crit and crit is None:
        raise CalcError("criteria required")
    if k in ("sum", "average", "min", "max", "sumif", "averageif", "unique_count",
             "duplicate_count", "missing_count", "date_span_days", "avg_days_between") and not v:
        raise CalcError("column required")
    if needs_crit and not crit_col:
        raise CalcError("criteria column required")

    if k in ("date_span_days", "avg_days_between"):
        if v.type != "date":
            raise CalcError(f"column '{v.name}' is not a date column")
        if k == "avg_days_between":
            if not c.criteria_column or not crit_col or crit_col.type != "date":
                raise CalcError("end date column (criteria_column) required and must be a date column")

    if grouped:
        g = info.find(c.group_by)
        if not g:
            raise CalcError(f"unknown group column '{c.group_by}'")
        G, gr = "$A{R}", rng(info, g)
        if k in ("count", "counta"):
            f, fmt = f"COUNTIF({gr},{G})", "#,##0"
        elif k == "sum":
            f, fmt = f"SUMIF({gr},{G},{rng(info, v)})", vfmt
        elif k == "average":
            f, fmt = f'IFERROR(AVERAGEIF({gr},{G},{rng(info, v)}),"")', avg_fmt
        elif k in ("min", "max"):
            fn = "_xlfn.MINIFS" if k == "min" else "_xlfn.MAXIFS"
            f, fmt = f'IF(COUNTIF({gr},{G})=0,"",{fn}({rng(info, v)},{gr},{G}))', vfmt
        elif k in ("countif", "countifs"):
            f, fmt = f"COUNTIFS({gr},{G},{rng(info, crit_col)},{crit})", "#,##0"
        elif k == "sumif":
            f, fmt = f"SUMIFS({rng(info, v)},{gr},{G},{rng(info, crit_col)},{crit})", vfmt
        elif k == "averageif":
            f, fmt = f'IFERROR(AVERAGEIFS({rng(info, v)},{gr},{G},{rng(info, crit_col)},{crit}),"")', avg_fmt
        elif k == "ratio":
            f, fmt = f'IF(COUNTIF({gr},{G})=0,"",COUNTIFS({gr},{G},{rng(info, crit_col)},{crit})/COUNTIF({gr},{G}))', "0.0%"
        else:
            raise CalcError(f"'{k}' is not supported per group")
        return f'IF({G}="","",{f})', fmt

    if k == "count":
        return (f"COUNT({rng(info, v)})" if v else f"COUNTA({rng(info, first)})"), "#,##0"
    if k == "counta":
        return f"COUNTA({rng(info, v or first)})", "#,##0"
    if k == "sum":
        return f"SUM({rng(info, v)})", vfmt
    if k == "average":
        return f'IF(COUNT({rng(info, v)})=0,"",AVERAGE({rng(info, v)}))', avg_fmt
    if k in ("min", "max"):
        return f'IF(COUNT({rng(info, v)})=0,"",{k.upper()}({rng(info, v)}))', vfmt
    if k in ("countif", "countifs"):
        return f"COUNTIF({rng(info, crit_col)},{crit})", "#,##0"
    if k == "sumif":
        return f"SUMIF({rng(info, crit_col)},{crit},{rng(info, v)})", vfmt
    if k == "averageif":
        return f'IFERROR(AVERAGEIF({rng(info, crit_col)},{crit},{rng(info, v)}),"")', avg_fmt
    if k == "ratio":
        den = _cnt(info, crit_col)
        return f'IF({den}=0,"",COUNTIF({rng(info, crit_col)},{crit})/{den})', "0.0%"
    if k == "unique_count":
        r = rng(info, v)
        return f'SUMPRODUCT(({r}<>"")/COUNTIF({r},{r}&""))', "#,##0"
    if k == "duplicate_count":  # non-empty cells minus distinct values
        r = rng(info, v)
        return f'ROUND(SUMPRODUCT(--({r}<>""))-SUMPRODUCT(({r}<>"")/COUNTIF({r},{r}&"")),0)', "#,##0"
    if k == "missing_count":  # empty cells among the prepared rows
        return f'SUMPRODUCT(--({rng(info, v)}=""))', "#,##0"
    if k == "date_span_days":  # latest minus earliest date
        r = rng(info, v)
        return f'IF(COUNT({r})=0,"",MAX({r})-MIN({r}))', "#,##0"
    if k == "avg_days_between":  # mean of (end - start) over rows where both dates are present
        s, e = rng(info, v), rng(info, crit_col)
        both = f'({s}<>"")*({e}<>"")'
        return f'IFERROR(SUMPRODUCT({both}*({e}-{s}))/SUMPRODUCT({both}),"")', "#,##0.00"
    raise CalcError(f"unsupported kind '{k}'")


@dataclass
class SummaryPlan:
    rows: list[SumRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


SPARE_GROUP_ROWS = 10


def plan_summary(sheets: list[tuple[SheetInfo, list[CalcSpec], list[str], bool]], title: str, labels: dict[str, str],
                 extra_warnings: list[str]) -> SummaryPlan:
    """sheets: (info, calculations, notes, synthetic). Produces sequential summary rows with {R} placeholders."""
    plan = SummaryPlan(warnings=list(extra_warnings))
    out = plan.rows
    out += [SumRow("title", title), SumRow("blank")]
    for info, calcs, _notes, _syn in sheets:
        if not calcs:
            continue
        out.append(SumRow("section", info.title))
        for c in calcs:
            grouped = bool(c.group_by)
            try:
                formula, fmt = build_formula(c, info, grouped)
            except CalcError as e:
                plan.warnings.append(f"Calculation skipped ({info.title} / {c.label}): {e}")
                continue
            if not grouped:
                out.append(SumRow("calc", c.label, "=" + formula, fmt))
                continue
            out.append(SumRow("sub", c.label, None, None))
            values = [v for v in c.group_values if v and v.strip()]
            for v in values:
                out.append(SumRow("group", v, "=" + formula, fmt))
            if not values:  # blank template: user types group names in column A
                out += [SumRow("group", "", "=" + formula, fmt) for _ in range(SPARE_GROUP_ROWS)]
        out.append(SumRow("blank"))
    notes = [n for _i, _c, ns, _s in sheets for n in ns]
    if any(s for *_x, s in sheets):
        notes.insert(0, labels["synthetic"])
    notes += plan.warnings
    if notes:
        out.append(SumRow("section", labels["notes"]))
        out += [SumRow("note", n) for n in notes]
    return plan
