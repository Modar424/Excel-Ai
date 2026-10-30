"""Measure workbook generation time and peak RSS, one fresh process per scenario.
Usage: python scripts/benchmark_excel.py            (all scenarios)"""
import json
import resource
import subprocess
import sys
import time

SCENARIOS = {  # name: (rows, cols, force_write_only: None=auto/True/False)
    "3,000 x 10 (auto)": (3000, 10, None),
    "3,000 x 10 write-only": (3000, 10, True),
    "5,000 x 20 (auto)": (5000, 20, None),
    "5,000 x 40 (auto)": (5000, 40, None),
    "5,000 x 40 normal mode": (5000, 40, False),
    "5,000 x 40 FULL (auto)": (5000, 40, None, True),
    "5,000 x 40 FULL normal": (5000, 40, False, True),
}


def run(rows, cols, force, full=False):
    from app.core.config import Settings
    from app.schemas.spreadsheet import CalcSpec, ColumnSpec, GenRule, SheetSpec, WorkbookSpec
    from app.services.excel_service import build_workbook
    from app.services.spreadsheet_service import validate_spec
    thr = {None: 100_000, True: 1, False: 10**12}[force]
    s = Settings(_env_file=None, writeonly_cells_threshold=thr, max_cells=10**7, max_cols=60)
    types = ["integer", "text", "decimal", "date", "currency"]
    rules_all = [GenRule(column=f"Column {i + 1}", kind={"integer": "sequence", "decimal": "sequence", "currency": "sequence",
                 "date": "date_sequence", "text": "cycle"}[types[i % 5]], start="1" if types[i % 5] != "date" else "2026-01-01", step=1,
                 values=["A", "B", "C"]) for i in range(cols)]
    sh = SheetSpec(title="Data", columns=[ColumnSpec(name=f"Column {i + 1}", type=types[i % 5]) for i in range(cols)], row_count=rows,
                   generation_rules=rules_all if full else [GenRule(column="Column 1", kind="sequence", start="1", step=1),
                                     GenRule(column="Column 2", kind="cycle", values=["A", "B", "C"]),
                                     GenRule(column="Column 3", kind="sequence", start="0.5", step=0.5),
                                     GenRule(column="Column 4", kind="date_sequence", start="2026-01-01", step=1)],
                   calculations=[CalcSpec(label="Rows", kind="count", column="Column 1"), CalcSpec(label="Total", kind="sum", column="Column 3")])
    spec = validate_spec(WorkbookSpec(title="Bench", sheets=[sh]), s, rows)
    t = time.perf_counter()
    r = build_workbook(spec, s)
    dt = time.perf_counter() - t
    print(json.dumps({"secs": round(dt, 2), "mb_file": round(len(r.data) / 1e6, 2), "write_only": r.write_only, "styles": r.styles,
                      "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)}))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        a = sys.argv[1:]
        run(int(a[0]), int(a[1]), {"None": None, "True": True, "False": False}[a[2]], len(a) > 3)
    else:
        base = subprocess.run([sys.executable, "-c", "import resource,app.services.excel_service;print(round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024))"],
                              capture_output=True, text=True).stdout.strip()
        print(f"baseline (imports only) peak RSS: {base} MB\n")
        print(f"{'scenario':26} {'secs':>6} {'file MB':>8} {'write-only':>11} {'styles':>7} {'peak RSS MB':>12}")
        for n, (r, c, f, *full) in SCENARIOS.items():
            argv = [sys.executable, __file__, str(r), str(c), str(f), *(["full"] if full else [])]
            o = json.loads(subprocess.run(argv, capture_output=True, text=True).stdout.strip().splitlines()[-1])  # noqa: S603 (fixed argv)
            print(f"{n:26} {o['secs']:>6} {o['mb_file']:>8} {str(o['write_only']):>11} {o['styles']:>7} {o['peak_rss_mb']:>12}")
