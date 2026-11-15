import pytest
from app.youtube import extract_video_id

@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=abcdefghijk", "abcdefghijk"),
    ("https://youtu.be/abcdefghijk", "abcdefghijk"),
    ("https://www.youtube.com/shorts/abcdefghijk", "abcdefghijk"),
    ("https://www.youtube.com/live/abcdefghijk", "abcdefghijk"),
    ("https://www.youtube.com/embed/abcdefghijk", "abcdefghijk"),
])
def test_valid_youtube_urls(url, expected):
    assert extract_video_id(url) == expected

@pytest.mark.parametrize("url", [
    "https://example.com/watch?v=abcdefghijk",
    "javascript:alert(1)",
    "https://www.youtube.com/watch?v=bad",
    "https://www.youtube.com/",
])
def test_reject_invalid_urls(url):
    with pytest.raises(ValueError):
        extract_video_id(url)
