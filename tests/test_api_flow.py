"""End-to-end API test: real uploads, real ffmpeg rendering, Groq calls mocked."""
import base64
import io
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")

AUTH = {"Authorization": "Basic " + base64.b64encode(b"tester:s3cret-password").decode()}
WORDS = [{"word": f"word{i}", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(40)]  # 20 s of speech
SEGMENTS = [{"start": 0, "end": 20, "text": "some speech"}]


@pytest.fixture(scope="module")
def video_bytes(tmp_path_factory):
    out = tmp_path_factory.mktemp("media") / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=22",
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=22", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(out)], check=True)
    return out.read_bytes()


@pytest.fixture(scope="module")
def silent_bytes(tmp_path_factory):
    out = tmp_path_factory.mktemp("media") / "silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=5",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)], check=True)
    return out.read_bytes()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    calls = {"transcribe": 0}

    def fake_transcribe(source, language=None, progress=None):
        calls["transcribe"] += 1
        if progress:
            progress(1.0)
        return WORDS, SEGMENTS

    def fake_select(words, segments, duration, count, mn, mx, ctype, guidance=""):
        return [{"start": 2.0, "end": 12.0, "score": 91, "hook": "Wait for it", "title": "First: moment/one",
                 "reason": "test", "description": "desc", "hashtags": ["#a"]},
                {"start": 12.5, "end": 21.0, "score": 70, "hook": "", "title": "Second", "reason": "r",
                 "description": "", "hashtags": []}]

    monkeypatch.setattr(main, "transcribe_video", fake_transcribe)
    monkeypatch.setattr(main, "select_highlights", fake_select)
    c = TestClient(main.app, headers=AUTH)
    c.calls = calls
    return c


def wait_for(client, job_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.3)
    raise AssertionError("job did not finish")


def upload(client, data, name="clip.mp4"):
    r = client.post("/api/videos", files={"file": (name, io.BytesIO(data), "video/mp4")})
    assert r.status_code == 200, r.text
    return r.json()


def test_full_flow(client, video_bytes):
    video = upload(client, video_bytes)
    assert "path" not in video and video["metadata"]["has_audio"] is True
    vid = video["id"]

    opts = {"clip_count": 2, "min_duration": 5, "max_duration": 30, "aspect_ratio": "9:16",
            "caption_style": "karaoke", "reframe": "blur", "show_hook": True}
    started = client.post(f"/api/videos/{vid}/analyze", json=opts)
    assert started.status_code == 200
    job = wait_for(client, started.json()["job_id"])
    assert job["status"] == "completed", job
    assert len(job["clips"]) == 2 and job["progress"] == 100

    clip = job["clips"][0]
    mp4 = client.get(clip["url"])
    assert mp4.status_code == 200 and len(mp4.content) > 10_000
    assert client.get(clip["srt_url"]).status_code == 200
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,pix_fmt",
                            "-of", "csv=p=0", str(main.OUTPUT_DIR / clip["filename"])],
                           capture_output=True, text=True).stdout
    assert "720,1280,yuv420p" in probe

    # project is in the library with its clips
    lib = client.get("/api/videos").json()
    assert any(v["id"] == vid and len(v["clips"]) == 2 and v["status"] == "processed" for v in lib)

    # zip contains both clips (+ subtitles) with safe file names
    z = client.get(f"/api/videos/{vid}/clips.zip")
    assert z.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert sum(n.endswith(".mp4") for n in names) == 2 and sum(n.endswith(".srt") for n in names) == 2
    assert all("/" not in n for n in names)

    # a second run reuses the cached transcript (no second Groq transcription bill) and adds clips
    job2 = wait_for(client, client.post(f"/api/videos/{vid}/analyze", json={**opts, "caption_style": "bold"}).json()["job_id"])
    assert job2["status"] == "completed" and client.calls["transcribe"] == 1
    assert len(client.get(f"/api/videos/{vid}").json()["clips"]) == 4

    # delete one clip: file gone, others untouched
    assert client.delete(f"/api/videos/{vid}/clips/{clip['id']}").status_code == 200
    assert not (main.OUTPUT_DIR / clip["filename"]).exists()
    assert len(client.get(f"/api/videos/{vid}").json()["clips"]) == 3

    # delete project: every file removed
    remaining = [c["filename"] for c in client.get(f"/api/videos/{vid}").json()["clips"]]
    assert client.delete(f"/api/videos/{vid}").status_code == 200
    assert client.get(f"/api/videos/{vid}").status_code == 404
    assert not any((main.OUTPUT_DIR / f).exists() for f in remaining)
    assert not list(main.UPLOAD_DIR.glob(f"{vid}*"))


def test_validation_errors_are_clear(client, video_bytes, silent_bytes):
    vid = upload(client, video_bytes)["id"]
    assert client.post(f"/api/videos/{vid}/analyze", json={"min_duration": 40, "max_duration": 20}).status_code == 400
    r = client.post(f"/api/videos/{vid}/analyze", json={"min_duration": 60, "max_duration": 90})
    assert r.status_code == 400 and "shorter than the minimum" in r.json()["detail"]
    assert client.post("/api/videos/nope/analyze", json={}).status_code == 404
    assert client.post(f"/api/videos/{vid}/analyze", json={"caption_style": "comic-sans"}).status_code == 422

    silent = upload(client, silent_bytes, "silent.mp4")
    assert silent["metadata"]["has_audio"] is False
    r = client.post(f"/api/videos/{silent['id']}/analyze", json={"min_duration": 5, "max_duration": 10})
    assert r.status_code == 400 and "no audio" in r.json()["detail"]


def test_upload_rejections(client):
    r = client.post("/api/videos", files={"file": ("notes.txt", io.BytesIO(b"hi"), "text/plain")})
    assert r.status_code == 400
    before = set(main.UPLOAD_DIR.iterdir())
    r = client.post("/api/videos", files={"file": ("fake.mp4", io.BytesIO(b"not a video" * 200), "video/mp4")})
    assert r.status_code == 400
    assert set(main.UPLOAD_DIR.iterdir()) == before  # the rejected file was cleaned up


def test_upload_size_limit(client, monkeypatch, video_bytes):
    monkeypatch.setattr(main, "MAX_UPLOAD_MB", 0.01)  # ~10 KB
    before = set(main.UPLOAD_DIR.iterdir())
    r = client.post("/api/videos", files={"file": ("big.mp4", io.BytesIO(video_bytes), "video/mp4")})
    assert r.status_code == 413
    assert set(main.UPLOAD_DIR.iterdir()) == before  # partial file removed


def test_missing_groq_key_is_a_clean_503(client, video_bytes, monkeypatch):
    vid = upload(client, video_bytes)["id"]
    monkeypatch.delenv("GROQ_API_KEY")
    assert client.post(f"/api/videos/{vid}/analyze", json={"min_duration": 5, "max_duration": 10}).status_code == 503


def test_failed_job_reports_error_and_unblocks_video(client, video_bytes, monkeypatch):
    vid = upload(client, video_bytes)["id"]
    monkeypatch.setattr(main, "select_highlights", lambda *a, **k: [])
    job = wait_for(client, client.post(f"/api/videos/{vid}/analyze", json={"min_duration": 5, "max_duration": 10}).json()["job_id"])
    assert job["status"] == "failed" and "did not find any clips" in job["error"]
    assert client.get(f"/api/videos/{vid}").json()["status"] == "failed"
    # video is not stuck: it can be analyzed again
    monkeypatch.undo()
    assert client.post(f"/api/videos/{vid}/analyze", json={"min_duration": 5, "max_duration": 10}).status_code in (200, 503)


def test_one_bad_clip_does_not_lose_the_others(client, video_bytes, monkeypatch):
    vid = upload(client, video_bytes)["id"]
    real = main.render_ai_clip
    state = {"n": 0}

    def flaky(*a, **k):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("boom")
        return real(*a, **k)

    monkeypatch.setattr(main, "render_ai_clip", flaky)
    job = wait_for(client, client.post(f"/api/videos/{vid}/analyze", json={"min_duration": 5, "max_duration": 30}).json()["job_id"])
    assert job["status"] == "completed" and len(job["clips"]) == 1 and "could not be rendered" in job["message"]


def test_retention_cleanup_removes_only_expired(client, video_bytes, monkeypatch):
    old, fresh = upload(client, video_bytes)["id"], upload(client, video_bytes)["id"]
    main.store.update_video(old, created_at=time.time() - 3 * 24 * 3600)
    (main.OUTPUT_DIR / "orphan_clip.mp4").write_bytes(b"x")
    import os
    os.utime(main.OUTPUT_DIR / "orphan_clip.mp4", (1, 1))
    monkeypatch.setattr(main, "RETENTION_HOURS", 24)
    assert main.cleanup_expired() >= 1
    assert client.get(f"/api/videos/{old}").status_code == 404
    assert client.get(f"/api/videos/{fresh}").status_code == 200
    assert not (main.OUTPUT_DIR / "orphan_clip.mp4").exists()


def test_import_runs_as_a_background_job(client, video_bytes, monkeypatch):
    def fake_inspect(url):
        return {"title": "Some VOD", "uploader": "x", "duration": 22, "thumbnail": "", "provider": "youtube.com", "url": url}

    def fake_download(url, destination):
        dest = Path(destination)
        dest.write_bytes(video_bytes)
        return dest

    monkeypatch.setattr(main, "inspect_url", fake_inspect)
    monkeypatch.setattr(main, "download_video", fake_download)
    r = client.post("/api/sources/download", json={"url": "https://www.youtube.com/watch?v=abcdefghijk"})
    assert r.status_code == 200 and "job_id" in r.json()      # returns immediately, no hour-long request
    job = wait_for(client, r.json()["job_id"])
    assert job["status"] == "completed" and job["video"]["filename"] == "Some VOD" and "path" not in job["video"]

    monkeypatch.setattr(main, "download_video", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("HTTP 403")))
    bad = wait_for(client, client.post("/api/sources/download", json={"url": "https://youtu.be/abcdefghijk"}).json()["job_id"])
    assert bad["status"] == "failed" and "403" in bad["error"]
