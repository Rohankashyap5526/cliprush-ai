import json
import re
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
ALLOWED_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "youtu.be", "www.youtu.be"
}

def extract_video_id(raw_url: str) -> str:
    try:
        parsed = urlparse(raw_url.strip())
    except Exception as exc:
        raise ValueError("Invalid URL.") from exc

    if parsed.scheme not in ("http", "https") or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("Enter a valid youtube.com or youtu.be video URL.")

    host = parsed.hostname
    video_id = None
    if host.endswith("youtu.be"):
        video_id = parsed.path.strip("/").split("/")[0]
    else:
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.path.rstrip("/") == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif len(parts) >= 2 and parts[0] in {"shorts", "live", "embed", "v"}:
            video_id = parts[1]

    if not video_id or not VIDEO_ID_RE.fullmatch(video_id):
        raise ValueError("Could not find a valid YouTube video ID in this URL.")
    return video_id

def inspect_youtube_url(raw_url: str) -> dict:
    video_id = extract_video_id(raw_url)
    endpoint = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    request = Request(endpoint, headers={"User-Agent": "ClipRushAI/0.2 (video metadata lookup)"})
    try:
        with urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise ValueError("YouTube did not return metadata. The video may be private, unavailable, age-restricted or embedding-restricted.") from exc
        raise RuntimeError(f"YouTube metadata request failed (HTTP {exc.code}).") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("Could not reach YouTube to retrieve metadata. Check your internet connection and try again.") from exc
    except Exception as exc:
        raise RuntimeError("YouTube returned an unexpected metadata response.") from exc

    return {
        "video_id": video_id,
        "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
        "title": data.get("title"),
        "author_name": data.get("author_name"),
        "author_url": data.get("author_url"),
        "thumbnail_url": data.get("thumbnail_url"),
        "embed_url": f"https://www.youtube-nocookie.com/embed/{video_id}",
        "provider": data.get("provider_name", "YouTube"),
        "processing_status": "authorized_source_required",
        "message": (
            "Metadata and preview are available. ClipRush does not download YouTube media. "
            "To process this video, upload a copy you own or are authorized to use, or provide "
            "a media source you are legally and contractually permitted to process."
        )
    }
