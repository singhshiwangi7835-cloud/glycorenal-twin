"""App settings, read from environment variables and the .env file (pydantic-settings).

Clinical numbers are NOT here: they live in config/clinical_rules.yaml and config/alerts.yaml.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
DEV_JWT_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8",
                                      extra="ignore")

    # database (SQLite file by default; any SQLAlchemy URL such as PostgreSQL also works)
    database_url: str = f"sqlite:///{(ROOT / 'data' / 'twin.db').as_posix()}"

    # auth
    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 12 * 60

    # LLM (primary = Kimi, backup = Gemini); empty = template fallback only
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_fallback_base_url: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_model: str = ""
    llm_timeout_s: float = 40.0

    # data sources
    fhir_base_url: str = "https://hapi.fhir.org/baseR4"
    fhir_auth_token: str = ""          # optional Bearer token for a hospital FHIR server (never commit)
    ehr_sync_minutes: int = 60         # linked hospital patients are re-pulled this often (0 = off)
    dexcom_client_id: str = ""
    dexcom_client_secret: str = ""
    dexcom_base_url: str = "https://sandbox-api.dexcom.com"
    dexcom_redirect_uri: str = "http://localhost:8000/devices/dexcom/callback"
    sim_speed_seconds: float = 3.0
    sim_autostart: str = "IND-0042"   # comma-separated patient ids whose simulator starts with the API

    # UI
    api_url: str = "http://localhost:8000"

    # local time zone for medicine reminder times such as "08:00" (stored times are UTC)
    timezone: str = "Asia/Kolkata"

    # seed demo data automatically when the database is empty
    auto_seed: bool = True

    # background jobs (daily twin re-run); tests switch this off
    scheduler_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
