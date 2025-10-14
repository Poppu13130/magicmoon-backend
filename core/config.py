from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    REPLICATE_API_TOKEN: str
    WEBHOOK_BASE_URL: str = ""
    REPLICATE_WEBHOOK_SECRET: str | None = None
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str
    SUPABASE_JWT_AUDIENCE: str = "authenticated"
    SUPABASE_JWT_ALGORITHM: str = "HS256"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()  # type: ignore[call-arg]
