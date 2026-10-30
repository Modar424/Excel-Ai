"""Recalculate an .xlsx with headless LibreOffice and return an openpyxl workbook with computed values."""
import os
import shutil
import subprocess
import tempfile

from openpyxl import load_workbook

SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")


def recalc(data: bytes):
    with tempfile.TemporaryDirectory() as d:
        src, out = os.path.join(d, "in.xlsx"), os.path.join(d, "out")
        os.makedirs(out)
        open(src, "wb").write(data)
        subprocess.run(  # noqa: S603 (fixed argv; test helper)
            [SOFFICE, f"-env:UserInstallation=file://{d}/profile", "--headless", "--calc", "--convert-to", "xlsx",
                        "--outdir", out, src], check=True, capture_output=True, timeout=180)
        return load_workbook(os.path.join(out, "in.xlsx"), data_only=True)
