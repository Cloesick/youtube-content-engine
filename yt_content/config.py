"""Configuration — everything comes from environment variables.

NEVER hardcode tokens. In GitHub Actions these are repo Secrets; locally they
live in a gitignored .env (see .env.example).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None, required: bool = False) -> str | None:
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Set it as a GitHub Actions secret or in your local .env."
        )
    return val


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # --- Airtable (the control plane) ---
    airtable_token: str | None
    airtable_base_id: str | None
    channels_table: str
    queue_table: str
    clips_table: str

    # --- YouTube Data API (the scrape layer) ---
    youtube_api_key: str | None
    # How many search results to pull per keyword before ranking by views.
    search_results_per_keyword: int

    # --- Gemini (generation) ---
    gemini_api_key: str | None
    gemini_model: str

    # --- Behaviour ---
    ideas_per_channel: int
    clips_per_source: int
    dry_run: bool

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            airtable_token=_env("AIRTABLE_TOKEN"),
            airtable_base_id=_env("YT_AIRTABLE_BASE_ID"),
            channels_table=_env("YT_CHANNELS_TABLE", "YT Channels"),
            queue_table=_env("YT_QUEUE_TABLE", "YT Content Queue"),
            clips_table=_env("YT_CLIPS_TABLE", "YT Clips"),
            youtube_api_key=_env("YOUTUBE_API_KEY"),
            search_results_per_keyword=int(_env("YT_SEARCH_RESULTS", "25")),
            gemini_api_key=_env("GEMINI_API_KEY"),
            gemini_model=_env("GEMINI_MODEL", "gemini-2.0-flash"),
            ideas_per_channel=int(_env("YT_IDEAS_PER_CHANNEL", "3")),
            clips_per_source=int(_env("YT_CLIPS_PER_SOURCE", "5")),
            dry_run=_flag("YT_DRY_RUN", default=False),
        )
