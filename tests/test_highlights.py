import json

import pytest

from app import groq_ai
from app.groq_ai import (_clean_tags, _parse_json, _transcript_lines, _windows, _WordIndex,
                         normalize_candidate, select_highlights)

# 120 s of speech, one word every 0.5 s, each 0.4 s long.
WORDS = [{"word": f"w{i}", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(240)]
INDEX = _WordIndex(WORDS)


def norm(start, end, **kw):
    return normalize_candidate({"start": start, "end": end, **kw}, INDEX, 120.0, 15, 45)


def test_snaps_to_word_boundaries():
    c = norm(10.2, 40.3)  # both timestamps fall inside words
    assert c["start"] == pytest.approx(10.0 - 0.12, abs=0.01)   # start of the word containing 10.2, with lead-in
    assert c["end"] == pytest.approx(40.4 + 0.2, abs=0.01)      # end of the word containing 40.3, with tail


def test_slightly_short_clip_is_extended_not_dropped():
    c = norm(10.0, 24.0)  # 14 s < 15 s minimum: the old code discarded this
    assert c is not None and 15 - 0.01 <= c["end"] - c["start"] <= 45


def test_overlong_clip_is_trimmed_to_limit():
    c = norm(5.0, 80.0)
    assert c is not None and c["end"] - c["start"] <= 45.01


@pytest.mark.parametrize("start,end", [(50, 40), (-5, -1), (200, 230)])
def test_garbage_ranges_rejected(start, end):
    assert norm(start, end) is None


def test_clip_cannot_run_past_end_of_video():
    c = norm(110, 140)
    assert c is None or c["end"] <= 120.01


def test_score_variants_and_tags():
    assert norm(10, 30, score="85")["score"] == 85
    assert norm(10, 30, score=85.7)["score"] == 85
    assert norm(10, 30, score=999)["score"] == 100
    assert norm(10, 30, score="junk")["score"] == 50
    assert _clean_tags(["#Fun", "fun", "big win!", "", "ok"]) == ["#Fun", "#bigwin", "#ok"]
    assert _clean_tags("a, b c") == ["#a", "#b", "#c"]
    assert _clean_tags(None) == []


def test_parse_json_handles_fences_and_prose():
    assert _parse_json('```json\n{"clips": []}\n```') == {"clips": []}
    assert _parse_json('Sure! {"clips": [{"start": 1}]} hope that helps') == {"clips": [{"start": 1}]}
    assert _parse_json('[{"start": 1}]') == {"clips": [{"start": 1}]}
    with pytest.raises(json.JSONDecodeError):
        _parse_json("no json here")


def test_long_transcripts_are_windowed_not_truncated():
    lines = [f"[{i}.0-{i + 1}.0] " + "x" * 100 for i in range(2000)]  # ~214k chars (> old 100k cap)
    windows = _windows(lines, max_chars=40_000)
    assert len(windows) >= 5
    assert sum(len(w) for w in windows) == len(lines)          # nothing dropped
    assert all(sum(len(l) + 1 for l in w) <= 40_000 + 120 for w in windows)


def test_word_fallback_groups_into_lines():
    lines = _transcript_lines(WORDS, [])
    assert 5 < len(lines) < 30  # ~10 s lines, not one per word (240)


def test_select_highlights_ranks_dedupes_and_spans_windows(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(groq_ai, "WINDOW_CHARS", 10)  # force several windows
    answers = iter([
        [{"start": 10, "end": 30, "score": 70, "title": "A"}, {"start": 12, "end": 31, "score": 95, "title": "dup of A"}],
        [{"start": 60, "end": 80, "score": 88, "title": "B"}],
        [{"start": 95, "end": 115, "score": 40, "title": "C"}],
    ])
    monkeypatch.setattr(groq_ai, "_ask_model", lambda *a, **k: next(answers))
    monkeypatch.setattr(groq_ai, "_windows", lambda lines, max_chars=0: [lines[:1], lines[1:2], lines[2:3]])
    segs = [{"start": i * 40, "end": i * 40 + 39, "text": f"seg {i}"} for i in range(3)]
    out = select_highlights(WORDS, segs, 120.0, 2, 15, 45, "podcast")
    assert [c["title"] for c in out] == ["dup of A", "B"]  # best-scoring non-overlapping, ordered by time


def test_all_windows_failing_raises_clear_error(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    def boom(*a, **k):
        raise ValueError("bad")
    monkeypatch.setattr(groq_ai, "_ask_model", boom)
    with pytest.raises(RuntimeError, match="invalid JSON"):
        select_highlights(WORDS, [{"start": 0, "end": 5, "text": "hi"}], 120.0, 3, 15, 45, "hybrid")
