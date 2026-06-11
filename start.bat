@echo off
if not exist .env (
    copy .env.example .env
    echo Created .env from defaults.
    echo Edit .env to set a strong POSTGRES_PASSWORD before continuing.
    echo.
)
docker compose up --build %*