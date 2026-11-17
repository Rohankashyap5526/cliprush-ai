"""URL ingestion via yt-dlp for supported public sources; no cookies, DRM, or access-control bypasses."""
from pathlib import Path
from urllib.parse import urlparse
import subprocess
import json

from .config import MAX_UPLOAD_MB

ALLOWED = {"youtube.com", "youtu.be", "twitch.tv", "kick.com"}

def validate_video_url(url: str):
    try:
        parsed = urlparse((url or "").strip())
    except ValueError as exc:
        raise ValueError("Enter a valid video URL.") from exc
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not any(host == d or host.endswith("." + d) for d in ALLOWED):
        raise ValueError("Supported URL sources: YouTube, Twitch and Kick.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not accepted.")
    return parsed.geturl()

def inspect_url(url: str):
    url = validate_video_url(url)
    try:
        p = subprocess.run(["yt-dlp", "--no-warnings", "--no-playlist", "--dump-single-json", "--skip-download", url],
                           capture_output=True, text=True, timeout=45)
    except FileNotFoundError as exc:
        raise RuntimeError("yt-dlp is not installed. Install dependencies and restart ClipRush.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("The video platform took too long to respond. Try again in a moment.") from exc
    if p.returncode:
        raise RuntimeError(p.stderr[-900:] or "The source could not be inspected.")
    try:
        info = json.loads(p.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The video platform returned unreadable metadata.") from exc
    if info.get("_type") in {"playlist", "multi_video"}:
        raise ValueError("Please paste a single video or VOD URL, not a channel or playlist.")
    if info.get("is_live"):
        raise ValueError("This stream is still live. Import it after it has ended and the VOD is available.")
    return {"title": info.get("title") or "Untitled video", "uploader": info.get("uploader") or info.get("channel") or "",
            "duration": float(info.get("duration") or 0), "thumbnail": info.get("thumbnail") or "",
            "provider": urlparse(url).hostname, "url": url}

def _contains_video_stream(path: Path) -> bool:
    try:
        p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=codec_type,width,height", "-of", "json", str(path)],
                           capture_output=True, text=True, timeout=30)
        return p.returncode == 0 and bool(json.loads(p.stdout).get("streams"))
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return False


def download_video(url: str, destination: Path):
    url = validate_video_url(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    template = str(destination.with_suffix(".%(ext)s"))
    try:
        p = subprocess.run(["yt-dlp", "--no-warnings", "--no-playlist", "--no-progress",
                            "--no-write-thumbnail", "--no-write-info-json", "--no-write-subs", "--no-write-auto-subs",
                            "--no-part", "--force-ipv4", "--extractor-retries", "3", "--fragment-retries", "3",
                            "--retry-sleep", "fragment:2", "-f",
                            "bv*[height<=1080]+ba/b[height<=1080]", "--merge-output-format", "mkv",
                            "--max-filesize", f"{MAX_UPLOAD_MB}M", "-o", template, url], capture_output=True, text=True, timeout=3600)
    except FileNotFoundError as exc:
        raise RuntimeError("yt-dlp is not installed. Install dependencies and restart ClipRush.") from exc
    if p.returncode:
        detail = p.stderr[-1200:] or "No downloadable media was returned."
        if "403" in detail or "Forbidden" in detail:
            raise RuntimeError(
                "The video platform/CDN returned HTTP 403 and refused the media download. "
                "Update yt-dlp (py -m pip install -U yt-dlp), retry later, or upload the video file directly. "
                "Some public URLs cannot be downloaded by the server; ClipRush does not bypass platform access controls. "
                + detail
            )
        raise RuntimeError("Source download failed: " + detail)
    outputs = sorted(destination.parent.glob(destination.stem + ".*"), key=lambda x: x.stat().st_size, reverse=True)
    outputs = [x for x in outputs if x.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}]
    video_outputs = [x for x in outputs if _contains_video_stream(x)]
    if not video_outputs:
        for item in outputs:
            item.unlink(missing_ok=True)
        raise RuntimeError(
            "yt-dlp did not produce a playable video stream (it may have returned an audio-only or thumbnail file). "
            "Update yt-dlp and retry, or upload a local MP4/MOV/WebM video."
        )
    final = destination.with_suffix(video_outputs[0].suffix.lower())
    if video_outputs[0] != final:
        video_outputs[0].replace(final)
    return final
