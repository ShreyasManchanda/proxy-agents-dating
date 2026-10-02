"""Single config file. Every tunable number from SPEC §5 lives here."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # secrets / connections (env only)
    database_url: str = ""
    apify_token: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # models (names live in config, SPEC §2)
    gemini_model: str = "gemini-3.5-flash-lite"
    groq_model: str = "openai/gpt-oss-120b"

    # Spend control. Gemini is on a paid tier (4K RPM / 150K RPD on Flash-Lite, AI Studio 2026-10-02),
    # so the limit that matters is dollars. Groq stays free and takes overflow.
    # USD per 1M tokens (input, output incl. thinking), ai.google.dev/pricing 2026-10-02.
    prices: dict[str, tuple[float, float]] = {
        "gemini:gemini-3.1-flash-lite": (0.25, 1.50),
        "gemini:gemini-3.5-flash-lite": (0.30, 2.50),
        "gemini:gemini-3.5-flash": (1.50, 9.00),
    }
    llm_budget_usd: float = 5.0  # whole-project ceiling for paid LLM calls; owner to confirm ($ or INR 500?)
    # Groq free limits per model: 1000 RPD, 8K TPM (response headers, 2026-10-02)
    daily_caps: dict[str, int] = {
        "groq:openai/gpt-oss-120b": 900, "groq:openai/gpt-oss-20b": 900, "groq:qwen/qwen3.8-27b": 900,
    }
    apify_monthly_budget_usd: float = 4.00  # plan credit is $5; stay under it

    # temperatures
    temp_extract: float = 0.3
    temp_turn: float = 0.8
    temp_verdict: float = 0.3
    temp_rank: float = 0.3

    # date structure
    turn_plan: tuple[int, ...] = (3, 4, 3)
    max_words_per_turn: int = 70
    verdict_samples: int = 2

    # scoring
    own_weight: float = 0.6
    partner_effect_shrink: float = 1.0
    min_dates_for_rater_z: int = 5
    stated_signal_baseline_weight: float = 0.3
    stated_conflict_penalty: float = 0.05
    conflict_topics: tuple[str, ...] = (
        "family_plans", "relationship_intent", "location_relocation",
    )

    # extraction / ingest
    persona_card_tokens: int = 900
    images_per_person: int = 8
    li_posts: int = 10
    apify_max_charge_per_run_usd: float = 0.10

    # live pools
    live_pool_max: int = 8
    live_concurrency: int = 1  # Apify free plan: 5 concurrent actor jobs, 3 per person
    live_turn_plan: tuple[int, ...] = (3, 4, 3)
    live_verdict_samples: int = 2

    # diagnostics
    retest_fraction: float = 0.10
    orderswap_sample: int = 10


settings = Settings()
