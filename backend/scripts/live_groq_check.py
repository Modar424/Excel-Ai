"""OPTIONAL manual check against the real Groq API (uses your free quota; 1 request).
Usage: GROQ_API_KEY=... python scripts/live_groq_check.py "Create a monthly expenses sheet"
Not run in CI. Not run by the author in Phase 4 (no key available)."""
import asyncio
import sys

from app.core.config import Settings
from app.services.groq_service import GroqService


async def main():
    s = Settings()
    sv = GroqService(s)
    spec = await sv.generate_spec(sys.argv[1] if len(sys.argv) > 1 else "Create an employee sheet with totals", "en", 3000)
    print(spec.model_dump_json(indent=1)[:2000])
    print("usage:", sv.usage)

asyncio.run(main())
