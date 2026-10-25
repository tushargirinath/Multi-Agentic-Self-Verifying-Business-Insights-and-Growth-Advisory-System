"""MAVIS Configuration Module."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API Keys & Model Providers
    ANTHROPIC_API_KEY: str = ""
    MAVIS_MODEL: str = "claude-3-5-sonnet-20241022"

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "liquid/lfm-2.5-2.6b:free"
    OLLAMA_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_PROVIDER: str = "openrouter"  # "openrouter" or "ollama"

    # Runtime Budgets
    MAVIS_MAX_STEPS: int = 12
    MAVIS_MAX_TOKENS: int = 60000
    MAVIS_MAX_SECONDS: int = 90
    MAVIS_MAX_REPAIRS: int = 3

    # Storage & Paths
    MAVIS_SANDBOX_MODE: str = "local"  # docker, e2b, or local
    MAVIS_TOKEN_SALT: str = "mavis_secret_salt_2026_salt_token"
    MAVIS_DATA_DIR: str = "data/lakehouse"
    MAVIS_RAW_DATA_PATH: str = "data/raw/sales_transactions.csv"
    MAVIS_DB_URL: str = "sqlite:///data/mavis_app.db"

    # Critic & Quality Parameters
    MAVIS_CRITIC_TOLERANCE: float = 0.005  # 0.5% tolerance

    @property
    def data_path(self) -> Path:
        p = Path(self.MAVIS_DATA_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def duckdb_path(self) -> str:
        return str(self.data_path / "mavis_analytics.duckdb")


settings = Settings()
