# File Converter

A free, open-source file converter you run on your own computer. No uploads to third-party servers, no accounts, no file size restrictions imposed by a website. Your files never leave your machine.

Upload a file, pick a target format, download the result. Files are deleted immediately after download.

## Features

- Convert documents, images, audio, video, and archives
- Files are deleted right after you download them, nothing is stored
- No accounts, no sign-up, no internet connection required after setup
- Upload progress bar so you know something is happening on large files
- Three color themes (Steel, Forest, Ocean)
- Runs entirely on your computer via Docker

## Installation

**You will need:**
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) free, available for Windows, Mac, and Linux
- [Git](https://git-scm.com/downloads) to download the project (or download the ZIP directly from GitHub)

**Steps:**

**Mac / Linux**
```bash
git clone <repo>
cd file-converter
chmod +x start.sh
./start.sh
```

**Windows (PowerShell)**
```powershell
git clone <repo>
cd file-converter
.\start.ps1
```
> If PowerShell says the script cannot be run, paste this first and press Enter:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**Windows (Command Prompt)**
```bat
git clone <repo>
cd file-converter
start.bat
```

The first run will take a few minutes while Docker downloads and builds everything. Once it's ready, open **http://localhost:3000** in your browser.

**To stop the app**, run `./stop.sh`, `.\stop.ps1`, or `stop.bat` depending on your platform, or press `Ctrl+C` in the terminal.

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

---

## For Developers

Everything below is intended for people who want to contribute to or modify the project.

### Security

- **Magic byte validation:** file content is checked against known signatures before conversion; a `.pdf` renamed to `.docx` is rejected
- **Zip Slip protection:** archive member paths are resolved and checked to stay inside the output directory before extraction
- **ZIP bomb protection:** total uncompressed size is capped at 4 GB across all archive converters
- **UUID job IDs:** job IDs are random UUIDs, not sequential integers, preventing enumeration of other users' files
- **NGINX rate limiting:** uploads capped at 3/min, status polling at 30/min, all other API calls at 60/min per IP; returns 429 on excess
- **Non-root containers:** backend and worker run as `appuser` (uid 1001) with all Linux capabilities dropped except `DAC_OVERRIDE`
- **Safe Content-Disposition:** download filenames strip control characters and use RFC 5987 encoding for non-ASCII names, preventing HTTP header injection

### Configuration

All configuration is through environment variables in `.env`. The start scripts create this file automatically. You only need to edit it if you are exposing the app beyond localhost.

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://file-converter:file-converter@postgres:5432/file-converter` |
| `REDIS_URL` | Redis connection string used by Celery | `redis://redis:6379/0` |
| `POSTGRES_USER` | PostgreSQL username | `file-converter` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `file-converter` |
| `POSTGRES_DB` | PostgreSQL database name | `file-converter` |
| `CORS_ORIGINS` | Comma-separated list of allowed CORS origins | `http://localhost:3000` |
| `MAX_FILE_SIZE_MB` | Fallback file size limit in MB for uncategorised formats | `50` |

### Resource Tuning

The worker container is capped at 6 GB RAM and 3 CPU cores by default, with `--concurrency=2` (two parallel conversions). Adjust in `docker-compose.yml` to match your host:

- Each conversion slot needs up to ~3 GB RAM for a 2 GB video file.
- Increase `--concurrency` only if you have enough RAM: `concurrency × 3 GB + 1 GB overhead`.
- `worker_max_tasks_per_child=10` restarts each worker process every 10 tasks to reclaim memory leaked by LibreOffice and ffmpeg.

### Running Without Docker

**Prerequisites:** Python 3.12+, Node 20+, a running Redis instance, a running PostgreSQL instance.

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
celery -A app.tasks worker --loglevel=info --concurrency=2

# Celery Beat scheduler (separate terminal, same backend/ directory)
celery -A app.tasks beat --loglevel=info

# Frontend
cd frontend
npm install
npm run dev
```

The API runs at http://localhost:8000 and the frontend dev server at http://localhost:5173.

### Project Structure

```
file-converter/
├── backend/
│   ├── app/
│   │   ├── config.py      # settings loaded from env vars
│   │   ├── converters.py  # conversion handlers and SUPPORTED_CONVERSIONS map
│   │   ├── main.py        # FastAPI app and all endpoints
│   │   ├── models.py      # SQLAlchemy database models
│   │   └── tasks.py       # Celery tasks (conversion + cleanup beat)
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api.ts         # all API calls
│   │   ├── App.tsx        # theme provider and root
│   │   ├── theme.tsx      # Steel / Forest / Ocean palettes
│   │   └── components/    # Dashboard, DropZone, FormatSelector
│   ├── nginx.conf
│   ├── Dockerfile
│   └── package.json
├── start.sh               # start script (Mac / Linux)
├── stop.sh                # stop script (Mac / Linux)
├── start.ps1              # start script (Windows PowerShell)
├── stop.ps1               # stop script (Windows PowerShell)
├── start.bat              # start script (Windows Command Prompt)
├── stop.bat               # stop script (Windows Command Prompt)
├── docker-compose.yml
└── .env.example
```

## License

MIT | [LICENSE](LICENSE)