#!/usr/bin/env bash
set -e

if [ ! -f .env ]; then
  cp .env.example .env
  SECRET=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c 48 || openssl rand -hex 24)
  sed -i "s/change-this-to-a-long-random-string/$SECRET/" .env
  echo "Created .env with a generated SECRET_KEY."
  echo "Edit .env if you want to set a custom POSTGRES_PASSWORD before continuing."
  echo ""
fi

docker compose up --build "$@"