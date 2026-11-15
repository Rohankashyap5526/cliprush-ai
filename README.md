# ClipRush AI — Phase 1 MVP

Local-first video highlight detection and clip export API.

## What works

- Upload MP4, MOV, MKV, WebM and AVI videos
- Inspect public YouTube URL metadata and show a privacy-enhanced preview (no media downloading)
- Probe video metadata with FFprobe
- Detect high-energy audio windows
- Detect approximate visual scene changes
- Rank and select candidate moments
- Export vertical 9:16, square 1:1 or landscape 16:9 MP4 clips

**Honest limitation:** Phase 1 uses signal-based candidate detection. It does not understand semantic meaning, identify specific GTA events, or guarantee viral clips. Speech transcription, semantic ranking, user accounts, cloud jobs and payments are later phases.

## Requirements

- Python 3.11 recommended
- FFmpeg + FFprobe installed and available in PATH
- Windows, macOS or Linux
- Internet is not required after Python dependencies are installed

## Install FFmpeg on Windows

1. Download an FFmpeg build from https://www.gyan.dev/ffmpeg/builds/
2. Extract it, for example to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to your Windows PATH
4. Open a **new** terminal and verify:

```powershell
ffmpeg -version
ffprobe -version
```

## Setup on Windows PowerShell

```powershell
cd cliprush-ai-phase1
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Open API docs at http://127.0.0.1:8000/docs

## Test the API

### 1. Health check

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

### 2. Upload a video

```powershell
$upload = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/videos `
  -Form @{ file = Get-Item "C:\Videos\sample.mp4" }

$upload
```

Copy the returned `id`.

### 3. Analyze and export clips

```powershell
$body = @{
  clip_count = 5
  min_duration = 15
  max_duration = 45
  aspect_ratio = "9:16"
  content_type = "hybrid"
} | ConvertTo-Json

$result = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/videos/$($upload.id)/analyze" `
  -ContentType "application/json" `
  -Body $body

$result.clips
```

Open a returned clip URL in your browser, for example:

`http://127.0.0.1:8000/clips/RETURNED_FILENAME.mp4`

### 4. Delete source and generated clips

```powershell
Invoke-RestMethod -Method Delete `
  -Uri "http://127.0.0.1:8000/api/videos/$($upload.id)"
```

## YouTube URL support (metadata + preview only)

ClipRush can validate common YouTube video URL formats and retrieve public metadata through YouTube's oEmbed endpoint. This feature does **not** download YouTube video/audio. A public URL alone does not grant permission to copy or process the underlying video.

### Inspect a YouTube URL

```powershell
$payload = @{ url = "https://www.youtube.com/watch?v=VIDEO_ID" } | ConvertTo-Json
$youtube = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/youtube/inspect `
  -ContentType "application/json" -Body $payload

$youtube
```

The response includes title, channel, thumbnail, embed URL and `processing_status: authorized_source_required`.

To create clips, obtain the source file from the creator or another source you are authorized to process, then upload it through `POST /api/videos` and use the existing analyze endpoint. Do not use third-party downloaders or bypass YouTube restrictions.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/api/youtube/inspect` | Validate YouTube URL and fetch public metadata only |
| POST | `/api/videos` | Upload |
| GET | `/api/videos` | List current-process uploads |
| POST | `/api/videos/{id}/analyze` | Detect and render clips |
| DELETE | `/api/videos/{id}` | Delete source and clips |
| GET | `/clips/{filename}` | Serve generated clip |

## Notes

- Uploaded files and clips are stored in `data/`.
- The current in-memory video registry resets when the server restarts. Re-upload videos after restart.
- Processing is synchronous in this MVP. Do not expose this development server publicly.
- The default upload cap is 1 GB. Change `CLIPRUSH_MAX_UPLOAD_MB` to adjust it.
- The first render of a long video may take time.
- 9:16 output uses center cropping. Face tracking and intelligent subject reframing are not included yet.
- Only process content you own or have permission to use.


# ClipRush AI Full Stack — React dashboard

## Run backend

From the project root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Run frontend

Open a second PowerShell terminal:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open http://localhost:5173

The frontend calls the backend at `http://127.0.0.1:8000` by default. Change `VITE_API_BASE` in `frontend/.env` if needed, then restart Vite.

## Frontend functionality

- Dashboard overview and current-session stats
- Direct video upload to `POST /api/videos`
- YouTube URL metadata inspection through `POST /api/youtube/inspect`
- Explicit authorized-source upload workflow (does not download YouTube media)
- Clip preferences and generation through `POST /api/videos/{id}/analyze`
- Preview and download generated MP4 clips
- API status indicator and readable errors

## Current MVP limitations

- No login, billing, cloud storage, persistent database, background job queue or multi-user isolation.
- Video registry is in memory and resets on backend restart; upload again after restarting.
- Processing is synchronous and intended for local testing only.
- Do not expose this development server to the public internet.

## Troubleshooting

- **Groq `invalid_media_file` (400):** ClipRush extracts mono 16 kHz PCM WAV chunks and validates each chunk with FFprobe before upload. If this persists, verify FFmpeg/FFprobe are installed and re-encode the source video to MP4 with AAC audio.
- **Source download HTTP 403:** This is a platform/CDN refusal, not a Groq error. Update yt-dlp with `py -m pip install -U yt-dlp`, retry later, or upload a video file directly. Some URLs remain unavailable; ClipRush does not bypass access controls.
