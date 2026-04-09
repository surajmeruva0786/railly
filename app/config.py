from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "Railly"
    app_env: str = "development"
    debug: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/railly"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = "change-this-to-a-random-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Anthropic
    anthropic_api_key: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
