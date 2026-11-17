"""ClipRush AI backend: FastAPI app serving the API, generated clips and the built React UI."""
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from .auth import BasicAuthMiddleware
from .config import (ALLOWED_EXTENSIONS, MAX_CONCURRENT_JOBS, MAX_UPLOAD_MB, OUTPUT_DIR, RETENTION_HOURS,
                     STATE_FILE, UPLOAD_DIR)
from .downloader import download_video, inspect_url
from .groq_ai import chat_model, select_highlights, stt_model, transcribe_video
from .schemas import AnalyzeRequest, SourceRequest
from .store import ACTIVE_VIDEO_STATES, Store, public_video
from .video_utils import probe_video, render_ai_clip

log = logging.getLogger("cliprush")
VERSION = "1.1.0"

store = Store(STATE_FILE)
# Rendering is CPU-heavy: run analysis jobs through a small worker pool so a small server is not
# overwhelmed. Downloads are network-bound and use their own pool so they never block rendering.
ANALYSIS_POOL = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS, thread_name_prefix="cliprush-analyze")
IMPORT_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cliprush-import")


# ---------------------------------------------------------------------------------------
# File housekeeping
# ---------------------------------------------------------------------------------------
def _slug(text: str, fallback: str = "clip") -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-").lower()[:50] or fallback


def _unlink_clip_files(clip: dict) -> None:
    (OUTPUT_DIR / clip["filename"]).unlink(missing_ok=True)
    (OUTPUT_DIR / clip["filename"]).with_suffix(".srt").unlink(missing_ok=True)


def _delete_video_files(record: dict) -> None:
    Path(record["path"]).unlink(missing_ok=True)
    (UPLOAD_DIR / f"{record['id']}.transcript.json").unlink(missing_ok=True)
    for clip in record.get("clips", []):
        _unlink_clip_files(clip)


def cleanup_expired(now: float | None = None) -> int:
    """Delete projects (and stray files) older than CLIPRUSH_RETENTION_HOURS. Returns the number removed."""
    if not RETENTION_HOURS:
        return 0
    cutoff = (now or time.time()) - RETENTION_HOURS * 3600
    removed = 0
    for record in list(store.videos.values()):
        if record.get("created_at", 0) < cutoff and record.get("status") not in ACTIVE_VIDEO_STATES:
            _delete_video_files(record)
            store.pop_video(record["id"])
            removed += 1
    live_ids = set(store.videos)
    for folder, id_of in ((UPLOAD_DIR, lambda n: n.split(".")[0]), (OUTPUT_DIR, lambda n: n.split("_")[0])):
        for path in folder.iterdir():
            try:
                if path.is_file() and id_of(path.name) not in live_ids and path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                continue
    return removed


def _cleanup_loop() -> None:
    while True:
        time.sleep(3600)
        try:
            removed = cleanup_expired()
            if removed:
                log.info("Retention cleanup removed %d expired project(s).", removed)
        except Exception:  # never let housekeeping crash the process
            log.exception("Retention cleanup failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        cleanup_expired()
    except Exception:
        log.exception("Startup cleanup failed")
    if RETENTION_HOURS:
        threading.Thread(target=_cleanup_loop, name="cliprush-cleanup", daemon=True).start()
    yield
    ANALYSIS_POOL.shutdown(wait=False, cancel_futures=True)
    IMPORT_POOL.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------------------
app = FastAPI(title="ClipRush AI", description="Password-protected Groq-powered video clipping studio",
              version=VERSION, lifespan=lifespan)
# Middleware order: the last one added is outermost, so CORS preflights are answered before auth runs.
app.add_middleware(BasicAuthMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/clips", StaticFiles(directory=str(OUTPUT_DIR)), name="clips")


@app.get("/health")
def health():
    return {
        "status": "ok", "version": VERSION,
        "groq_configured": bool(os.getenv("GROQ_API_KEY")),
        "ai_provider": "Groq only", "chat_model": chat_model(), "transcription_model": stt_model(),
        "ffmpeg_available": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
        "yt_dlp_available": bool(shutil.which("yt-dlp")),
        "max_upload_mb": MAX_UPLOAD_MB, "retention_hours": RETENTION_HOURS,
        "max_concurrent_jobs": MAX_CONCURRENT_JOBS,
    }


@app.get("/api/groq/status")
def groq_status():
    return {"configured": bool(os.getenv("GROQ_API_KEY")), "provider": "Groq",
            "chat_model": chat_model(), "stt_model": stt_model()}


# ---------------------------------------------------------------------------------------
# Sources: upload / URL import
# ---------------------------------------------------------------------------------------
@app.post("/api/videos")
async def upload_video(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    video_id = str(uuid4())
    destination = UPLOAD_DIR / f"{video_id}{suffix}"
    total = 0
    try:
        with destination.open("wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(413, f"File exceeds the {MAX_UPLOAD_MB} MB limit.")
                buffer.write(chunk)
        metadata = await run_in_threadpool(probe_video, destination)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not read video: {exc}")
    record = {"id": video_id, "filename": Path(file.filename or "video").name[:150], "path": str(destination),
              "metadata": metadata, "status": "uploaded", "source_type": "upload", "clips": []}
    store.add_video(record)
    return public_video(record)


@app.post("/api/sources/inspect")
def inspect_source(payload: SourceRequest):
    try:
        return inspect_url(payload.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, str(exc))


def _run_import_job(job_id: str, url: str) -> None:
    video_id = str(uuid4())
    destination = UPLOAD_DIR / f"{video_id}.mp4"
    try:
        store.update_job(job_id, status="importing", progress=8, message="Checking the video link…")
        info = inspect_url(url)
        store.update_job(job_id, progress=15,
                         message=f"Downloading “{info['title'][:60]}”. Long videos can take several minutes…")
        source = download_video(url, destination)
        metadata = probe_video(source)
        record = {"id": video_id, "filename": info["title"], "path": str(source), "metadata": metadata,
                  "status": "downloaded", "source_type": info["provider"], "source_url": url, "clips": []}
        store.add_video(record)
        store.update_job(job_id, status="completed", progress=100, message="Source video imported.",
                         video_id=video_id, video=public_video(record))
    except Exception as exc:
        for leftover in UPLOAD_DIR.glob(f"{video_id}.*"):
            leftover.unlink(missing_ok=True)
        store.update_job(job_id, status="failed", error=str(exc), message="Import failed.")


@app.post("/api/sources/download")
def download_source(payload: SourceRequest):
    """Import a supported public source in the background (no auth/DRM bypass). Poll /api/jobs/{id}.

    This used to block one HTTP request for up to an hour, which hosting proxies cut off.
    """
    job = store.new_job({"id": str(uuid4()), "type": "import", "status": "queued", "progress": 0,
                         "message": "Waiting to start the import…", "clips": []})
    IMPORT_POOL.submit(_run_import_job, job["id"], payload.url)
    return {"job_id": job["id"], "status": "queued"}


# ---------------------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------------------
@app.get("/api/videos")
def list_videos():
    with store.lock:
        records = sorted(store.videos.values(), key=lambda v: v.get("created_at", 0), reverse=True)
        return [public_video(v) for v in records]


@app.get("/api/videos/{video_id}")
def get_video(video_id: str):
    record = store.videos.get(video_id)
    if not record:
        raise HTTPException(404, "Video not found.")
    return public_video(record)


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: str):
    record = store.videos.get(video_id)
    if not record:
        raise HTTPException(404, "Video not found.")
    if record.get("status") in ACTIVE_VIDEO_STATES:
        raise HTTPException(409, "This video is being processed. Wait for the job to finish first.")
    store.pop_video(video_id)
    _delete_video_files(record)
    return {"deleted": video_id}


@app.delete("/api/videos/{video_id}/clips/{clip_id}")
def delete_clip(video_id: str, clip_id: str):
    record = store.videos.get(video_id)
    clip = next((c for c in (record or {}).get("clips", []) if c["id"] == clip_id), None)
    if not record or not clip:
        raise HTTPException(404, "Clip not found.")
    _unlink_clip_files(clip)
    store.update_video(video_id, clips=[c for c in record["clips"] if c["id"] != clip_id])
    return {"deleted": clip_id}


@app.get("/api/videos/{video_id}/clips.zip")
def download_all_clips(video_id: str):
    record = store.videos.get(video_id)
    if not record:
        raise HTTPException(404, "Video not found.")
    clips = [c for c in record.get("clips", []) if (OUTPUT_DIR / c["filename"]).exists()]
    if not clips:
        raise HTTPException(404, "This video has no clips to download yet.")
    fd, tmp_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_STORED) as archive:  # MP4 is already compressed
        for i, clip in enumerate(sorted(clips, key=lambda c: c.get("created_at", 0)), 1):
            stem = f"{i:02d}-{_slug(clip.get('title'))}"
            archive.write(OUTPUT_DIR / clip["filename"], f"{stem}.mp4")
            srt = (OUTPUT_DIR / clip["filename"]).with_suffix(".srt")
            if srt.exists():
                archive.write(srt, f"{stem}.srt")
    return FileResponse(tmp_path, media_type="application/zip",
                        filename=f"{_slug(record.get('filename'), 'cliprush')}-clips.zip",
                        background=BackgroundTask(os.unlink, tmp_path))


# ---------------------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------------------
def _load_transcript(video_id: str, language: str | None):
    path = UPLOAD_DIR / f"{video_id}.transcript.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("language") == language and data.get("words"):
            return data["words"], data.get("segments", [])
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _save_transcript(video_id: str, language: str | None, words: list, segments: list) -> None:
    try:
        (UPLOAD_DIR / f"{video_id}.transcript.json").write_text(
            json.dumps({"language": language, "words": words, "segments": segments}), encoding="utf-8")
    except OSError:
        log.warning("Could not cache transcript for %s", video_id)


def _run_analysis_job(job_id: str, video_id: str, options: dict) -> None:
    record = store.videos.get(video_id)
    if not record:
        store.update_job(job_id, status="failed", error="Video not found.", message="Clip generation failed.")
        return
    source = Path(record["path"])
    duration = record["metadata"]["duration"]
    source_size = (record["metadata"].get("width"), record["metadata"].get("height"))
    try:
        if not os.getenv("GROQ_API_KEY"):
            raise RuntimeError("Add GROQ_API_KEY to your .env file before using AI clipping.")
        language = options.get("language")

        cached = _load_transcript(video_id, language)
        if cached:
            words, segments = cached
            store.update_job(job_id, status="transcribing", progress=50,
                             message="Reusing the saved transcript from your last run…")
        else:
            store.update_job(job_id, status="transcribing", progress=8, message="Groq Whisper is transcribing audio…")
            store.update_video(video_id, status="transcribing")
            words, segments = transcribe_video(
                source, language=language,
                progress=lambda f: store.update_job(job_id, progress=8 + int(42 * f),
                                                    message="Groq Whisper is transcribing audio…"))
            _save_transcript(video_id, language, words, segments)

        store.update_job(job_id, status="selecting", progress=55, message="Groq AI is selecting the best moments…")
        store.update_video(video_id, status="selecting_highlights")
        candidates = select_highlights(words, segments, duration, options["clip_count"], options["min_duration"],
                                       options["max_duration"], options["content_type"], options.get("guidance", ""))
        if not candidates:
            raise RuntimeError("Groq did not find any clips matching your duration settings. "
                               "Try a wider duration range, or a video with more speech.")

        store.update_video(video_id, status="rendering")
        clips, failures = [], []
        settings = {k: options[k] for k in ("aspect_ratio", "caption_style", "caption_position", "reframe",
                                            "quality", "show_hook")}
        for index, candidate in enumerate(candidates):
            store.update_job(job_id, status="rendering", progress=60 + int(38 * index / max(1, len(candidates))),
                             message=f"Rendering clip {index + 1} of {len(candidates)} with captions…")
            clip_id = str(uuid4())
            output_name = f"{video_id}_{clip_id}.mp4"
            try:
                render_ai_clip(source, OUTPUT_DIR / output_name, candidate["start"], candidate["end"],
                               options["aspect_ratio"], words, candidate.get("hook", ""), options["caption_style"],
                               reframe=options["reframe"], quality=options["quality"],
                               caption_position=options["caption_position"], show_hook=options["show_hook"],
                               source_size=source_size)
            except Exception as exc:  # keep the clips that did render
                log.warning("Clip %d failed to render: %s", index + 1, exc)
                failures.append(str(exc))
                (OUTPUT_DIR / output_name).unlink(missing_ok=True)
                continue
            clips.append({"id": clip_id, "filename": output_name, "url": f"/clips/{output_name}",
                          "srt_url": f"/clips/{Path(output_name).with_suffix('.srt').name}",
                          **candidate, "duration": round(candidate["end"] - candidate["start"], 2),
                          "settings": settings, "created_at": time.time()})
        if not clips:
            raise RuntimeError("All clips failed to render. " + (failures[0] if failures else ""))

        # New clips are added to the project; earlier runs stay available until deleted.
        existing = store.videos.get(video_id, {}).get("clips", [])
        store.update_video(video_id, status="processed", clips=existing + clips, transcript_words=len(words))
        note = f" ({len(failures)} clip(s) could not be rendered.)" if failures else ""
        store.update_job(job_id, status="completed", progress=100, message="Your clips are ready." + note,
                         clips=clips, transcript_words=len(words), ai_provider="Groq",
                         transcription_model=stt_model(), highlight_model=chat_model())
    except Exception as exc:
        log.warning("Analysis job %s failed: %s", job_id, exc)
        store.update_video(video_id, status="failed")
        store.update_job(job_id, status="failed", error=str(exc), message="Clip generation failed.")


@app.post("/api/videos/{video_id}/analyze")
def analyze_video(video_id: str, request: AnalyzeRequest):
    record = store.videos.get(video_id)
    if not record:
        raise HTTPException(404, "Video not found. It may have expired or the server was reset. Upload it again.")
    if request.max_duration < request.min_duration:
        raise HTTPException(400, "Maximum clip length must be greater than or equal to the minimum.")
    meta = record["metadata"]
    if meta.get("has_audio") is False:
        raise HTTPException(400, "This video has no audio track, so it cannot be transcribed. "
                                 "Upload a version that includes the original audio.")
    if meta["duration"] < request.min_duration:
        raise HTTPException(400, f"This video is only {meta['duration']:.0f}s long, which is shorter than the "
                                 f"minimum clip length ({request.min_duration:g}s). Lower the minimum duration.")
    if not os.getenv("GROQ_API_KEY"):
        raise HTTPException(503, "Add GROQ_API_KEY to your .env file before using AI clipping.")
    if record.get("status") in ACTIVE_VIDEO_STATES:
        raise HTTPException(409, "This video is already being processed.")

    job = store.new_job({"id": str(uuid4()), "type": "analyze", "video_id": video_id, "status": "queued",
                         "progress": 0, "clips": [],
                         "message": "Queued. Waiting for the worker…"})
    store.update_video(video_id, status="queued")
    ANALYSIS_POOL.submit(_run_analysis_job, job["id"], video_id, request.model_dump())
    return {"job_id": job["id"], "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = store.snapshot_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found. The server may have restarted.")
    return job


# ---------------------------------------------------------------------------------------
# Frontend (same origin, so Basic Auth also protects clip files)
# ---------------------------------------------------------------------------------------
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return {"app": "ClipRush AI", "version": VERSION, "docs": "/docs",
                "hint": "Build the UI with `cd frontend && npm run build`, or run `npm run dev`."}
