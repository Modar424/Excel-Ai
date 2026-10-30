# End-to-end test
Real FastAPI (`AI_PROVIDER=mock`) + production frontend build + headless Chromium (Playwright for Python).
```
cd frontend && npm ci && VITE_API_BASE_URL=http://localhost:8000 npm run build && cd ..
pip install playwright && playwright install chromium
python e2e/run_e2e.py
```
Covers: Arabic and English flows, real `.xlsx` downloads (3,000 and 500 rows), UTF-8 filename, error states (quota, invalid spec, AI down, network failure, proxy 502), retry, cancel, validation, theme/lang persistence, mobile 390 px. Does **not** cover the real Groq API or a deployed host.
