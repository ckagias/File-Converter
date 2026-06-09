# File Converter

A self-hosted file conversion service with user authentication, background processing, and support for documents, images, audio, video, and archives.

## Features

- User authentication with JWT (register, login, 24-hour tokens)
- Background file conversion via Celery + Redis
- Per-user file isolation (UUID-prefixed storage, jobs scoped to owner)
- Strict file size limits per category (images 50 MB, documents 100 MB, audio 200 MB, archives 500 MB, video 2 GB)
- Support for documents, images, audio, video, and archives
- Docker Compose setup — one command to run

## Supported Formats

### Documents

| Format | Converts To |
|--------|-------------|
| PDF | DOCX, TXT, JPG, PNG |
| DOCX | PDF, TXT, HTML |
| PPTX | PDF, JPG, PNG |
| XLSX | PDF, CSV |
| ODT | PDF |

### Images

| Format | Converts To |
|--------|-------------|
| JPG / JPEG | PNG, WEBP, BMP, TIFF, PDF |
| PNG | JPG, WEBP, BMP, TIFF, PDF |
| WEBP | JPG, PNG, BMP, TIFF, PDF |
| BMP | JPG, PNG, WEBP, TIFF, PDF |
| TIFF | JPG, PNG, WEBP, BMP, PDF |
| SVG | PNG, JPG |
| ICO | PNG |

### Audio

| Format | Converts To |
|--------|-------------|
| MP3 | WAV, OGG, FLAC, AAC, M4A |
| WAV | MP3, OGG, FLAC, AAC, M4A |
| OGG | MP3, WAV, FLAC, AAC, M4A |
| FLAC | MP3, WAV, OGG, AAC, M4A |
| AAC | MP3, WAV, OGG, FLAC, M4A |
| M4A | MP3, WAV, OGG, FLAC, AAC |

### Video

| Format | Converts To |
|--------|-------------|
| MP4 | MKV, AVI, MOV, WEBM, MP3 |
| MKV | MP4, AVI, MOV, WEBM, MP3 |
| AVI | MP4, MKV, MOV, WEBM |
| MOV | MP4, MKV, AVI, WEBM |
| WEBM | MP4, MKV, AVI, MOV |

### Archives

| Format | Converts To |
|--------|-------------|
| ZIP | 7Z, TAR.GZ |
| 7Z | ZIP |
| TAR.GZ | ZIP |

## Quickstart

```bash
git clone <repo>
cd file-converter
cp .env.example .env
# Edit .env and set a strong SECRET_KEY
docker compose up --build
```

Open http://localhost:3000

## Configuration

All configuration is through environment variables. Copy `.env.example` to `.env` and edit before starting.

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing secret — use a long random string in production | `change-this-to-a-long-random-string` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://file-converter:file-converter@postgres:5432/file-converter` |
| `REDIS_URL` | Redis connection string used by Celery | `redis://redis:6379/0` |
| `POSTGRES_USER` | PostgreSQL username (used by the postgres container) | `file-converter` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `file-converter` |
| `POSTGRES_DB` | PostgreSQL database name | `file-converter` |
| `CORS_ORIGINS` | Comma-separated list of allowed CORS origins | `http://localhost:3000` |
| `MAX_FILE_SIZE_MB` | Fallback file size limit in MB for uncategorised formats | `50` |

## Development

Run each service independently without Docker.

**Prerequisites:** Python 3.11+, Node 20+, a running Redis instance, a running PostgreSQL instance.

```bash
# Redis
docker run -p 6379:6379 redis:7-alpine

# PostgreSQL
docker run \
  -e POSTGRES_USER=file-converter \
  -e POSTGRES_PASSWORD=file-converter \
  -e POSTGRES_DB=file-converter \
  -p 5432:5432 \
  postgres:16-alpine

# Backend API
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Celery worker (separate terminal, same backend/ directory)
cd backend
celery -A app.tasks worker --loglevel=info

# Frontend
cd frontend
npm install
npm run dev
```

The API runs at http://localhost:8000 and the frontend dev server at http://localhost:5173.

## Project Structure

```
file-converter/
├── backend/
│   ├── app/
│   │   ├── config.py      # settings loaded from env vars
│   │   ├── converters.py  # conversion handlers and SUPPORTED_CONVERSIONS map
│   │   ├── main.py        # FastAPI app and all endpoints
│   │   ├── models.py      # SQLAlchemy database models
│   │   └── tasks.py       # Celery background tasks
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api.ts         # all API calls
│   │   ├── App.tsx        # auth router (login / main view)
│   │   └── components/    # UI components
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
└── .env.example
```

## License

MIT — see LICENSE