"""Compact preview sample for the UI, sent in the `X-Preview` header as base64(JSON, UTF-8).
Why a header: the UI needs a few real rows without a second AI call (free quota) and without server-side state.
Shrinks progressively to stay under `max_bytes`; returns None if nothing fits (UI then shows no preview)."""
import base64
import json
from datetime import date, datetime

# (sheets, columns, rows, chars per cell)
_STEPS = [(3, 12, 8, 30), (3, 10, 5, 24), (2, 8, 3, 20), (1, 6, 2, 16)]


def _cell(v, n: int):
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.isoformat()[:10]
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, int):
        return v
    return str(v)[:n]


def build_preview(sheets: list[dict], steps: tuple[int, int, int, int]) -> dict:
    ns, nc, nr, nchar = steps
    out = []
    for sh in sheets[:ns]:
        out.append({"name": sh["name"][:31], "columns": [str(c)[:nchar] for c in sh["columns"][:nc]],
                    "rows": [[_cell(v, nchar) for v in r[:nc]] for r in sh["rows"][:nr]],
                    "total_rows": sh["total_rows"], "total_cols": sh["total_cols"], "synthetic": sh["synthetic"],
                    "calcs": [str(c)[:40] for c in sh["calcs"][:8]]})
    return {"v": 1, "sheets": out}


def encode_preview(sheets: list[dict], max_bytes: int = 4500) -> str | None:
    if not sheets:
        return None
    for st in _STEPS:
        raw = json.dumps(build_preview(sheets, st), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(raw) <= max_bytes:
            return base64.b64encode(raw).decode("ascii")
    return None
