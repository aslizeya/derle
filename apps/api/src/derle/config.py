from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (prefix ``DERLE_``) or ``.env``."""

    model_config = SettingsConfigDict(env_prefix="DERLE_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    db_filename: str = "derle.duckdb"

    # AI is strictly optional: with ``llm_provider="none"`` every feature falls back to rules.
    llm_provider: Literal["none", "anthropic"] = "none"
    llm_model: str = "claude-opus-5-5"
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("DERLE_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
    )

    max_upload_bytes: int = 25 * 1024 * 1024

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def blob_dir(self) -> Path:
        return self.data_dir / "blobs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
