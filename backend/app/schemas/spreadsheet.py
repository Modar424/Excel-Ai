"""Request schema + AI spec schema (contract in docs/API_CONTRACT.md). Extended in Phases 3-5."""
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u2028\u2029\u202a-\u202e\u2066-\u2069]")  # incl. bidi override/isolate controls
ColType = Literal["text", "integer", "decimal", "currency", "percent", "date", "boolean"]


class GenerateRequest(BaseModel):
    """Hard ceilings live in Settings (checked in the route); schema only enforces basic shape."""
    prompt: str = Field(min_length=3, max_length=20000)
    language: Literal["ar", "en"] = "ar"
    max_rows: int | None = Field(default=None, ge=1)

    @field_validator("prompt")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = _CTRL.sub("", v).strip()  # drop control chars (keep \t \n \r)
        if len(v) < 3:
            raise ValueError("prompt too short")
        return v


class ColumnSpec(BaseModel):
    name: str = Field(min_length=1)
    type: ColType = "text"


GenKind = Literal["sequence", "constant", "date_sequence", "cycle"]


class GenRule(BaseModel):
    """Deterministic row generator executed by Python (Phase 5), never by the model."""
    column: str
    kind: GenKind
    start: str | None = None       # sequence start number / ISO start date / constant value
    step: float | None = None
    values: list[str] = []         # for cycle


class CalcSpec(BaseModel):
    label: str
    kind: Literal["count", "counta", "sum", "average", "min", "max",
                  "countif", "sumif", "averageif", "countifs", "ratio", "unique_count",
                  "duplicate_count", "missing_count", "date_span_days", "avg_days_between"]
    column: str | None = None
    criteria_column: str | None = None
    criteria: str | None = None
    group_by: str | None = None  # expands to one row per value in group_values
    group_values: list[str] = []


class SheetSpec(BaseModel):
    title: str = Field(min_length=1)
    columns: list[ColumnSpec] = Field(min_length=1)
    rows: list[list[str | float | int | bool | None]] = []   # only small explicit data
    row_count: int = 0                                       # blank/template rows to prepare
    generation_rules: list[GenRule] = []                        # deterministic Python generators
    calculations: list[CalcSpec] = []
    notes: list[str] = []
    synthetic: bool = False                                  # labels synthetic data


class WorkbookSpec(BaseModel):
    title: str
    sheets: list[SheetSpec] = Field(min_length=1)
    rtl: bool = False
