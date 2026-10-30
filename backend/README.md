# SheetCraft AI — Backend
FastAPI + openpyxl (+ Groq from Phase 4).
```
cd backend && pip install -r requirements.txt
cp .env.example .env   # set GROQ_API_KEY (Phase 4)
uvicorn app.main:app --reload      # http://localhost:8000/docs
pytest -q
```
Status (Phase 3): API skeleton, validation, limits, errors, CORS, rate limit, minimal xlsx writer. AI call is a stub (503 `ai_unavailable`); tests use a mock provider. Full config: `app/core/config.py` (env-overridable).

Benchmark: `PYTHONPATH=. python scripts/benchmark_excel.py`. Formula-recalculation tests need LibreOffice (`soffice`); they skip otherwise.
