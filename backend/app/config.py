from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str
    database_url: str
    redis_url: str
    cors_origins: str = "http://localhost:3000"
    max_file_size_mb: int = 50

    class Config:
        env_file = ".env"


settings = Settings()