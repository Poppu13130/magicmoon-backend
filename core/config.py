from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    REPLICATE_API_TOKEN: str
    WEBHOOK_BASE_URL: str = ""
    REPLICATE_WEBHOOK_SECRET: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()  # type: ignore[call-arg]
