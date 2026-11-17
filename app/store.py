"""Small JSON-file backed registry for videos and jobs.

Previously everything lived in process memory, so any restart orphaned uploaded files and
finished clips. This keeps the same simple model but persists it to DATA_DIR/state.json
(atomic write) so projects survive restarts whenever the data directory itself survives.
"""
import json
import logging
import os
import threading
import time
from pathlib import Path

log = logging.getLogger("cliprush.store")

ACTIVE_VIDEO_STATES = {"queued", "transcribing", "selecting_highlights", "rendering", "importing"}
MAX_JOBS_KEPT = 60


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.videos: dict[str, dict] = {}
        self.jobs: dict[str, dict] = {}
        self._load()

    # ---- persistence -------------------------------------------------------------------
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not read %s (%s); starting with an empty registry.", self.path, exc)
            return
        self.videos = {k: v for k, v in data.get("videos", {}).items() if Path(v.get("path", "")).exists()}
        self.jobs = data.get("jobs", {})
        # Anything that was mid-flight when the process died can never finish now.
        for job in self.jobs.values():
            if job.get("status") not in ("completed", "failed"):
                job.update(status="failed", error="The server restarted while this job was running. Please try again.",
                           message="Interrupted by a server restart.")
        for video in self.videos.values():
            if video.get("status") in ACTIVE_VIDEO_STATES:
                video["status"] = "failed"

    def save(self) -> None:
        with self.lock:
            self._trim_jobs()
            payload = json.dumps({"videos": self.videos, "jobs": self.jobs}, ensure_ascii=False)
            tmp = self.path.with_suffix(".tmp")
            try:
                tmp.write_text(payload, encoding="utf-8")
                os.replace(tmp, self.path)
            except OSError as exc:  # never let a bookkeeping failure kill a render
                log.warning("Could not persist state: %s", exc)

    def _trim_jobs(self) -> None:
        if len(self.jobs) <= MAX_JOBS_KEPT:
            return
        ordered = sorted(self.jobs.values(), key=lambda j: j.get("created_at", 0))
        for job in ordered[: len(self.jobs) - MAX_JOBS_KEPT]:
            if job.get("status") in ("completed", "failed"):
                self.jobs.pop(job["id"], None)

    # ---- videos ------------------------------------------------------------------------
    def add_video(self, record: dict) -> None:
        record.setdefault("created_at", time.time())
        with self.lock:
            self.videos[record["id"]] = record
            self.save()

    def update_video(self, video_id: str, **fields) -> None:
        with self.lock:
            if video_id in self.videos:
                self.videos[video_id].update(fields)
                self.save()

    def pop_video(self, video_id: str) -> dict | None:
        with self.lock:
            record = self.videos.pop(video_id, None)
            if record:
                self.save()
            return record

    # ---- jobs --------------------------------------------------------------------------
    def new_job(self, job: dict) -> dict:
        job.setdefault("created_at", time.time())
        with self.lock:
            self.jobs[job["id"]] = job
            self.save()
        return job

    def update_job(self, job_id: str, **fields) -> None:
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(fields)
                self.save()

    def snapshot_job(self, job_id: str) -> dict | None:
        with self.lock:
            job = self.jobs.get(job_id)
            return json.loads(json.dumps(job)) if job else None


def public_video(record: dict) -> dict:
    """Strip server-side filesystem paths before sending a record to the browser."""
    return {k: v for k, v in record.items() if k != "path"}
