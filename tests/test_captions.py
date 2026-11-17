from app.video_utils import build_ass, build_srt, group_words, output_size

WORDS = [{"word": w, "start": 10 + i * 0.5, "end": 10 + i * 0.5 + 0.4}
         for i, w in enumerate("Stop chasing every trend. Focus on one thing and win".split())]


def test_output_sizes():
    assert output_size("9:16") == (720, 1280)
    assert output_size("9:16", "high") == (1080, 1920)
    assert output_size("16:9") == (1280, 720)
    assert output_size("1:1") == (720, 720)


def test_groups_break_on_sentence_end_and_limits():
    cards = group_words(WORDS, 10, 20, max_words=5, max_chars=34)
    assert [" ".join(w for w, _ in c["words"]) for c in cards][0] == "Stop chasing every trend."
    assert all(len(c["words"]) <= 5 for c in cards)


def test_group_times_are_clip_relative_and_clamped():
    cards = group_words(WORDS, 10, 12, max_words=3)
    assert cards[0]["start"] == 0.0
    assert all(0 <= c["start"] < c["end"] <= 2.0 for c in cards)


def test_srt_still_matches_original_behaviour():
    words = [{"word": "Hello", "start": 10.0, "end": 10.3}, {"word": "there", "start": 10.3, "end": 10.8},
             {"word": "creator", "start": 10.8, "end": 11.2}]
    srt = build_srt(words, 10.0, 12.0)
    assert "00:00:00,000 --> 00:00:01,200" in srt and "Hello there creator" in srt


def test_ass_playres_matches_output_so_fonts_are_real_pixels():
    ass = build_ass(WORDS, 10, 18, "9:16", "standard", "bold", hook="Stop chasing trends")
    assert "PlayResX: 720" in ass and "PlayResY: 1280" in ass
    caption_style = next(l for l in ass.splitlines() if l.startswith("Style: Caption"))
    size = int(caption_style.split(",")[2])
    assert 40 <= size <= 80  # sane pixel size, not a 288px-canvas value scaled up to ~100+


def test_karaoke_emits_one_event_per_word_with_highlight():
    ass = build_ass(WORDS, 10, 18, "9:16", "standard", "karaoke")
    events = [l for l in ass.splitlines() if l.startswith("Dialogue")]
    assert events and all("\\c&H0000E5FF&" in e for e in events)
    assert "STOP" in events[0]  # uppercase style


def test_hook_only_in_first_seconds_and_escaped():
    ass = build_ass(WORDS, 10, 18, "9:16", "standard", "none", hook="Big {win}: 100%")
    hooks = [l for l in ass.splitlines() if ",Hook," in l]
    assert len(hooks) == 1 and hooks[0].startswith("Dialogue: 1,0:00:00.00,0:00:03.50")
    assert "{win}" not in hooks[0] and "100%" in hooks[0]


def test_nothing_to_draw_returns_none():
    assert build_ass(WORDS, 10, 18, "9:16", "standard", "none", hook="") is None
