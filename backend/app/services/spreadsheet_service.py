"""Validate and normalise an (untrusted) AI-produced WorkbookSpec against configured limits."""
import re

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.spreadsheet import WorkbookSpec

_BAD_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _bad(msg: str) -> AppError:
    return AppError(422, "invalid_spec", msg)


def sheet_name(raw: str, used: set[str], idx: int) -> str:
    name = _CTRL.sub(" ", _BAD_SHEET_CHARS.sub(" ", raw)).strip().strip("'")[:31].strip() or f"Sheet{idx + 1}"
    base, n = name, 2
    while name.lower() in used:
        suffix = f" {n}"
        name = base[: 31 - len(suffix)] + suffix
        n += 1
    used.add(name.lower())
    return name


def validate_spec(spec: WorkbookSpec, s: Settings, rows_cap: int) -> WorkbookSpec:
    if len(spec.sheets) > s.max_sheets:
        raise _bad(f"Too many sheets (max {s.max_sheets}).")
    used: set[str] = set()
    for i, sh in enumerate(spec.sheets):
        if len(sh.columns) > s.max_cols:
            raise _bad(f"Too many columns (max {s.max_cols}).")
        seen: set[str] = set()
        for c in sh.columns:
            c.name = _CTRL.sub(" ", c.name).strip()
            if not c.name or len(c.name) > s.max_header_len:
                raise _bad(f"Invalid header (1-{s.max_header_len} characters).")
            if c.name.lower() in seen:
                raise _bad("Duplicate column headers.")
            seen.add(c.name.lower())
        if len(sh.rows) > rows_cap:
            raise _bad(f"Too many rows (max {rows_cap}).")
        if any(len(r) != len(sh.columns) for r in sh.rows):
            raise _bad("Rows do not match the number of columns.")
        sh.row_count = max(0, min(sh.row_count, rows_cap - len(sh.rows)))
        sh.title = sheet_name(sh.title, used, i)
    cells = sum((len(sh.rows) + sh.row_count) * len(sh.columns) for sh in spec.sheets)
    if cells > s.max_cells:
        raise _bad(f"Workbook too large (max {s.max_cells:,} cells = rows x columns).")
    spec.title = _CTRL.sub(" ", spec.title).strip()[:100] or "Workbook"
    return spec
