# ClipRush AI

A password-protected, single-instance deployment of the ClipRush AI video clipping MVP. The React/Vite interface and FastAPI backend are served from one origin; Groq handles speech transcription and highlight selection; FFmpeg renders the final clips.

## Features

- Upload MP4, MOV, MKV, WebM, AVI and M4V video files
- Inspect supported public video URLs and import sources when the provider permits access
- Transcribe audio with Groq Whisper (`whisper-large-v3-turbo` by default)
- Select candidate highlights with Groq (`openai/gpt-oss-120b` by default)
- Render captioned 9:16, 1:1 and 16:9 MP4 clips with FFmpeg
- React dashboard served by FastAPI from the same origin
- HTTP Basic Authentication for the dashboard, API, documentation and generated clips

Only process videos you own or have permission to use. Source URL imports are best-effort and do not bypass logins, DRM, paywalls, or provider restrictions.

## Deploy to Render

1. Push this repository to GitHub.
2. In Render, choose **New → Blueprint** and select this repository. Render reads `render.yaml` and builds the Docker image.
3. In the service's Environment settings, set these secret values:
   - `GROQ_API_KEY`: create a key in the Groq Console.
   - `CLIPRUSH_AUTH_USERNAME`: choose a private username.
   - `CLIPRUSH_AUTH_PASSWORD`: set a long, unique password (at least 24 random characters recommended).
4. Deploy. Open the service URL; the browser will request the Basic Auth username and password.
5. Check `/health` for service health. The endpoint intentionally does not reveal secrets.

Do not commit `.env` or put the Groq key in a `VITE_*` variable. The API key belongs only in the Render backend environment.

### Render free-plan limitations

The supplied Blueprint uses Render's free web-service plan to keep initial hosting cost at zero. Free instances can sleep and their local filesystem is ephemeral. Uploaded videos, generated clips, in-memory job state and video records can be lost when the service restarts, redeploys or sleeps. The app is therefore suitable for a protected demo/test deployment, not durable production storage. For reliable production use, add a persistent disk or object storage, a database and a durable background worker; these may incur charges.

The app currently uses one shared Basic Auth login, one process-local registry and in-process background tasks. It is not a multi-user SaaS: users sharing the login also share the same service instance and its files. Do not distribute the shared credentials publicly. For public launch, implement individual accounts, per-user authorization, rate limits/quotas, durable job processing, persistent storage, monitoring and abuse controls first.

## Local development

### Requirements

- Python 3.11+
- Node.js 20+
- FFmpeg and FFprobe on `PATH`
- A Groq API key for clip generation

### Backend

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Set `GROQ_API_KEY`, `CLIPRUSH_AUTH_USERNAME` and `CLIPRUSH_AUTH_PASSWORD` in `.env`. The frontend dev server runs on a different origin, so local browser calls to the protected backend may trigger the browser's Basic Auth prompt.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

For local Vite development, set `VITE_API_BASE=http://127.0.0.1:8000` in `frontend/.env`. In the Docker deployment this variable is empty and the UI uses the same origin.

## Environment variables

| Variable | Required | Purpose |
|---|---:|---|
| `GROQ_API_KEY` | Yes for AI generation | Secret Groq API key |
| `CLIPRUSH_AUTH_USERNAME` | Yes for all routes except health | Shared dashboard/API login |
| `CLIPRUSH_AUTH_PASSWORD` | Yes for all routes except health | Shared dashboard/API password |
| `GROQ_CHAT_MODEL` | No | Defaults to `openai/gpt-oss-120b` |
| `GROQ_STT_MODEL` | No | Defaults to `whisper-large-v3-turbo` |
| `CLIPRUSH_MAX_UPLOAD_MB` | No | Defaults to 1024 locally; Blueprint sets 500 |
| `CLIPRUSH_DATA_DIR` | No | Writable upload/output directory |
| `PORT` | No | Render supplies this; Docker defaults to 10000 |

## API

- `GET /health` — unauthenticated health check
- `POST /api/videos` — upload a video
- `GET /api/videos` — list videos in the current process
- `POST /api/videos/{video_id}/analyze` — start clip generation
- `GET /api/jobs/{job_id}` — inspect in-process job status
- `DELETE /api/videos/{video_id}` — delete source and generated clips
- `POST /api/sources/inspect` — inspect a supported source URL
- `POST /api/sources/download` — best-effort import where permitted
- `GET /clips/{filename}` — serve generated clips (authentication required)

## Current limitations

- No individual user accounts, billing, persistent database, object storage or durable queue.
- Jobs and video metadata live in process memory; restart loses the registry.
- Render free filesystem is ephemeral; files are not durable.
- The shared Basic Auth gate is for a private demo, not a public multi-tenant product.
- Clip selection quality depends on speech/transcript quality and model output; results are not guaranteed to be viral or factually perfect.
- Center crop is used for vertical output; face tracking and intelligent subject reframing are not included.

## Troubleshooting

- **401 / browser login:** enter the Render environment username/password configured for `CLIPRUSH_AUTH_USERNAME` and `CLIPRUSH_AUTH_PASSWORD`.
- **503 deployment credentials not configured:** set both auth variables and redeploy.
- **Groq key missing:** set `GROQ_API_KEY` in the service's secret environment variables.
- **FFmpeg not found:** the Docker image installs FFmpeg and FFprobe; local development must install them separately.
- **Files disappear after restart:** expected on the free ephemeral filesystem. Use persistent storage/object storage for durable use.
