"""App configuration: secrets and tunables read from the environment.

This module owns *what* the app is configured with. v1 needed none of this
(CRUD reads no secrets), so it didn't exist. v2 introduces the first secret we
must read — the Anthropic API key for JD parsing — which is what finally earns
pydantic-settings its place here.

Why a settings class instead of scattered os.getenv() calls: pydantic-settings
loads values from the environment and backend/.env, validates their types, and
fails loudly at startup if a required key is missing — rather than blowing up
mid-request with a confusing None. One typed object, one source of truth.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration loaded from the environment and backend/.env.

    Each field maps to an environment variable by name, case-insensitively:
    `anthropic_api_key` is read from ANTHROPIC_API_KEY. A field with no default
    (anthropic_api_key) is required — construction raises if it's absent. A
    field with a default (anthropic_model) is optional and overridable.
    """

    # env_file is relative to where uvicorn runs (backend/), matching the same
    # relative-path convention as DATABASE_URL in database.py. extra="ignore"
    # lets .env hold keys we don't model yet (e.g. JWT_SECRET) without erroring.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # No default: ANTHROPIC_API_KEY must be present or the app won't start.
    anthropic_api_key: str

    # The parsing model lives here as a tunable so we can swap models (e.g. to
    # claude-sonnet-5 if extraction quality needs a step up) without touching
    # code. Vision policy: cheaper capable model for routine parsing work.
    anthropic_model: str = "claude-haiku-4-5"

    # Resume tailoring uses the TOP model, per vision policy ("the top model only
    # for resume tailoring and essay drafts"). Bullet selection and phrasing is
    # the highest-value, most judgment-heavy step, so it earns Opus over Haiku.
    # Verified current against the API docs (July 2026).
    anthropic_tailoring_model: str = "claude-opus-4-8"

    # --- Auth ---------------------------------------------------------------
    # JWT signing secret. No default: JWT_SECRET must be present or the app
    # won't start (same fail-loud rule as anthropic_api_key). Already in .env.
    jwt_secret: str

    # Symmetric signing: one secret both signs and verifies. HS256 is the
    # standard choice when the same server both issues and checks the token.
    jwt_algorithm: str = "HS256"

    # How long a login token stays valid. 7 days for a personal tool, with no
    # refresh token to manage. Minutes because that is the unit the exp math
    # in the auth service will use.
    access_token_expire_minutes: int = 60 * 24 * 7


@lru_cache
def get_settings() -> Settings:
    """Return the app settings, built once and cached for the process lifetime.

    @lru_cache makes this a lazy singleton: the first call constructs Settings
    (reading .env), and every later call returns that same instance instead of
    re-reading the file. Routes and services depend on it via Depends(get_settings),
    exactly like get_db — so a test can override it with a fake if needed.
    """
    return Settings()
