"""Application settings loaded from environment variables.

Every field maps 1:1 to a variable documented in the repository's
.env.example. Settings are cached so tests can override environment
variables per test and clear the cache afterwards.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    database_url: str = "sqlite:///./sokhan-dev.sqlite3"
    redis_url: str = "redis://localhost:6379/0"
    celery_enabled: bool = True
    data_dir: str = "./data"

    # Whisper
    whisper_model_size: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Diarization (optional, behind a feature flag)
    # stub = no speaker labels | energy = heuristic two-cluster splitter | pyannote = neural
    diarization_engine: str = "stub"
    pyannote_hf_token: str = ""
    pyannote_model: str = "pyannote/speaker-diarization-3.1"

    # Quota
    free_minutes_per_user_per_month: int = 30
    max_upload_mb: int = 200

    # LLM summaries (optional, behind a feature flag)
    summary_enabled: bool = False
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    # Web / bot integration
    web_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
