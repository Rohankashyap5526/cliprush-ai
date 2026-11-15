from pathlib import Path
from uuid import uuid4
import os
import base64
import binascii
import secrets

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .config import UPLOAD_DIR, OUTPUT_DIR, MAX_UPLOAD_MB, ALLOWED_EXTENSIONS
from .schemas import AnalyzeRequest, YouTubeInspectRequest
from .youtube import inspect_youtube_url
from .video_utils import probe_video, audio_energy_events, scene_change_events, build_candidates, render_clip, render_ai_clip
from .downloader import inspect_url, download_video
from .groq_ai import transcribe_video, select_highlights

app = FastAPI(title="ClipRush AI", description="Password-protected Groq-powered video clipping studio", version="1.0.0")

class SharedAccessMiddleware(BaseHTTPMiddleware):
    """Single-owner staging gate. Use a unique username/password in deployment secrets."""
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        username = os.getenv("CLIPRUSH_AUTH_USERNAME", "").strip()
        password = os.getenv("CLIPRUSH_AUTH_PASSWORD", "")
        if not username or not password:
            return JSONResponse({"detail": "Deployment access credentials are not configured."}, status_code=503)
        header = request.headers.get("authorization", "")
        try:
            scheme, encoded = header.split(" ", 1)
            if scheme.lower() != "basic": raise ValueError("Unsupported auth scheme")
            supplied = base64.b64decode(encoded, validate=True).decode("utf-8")
            supplied_user, supplied_password = supplied.split(":", 1)
        except (ValueError, UnicodeDecodeError, binascii.Error):
            supplied_user, supplied_password = "", ""
        valid = secrets.compare_digest(supplied_user, username) and secrets.compare_digest(supplied_password, password)
        if not valid:
            return JSONResponse({"detail": "Authentication required."}, status_code=401,
                                headers={"WWW-Authenticate": 'Basic realm="ClipRush AI"'})
        return await call_next(request)

app.add_middleware(SharedAccessMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/clips", StaticFiles(directory=str(OUTPUT_DIR)), name="clips")
VIDEOS = {}
JOBS = {}

@app.get("/")
def root():
    index = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "index.html"
    if index.exists(): return FileResponse(index)
    return {"app": "ClipRush AI", "version": "1.0.0", "docs": "/docs"}

@app.get("/health")
def health():
    return {"status": "ok", "groq_configured": bool(os.getenv("GROQ_API_KEY")),
            "ai_provider": "Groq only", "chat_model": os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-120b"),
            "transcription_model": os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")}

@app.post("/api/videos")
async def upload_video(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS: raise HTTPException(400, f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    video_id = str(uuid4()); destination = UPLOAD_DIR / f"{video_id}{suffix}"; total = 0
    try:
        with destination.open("wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_MB * 1024 * 1024:
                    buffer.close(); destination.unlink(missing_ok=True); raise HTTPException(413, f"File exceeds {MAX_UPLOAD_MB} MB limit.")
                buffer.write(chunk)
        metadata = probe_video(destination)
    except HTTPException: raise
    except Exception as exc:
        destination.unlink(missing_ok=True); raise HTTPException(400, f"Could not read video: {exc}")
    record = {"id": video_id, "filename": file.filename, "path": str(destination), "metadata": metadata,
              "status": "uploaded", "source_type": "upload", "clips": []}
    VIDEOS[video_id] = record
    return {k: v for k, v in record.items() if k != "path"}

@app.post("/api/sources/inspect")
def inspect_source(payload: YouTubeInspectRequest):
    try: return inspect_url(payload.url)
    except ValueError as exc: raise HTTPException(400, str(exc))
    except Exception as exc: raise HTTPException(502, str(exc))

@app.post("/api/sources/download")
def download_source(payload: YouTubeInspectRequest):
    """Retrieve a supported public source when the platform/provider allows it; no auth/DRM bypass."""
    video_id = str(uuid4()); destination = UPLOAD_DIR / f"{video_id}.mp4"
    try:
        info = inspect_url(payload.url)
        source = download_video(payload.url, destination)
        metadata = probe_video(source)
    except ValueError as exc: raise HTTPException(400, str(exc))
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(502, str(exc))
    record = {"id": video_id, "filename": info["title"], "path": str(source), "metadata": metadata,
              "status": "downloaded", "source_type": info["provider"], "source_url": payload.url, "clips": []}
    VIDEOS[video_id] = record
    return {k: v for k, v in record.items() if k != "path"}

@app.post("/api/youtube/inspect")
def inspect_youtube(payload: YouTubeInspectRequest):
    # Backward-compatible metadata preview endpoint.
    try: return inspect_youtube_url(payload.url)
    except ValueError as exc: raise HTTPException(400, str(exc))
    except RuntimeError as exc: raise HTTPException(502, str(exc))

@app.get("/api/videos")
def list_videos(): return [{k: v for k, v in item.items() if k != "path"} for item in VIDEOS.values()]

@app.get("/api/groq/status")
def groq_status(): return {"configured": bool(os.getenv("GROQ_API_KEY")), "provider": "Groq", "chat_model": os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-120b"), "stt_model": os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")}

def _run_analysis_job(job_id: str, video_id: str, options: dict):
    job = JOBS[job_id]
    record = VIDEOS.get(video_id)
    if not record:
        job.update(status="failed", error="Video not found.")
        return
    source = Path(record["path"]); duration = record["metadata"]["duration"]
    try:
        if not os.getenv("GROQ_API_KEY"):
            raise RuntimeError("Add GROQ_API_KEY to your .env file before using AI clipping.")
        job.update(status="transcribing", progress=10, message="Groq Whisper is transcribing audio…")
        record["status"] = "transcribing"
        words, segments = transcribe_video(source)
        job.update(status="selecting", progress=55, message="Groq AI is selecting the best moments…")
        record["status"] = "selecting_highlights"
        candidates = select_highlights(words, segments, duration, options["clip_count"],
                                       options["min_duration"], options["max_duration"], options["content_type"])
        if not candidates:
            raise RuntimeError("Groq did not find any clips matching your duration settings. Try a longer video or wider duration range.")
        clips = []
        for index, candidate in enumerate(candidates):
            job.update(status="rendering", progress=60 + int(35 * index / max(1, len(candidates))),
                       message=f"Rendering clip {index+1} of {len(candidates)} with captions…")
            clip_id = str(uuid4()); output_name = f"{video_id}_{clip_id}.mp4"; output_path = OUTPUT_DIR / output_name
            render_ai_clip(source, output_path, candidate["start"], candidate["end"], options["aspect_ratio"],
                           words, candidate.get("hook", ""), options.get("caption_style", "bold"))
            clips.append({"id": clip_id, "filename": output_name, "url": f"/clips/{output_name}",
                          **candidate, "duration": round(candidate["end"]-candidate["start"], 2)})
        record["status"] = "processed"; record["clips"] = clips; record["transcript_words"] = len(words)
        job.update(status="completed", progress=100, message="Your clips are ready.", clips=clips,
                   transcript_words=len(words), ai_provider="Groq",
                   transcription_model=os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo"),
                   highlight_model=os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-120b"))
    except Exception as exc:
        record["status"] = "failed"
        job.update(status="failed", error=str(exc), message="Clip generation failed.")

@app.post("/api/videos/{video_id}/analyze")
def analyze_video(video_id: str, request: AnalyzeRequest, background_tasks: BackgroundTasks):
    record = VIDEOS.get(video_id)
    if not record: raise HTTPException(404, "Video not found. Upload or import it again after restarting the server.")
    if request.max_duration < request.min_duration: raise HTTPException(400, "max_duration must be greater than or equal to min_duration.")
    if not os.getenv("GROQ_API_KEY"): raise HTTPException(503, "Add GROQ_API_KEY to your .env file before using AI clipping.")
    job_id = str(uuid4())
    JOBS[job_id] = {"id": job_id, "video_id": video_id, "status": "queued", "progress": 0,
                    "message": "Waiting for the worker…", "clips": []}
    background_tasks.add_task(_run_analysis_job, job_id, video_id, request.model_dump())
    return {"job_id": job_id, "status": "queued"}

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job: raise HTTPException(404, "Job not found.")
    return job

@app.delete("/api/videos/{video_id}")
def delete_video(video_id: str):
    record = VIDEOS.pop(video_id, None)
    if not record: raise HTTPException(404, "Video not found.")
    Path(record["path"]).unlink(missing_ok=True)
    for clip in record.get("clips", []): (OUTPUT_DIR / clip["filename"]).unlink(missing_ok=True)
    return {"deleted": video_id}


# Serve the compiled React app from the same origin so Basic Auth also protects clip files.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
