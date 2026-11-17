"""Application settings loaded from environment / .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[REPO_ROOT / ".env", BACKEND_ROOT / ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- LLM --------------------------------------------------------------
    # Any endpoint speaking the OpenAI protocol. The code depends on the
    # protocol, not the provider: changing model is configuration.
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_chat_model: str = "gemini-3.5-flash-lite"
    # Tried once when the primary answers 429 or 5xx.
    llm_fallback_model: str = ""
    llm_timeout_seconds: float = 25.0

    # ---- CRM ----------------------------------------------------------------
    # Empty (the demo): the synthetic CRM inside the database answers. Set, the
    # same interface talks to HubSpot's v3 API. See services/crm.py.
    hubspot_token: str = ""

    # ---- Data paths ---------------------------------------------------------
    data_dir: Path = REPO_ROOT / "data"
    # The build writes here; the app serves a working copy, so a reset is a
    # file copy, not a rebuild.
    build_db_path: Path = REPO_ROOT / "data" / "platform.build.duckdb"
    duckdb_path: Path = REPO_ROOT / "data" / "platform.duckdb"

    # ---- Abuse controls (anonymous, LLM-backed endpoints) ------------------
    orb_rate_limit_per_ip: int = 20
    orb_rate_limit_global: int = 300
    orb_rate_limit_window_seconds: float = 300.0
    orb_max_message_chars: int = 2000
    orb_max_context_chars: int = 8000

    # Shared secret for write endpoints. Fail closed: empty refuses writes.
    demo_write_token: str = ""
    # Open demo: any visitor can use the three workflow systems. Their changes
    # live in the working copy, which goes back to the build on every cold
    # start (scale to zero) and on the operator's reset. False restores the
    # token gate on every write.
    public_writes: bool = True
    write_rate_limit_per_ip: int = 300
    write_rate_limit_global: int = 3000

    # Stamped into the image at build time; shown by /api/meta.
    git_sha: str = ""

    cors_origins: str = "http://localhost:5261"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_key(self) -> str:
        # Container Apps cannot hold an empty secret, so "unset" arrives as a space.
        return self.llm_api_key.strip()


settings = Settings()
