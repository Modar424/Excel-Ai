#!/usr/bin/env bash
# Starts backend (:8000) and frontend (:5173). Usage: ./run_local.sh [mock]   (mock = no Groq key needed)
set -e
cd "$(dirname "$0")"
[ "$1" = "mock" ] && export AI_PROVIDER=mock
[ -f backend/.env ] || cp backend/.env.example backend/.env
[ -f frontend/.env ] || cp frontend/.env.example frontend/.env
[ -d backend/.venv ] || python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -q -r backend/requirements.txt
(cd frontend && npm install --silent)
(cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000) & API=$!
trap 'kill $API 2>/dev/null' EXIT
cd frontend && npm run dev -- --port 5173
