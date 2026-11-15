import pytest
from app.downloader import validate_video_url
from app.video_utils import build_srt

@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=abcdefghijk",
    "https://youtu.be/abcdefghijk",
    "https://www.twitch.tv/videos/123456",
    "https://kick.com/channel/video/123",
])
def test_supported_video_domains(url):
    assert validate_video_url(url) == url

@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "http://127.0.0.1/video", "https://youtube.com.evil.test/video",
    "https://user:pass@youtube.com/watch?v=abcdefghijk", "ftp://youtube.com/video",
])
def test_rejects_unsafe_or_unsupported_urls(url):
    with pytest.raises(ValueError):
        validate_video_url(url)

def test_build_srt_uses_clip_relative_word_timestamps():
    words = [
        {"word": "Hello", "start": 10.0, "end": 10.3},
        {"word": "there", "start": 10.3, "end": 10.8},
        {"word": "creator", "start": 10.8, "end": 11.2},
    ]
    srt = build_srt(words, 10.0, 12.0)
    assert "00:00:00,000 --> 00:00:01,200" in srt
    assert "Hello there creator" in srt


def test_audio_stream_probe_detects_missing_audio(monkeypatch, tmp_path):
    import subprocess
    from app.groq_ai import _has_audio_stream

    class Result:
        returncode = 0
        stdout = '{"streams": []}'

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Result())
    assert _has_audio_stream(tmp_path / "silent-video.mp4") is False


def test_audio_stream_probe_detects_audio(monkeypatch, tmp_path):
    import subprocess
    from app.groq_ai import _has_audio_stream

    class Result:
        returncode = 0
        stdout = '{"streams": [{"codec_type": "audio", "codec_name": "aac"}]}'

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Result())
    assert _has_audio_stream(tmp_path / "video-with-audio.mp4") is True
