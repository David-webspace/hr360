from datetime import date, datetime
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

TZ = ZoneInfo("Asia/Taipei")


class Settings(BaseSettings):
    # .env 裡留空的欄位視為未設定，避免空字串被當成值（例如 APP_TODAY=）
    model_config = SettingsConfigDict(env_ignore_empty=True)

    database_url: str
    jwt_secret: str  # 不給預設值：沒設定就啟動失敗，避免正式環境用到可猜測的固定金鑰
    jwt_ttl_hours: int = 12
    cookie_secure: bool = False
    enable_api_docs: bool = False

    embedding_dim: int = 512
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    model_cache_dir: str = ".cache/models"

    llm_provider: str = "anthropic"  # anthropic / foundry / openai_compatible
    llm_foundry_resource: str | None = None  # Microsoft Foundry 資源名稱
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model_fast: str = "claude-haiku-5-5"
    llm_model_strong: str = "claude-sonnet-5-5"
    llm_model_vision: str | None = None  # 讀取上傳文件用；未設定時用 llm_model_fast（該模型須支援影像）
    llm_anthropic_fallbacks: bool = True  # 只在官方 API（未設定 base_url）時生效
    llm_reasoning_effort: str | None = None  # openai_compatible 才用；Ollama 推理模型建議 none
    llm_pricing_file: str = "config/pricing.yaml"
    llm_router_file: str = "config/router_table.yaml"

    chat_rate_per_minute: int = 12
    chat_daily_token_cap: int = 300_000
    upload_dir: str = "uploads"
    upload_daily_limit: int = 20

    app_today: date | None = None  # 示範資料以 2026-11-10 為基準；未設定時用實際日期


settings = Settings()


def today() -> date:
    return settings.app_today or datetime.now(TZ).date()
