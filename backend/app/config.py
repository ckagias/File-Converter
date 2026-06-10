from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str
    redis_url: str
    cors_origins: str = "http://localhost:3000"
    max_file_size_mb: int = 50

    upload_dir: Path = Path("/app/uploads")
    output_dir: Path = Path("/app/outputs")


settings = Settings()