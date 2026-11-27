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
    # Accuracy-first default: on CPU int8, `medium` measured 59.8% WER on the
    # Persian fixture vs 78.0% for `small` (~1.1x realtime on 2 cores, ~800 MB
    # download). Set WHISPER_MODEL_SIZE=small for the speed-first profile.
    whisper_model_size: str = "medium"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    # Decoding knobs: beam width, and a domain lexicon whispered to the
    # decoder up front so names and technical terms survive transcription.
    # The default prompt also nudges the decoder towards standard written
    # orthography (ZWNJ-correct Persian): measured -1.3 WER points on small,
    # -4.8 on the fine-tuned checkpoint (benchmarks/tune_decode.py).
    whisper_beam_size: int = 5
    whisper_initial_prompt: str = (
        "این صدا به فارسی است. متن را با املای استاندارد و نیم‌فاصلهٔ درست بنویس: "
        "می‌شود، می‌گویم، کتاب‌ها، بزرگ‌ترین."
    )

    # Orthographic Persian polish (ZWNJ repair, Arabic look-alikes, split
    # imperatives, digits) applied to every transcript before storage.
    # Measured -3.6 WER points on the fixture; never rewords colloquial
    # speech. Disable for raw model output.
    fa_polish: bool = True

    # Transcript post-processing: rule-based Persian punctuation restoration
    # (v1.4) and the confidence threshold under which a segment is flagged
    # for human review in the exports and the dashboard.
    punctuation_enabled: bool = True
    low_confidence_threshold: float = 0.5

    # Decode audio block-by-block while transcribing (peak RAM proportional
    # to the 30-second window, not the file length). Diarization engines
    # other than "stub" need the whole signal at once and force the legacy
    # full decode automatically.
    streaming_decode: bool = True

    # Diarization (optional, behind a feature flag)
    # stub = no speaker labels | energy = heuristic two-cluster splitter | pyannote = neural
    diarization_engine: str = "stub"
    pyannote_hf_token: str = ""
    pyannote_model: str = "pyannote/speaker-diarization-3.1"

    # Quota — the free tier is deliberately tight ("not too free"): short
    # files and a small monthly allowance. Pro subscribers get higher caps
    # (see sokhan.core.plans) while their subscription is unexpired.
    free_minutes_per_user_per_month: int = 30
    plan_free_max_file_minutes: int = 10
    plan_pro_max_file_minutes: int = 180
    plan_pro_monthly_minutes: int = 1200
    max_upload_mb: int = 200

    # Admin operations (plan grants): shared secret sent as X-Admin-Key.
    # Leave empty to disable the admin endpoints entirely.
    admin_api_key: str = ""

    bot_api_secret: str = ""

    # Dashboard session cookie (httpOnly). AUTH_COOKIE_SECURE=auto sets the
    # Secure attribute whenever the browser came in over HTTPS (directly or
    # via X-Forwarded-Proto); true/false force it. The web app proxies the
    # API under its own origin (/api), so SameSite=lax always applies; a
    # separately hosted API on another site needs "none" plus HTTPS.
    auth_cookie_secure: str = "auto"
    auth_cookie_samesite: str = "lax"
    auth_cookie_max_age_days: int = 30

    # LLM summaries (optional, behind a feature flag)
    summary_enabled: bool = False
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    # Web / bot integration
    web_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"

    # Job-completion webhooks: a job can carry a callback_url; when it
    # finishes, the worker POSTs a JSON payload signed with this secret in
    # `X-Sokhan-Signature` (t=<unix>,v1=<hex hmac-sha256(timestamp.body)>).
    # Leave empty to deliver callbacks unsigned.
    webhook_signing_secret: str = ""
    webhook_timeout_seconds: float = 4.0
    webhook_attempts: int = 2
    webhook_allow_private_targets: bool = False

    login_max_failures: int = 10
    login_failure_window_seconds: int = 900


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
