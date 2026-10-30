"""Central, env-driven configuration. All limits are configurable (see docs/LARGE_WORKBOOKS.md)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ai_provider: str = "openrouter"     # "openrouter" (default) | "groq" | "mock" (local E2E/demo only; never for public deploys)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"  # verify availability in Phase 4
    groq_timeout_s: float = 30          # per attempt (SDK-level)
    groq_max_retries: int = 1           # extra attempts on invalid output / transient errors (never on 429/401)
    groq_structured_mode: str = "auto"  # auto | strict | best_effort | json_object
    groq_max_tokens: int = 2500
    groq_temperature: float = 0.2
    groq_fallback_model: str = ""       # optional; used once if the primary model is not found
    ai_total_timeout_s: float = 50      # whole AI step incl. retries / model rotation
    # --- OpenRouter (free-model rotation) ---
    openrouter_api_key: str = ""
    # Priority list of FREE model ids (comma separated). Free models change often: edit via env, no code change needed.
    openrouter_models: str = "openai/gpt-oss-20b:free,google/gemma-4-31b-it:free,openai/gpt-oss-120b:free,meta-llama/llama-3.3-70b-instruct:free,openrouter/free"
    openrouter_auto_discover: bool = True   # also fetch currently-free models from /api/v1/models (cached 1 h) after the configured list
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_s: float = 30        # per model attempt (a slow model no longer blocks: others are started in parallel)
    openrouter_max_attempts: int = 5        # models started per user request (each counts toward the daily limit)
    openrouter_hedge_delay_s: float = 5     # start the next model if the current ones have not answered after this long
    openrouter_parallel: int = 3            # max models running at the same time
    openrouter_max_tokens: int = 3000
    openrouter_temperature: float = 0.2
    openrouter_daily_budget: int = 45       # HTTP requests/UTC day; OpenRouter free = 50/day (1000 after buying $10 credits once)
    openrouter_rpm: int = 18                # OpenRouter free = 20 req/min per account
    openrouter_site_url: str = ""           # optional attribution header (HTTP-Referer)
    openrouter_app_title: str = "SheetCraft AI"
    ai_daily_budget: int = 40           # app-level cap on Groq requests/UTC day; Groq free 70B TPD (100K tokens) binds before 1K RPD

    cors_origins: str = "http://localhost:5173"  # comma-separated, explicit
    max_prompt_chars: int = 4000
    max_request_bytes: int = 64_000
    default_rows: int = 3000
    max_rows: int = 5000      # provisional; confirmed by Phase 5/7 benchmarks
    max_cols: int = 40
    max_header_len: int = 60
    max_sheets: int = 6
    max_cells: int = 200_000         # rows x columns summed over sheets (e.g. 5,000 x 40)
    writeonly_cells_threshold: int = 100_000  # above this, openpyxl write-only mode is used
    max_ai_input_rows: int = 50   # AI never receives bulk data
    generation_timeout_s: float = 45
    max_concurrent_builds: int = 2    # memory guard: a 5,000x40 build peaks ~145 MB (normal mode)
    rate_limit_per_min: int = 5   # per-IP, in-memory (per instance only)
    trust_proxy: bool = False     # True only behind a trusted proxy (e.g. Render) to read X-Forwarded-For
    preview_max_bytes: int = 4500       # cap for the X-Preview response header (JSON before base64)
    app_version: str = "0.6.0"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
