"""FFmpeg helpers: probing, caption generation (SRT + ASS) and clip rendering."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

CAPTION_STYLES = ("bold", "karaoke", "classic", "minimal", "none")


def run_command(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg/FFprobe was not found. Install FFmpeg and add its bin folder to PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("A media command timed out.") from exc
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "Media command failed")[-1500:])
    return result


def probe_video(path: Path) -> dict:
    result = run_command([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,width,height,duration",
        "-of", "json", str(path),
    ], timeout=60)
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("The uploaded file does not contain a video stream.")

    def _num(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    # Some WebM/MKV files report no container duration; fall back to the stream's own.
    duration = _num(data.get("format", {}).get("duration")) or _num(video.get("duration"))
    if duration <= 0:
        raise ValueError("Could not determine video duration.")
    return {
        "duration": duration,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "size_bytes": int(_num(data.get("format", {}).get("size"))),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


# --------------------------------------------------------------------------------------
# Output geometry
# --------------------------------------------------------------------------------------
def output_size(ratio: str, quality: str = "standard") -> tuple[int, int]:
    """(width, height). `standard` keeps the short side at 720px (fast on small servers)."""
    short = 1080 if quality == "high" else 720
    long_side = round(short * 16 / 9 / 2) * 2
    if ratio == "9:16":
        return short, long_side
    if ratio == "1:1":
        return short, short
    return long_side, short


# --------------------------------------------------------------------------------------
# Captions
# --------------------------------------------------------------------------------------
def group_words(words: list[dict], start: float, end: float, max_words: int = 5,
                max_chars: int = 34) -> list[dict]:
    """Split the words that fall inside [start, end] into short caption cards (clip-relative times)."""
    selected = [w for w in words if w.get("word") and w["end"] > start and w["start"] < end]
    cards: list[dict] = []
    group: list[dict] = []

    def flush():
        if not group:
            return
        a = max(0.0, group[0]["start"] - start)
        b = min(end - start, max(a + 0.25, group[-1]["end"] - start))
        cards.append({
            "start": a, "end": b,
            "words": [(x["word"], max(0.0, x["start"] - start)) for x in group],
        })
        group.clear()

    for word in selected:
        group.append(word)
        text_len = len(" ".join(x["word"] for x in group))
        if len(group) >= max_words or text_len >= max_chars or word["word"][-1] in ".?!":
            flush()
    flush()
    return cards


def _srt_time(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, milli = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{milli:03}"


def build_srt(words: list[dict], start: float, end: float) -> str:
    """Readable short caption cards from word timestamps, relative to the clip start."""
    rows = []
    for i, card in enumerate(group_words(words, start, end), 1):
        text = " ".join(w for w, _ in card["words"])
        rows.append(f"{i}\n{_srt_time(card['start'])} --> {_srt_time(card['end'])}\n{text}\n")
    return "\n".join(rows)


def _ass_time(seconds: float) -> str:
    cs = max(0, int(round(seconds * 100)))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02}:{s:02}.{c:02}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


# &HAABBGGRR colours
WHITE, BLACK, YELLOW = "&H00FFFFFF", "&H00000000", "&H0000E5FF"

# font scale (relative to the base size), outline as a fraction of the font size,
# uppercase?, highlight the active word?
_STYLE_SPECS = {
    "bold":    {"scale": 1.00, "outline": 0.085, "upper": True,  "highlight": False},
    "karaoke": {"scale": 1.00, "outline": 0.085, "upper": True,  "highlight": True},
    "classic": {"scale": 0.82, "outline": 0.060, "upper": False, "highlight": False},
    "minimal": {"scale": 0.70, "outline": 0.045, "upper": False, "highlight": False},
}
_BASE_FONT = {"9:16": 0.088, "1:1": 0.068, "16:9": 0.062}      # fraction of the short side
_BOTTOM_MARGIN = {"9:16": 0.20, "1:1": 0.09, "16:9": 0.08}      # fraction of height (clears platform UI)
_HOOK_SECONDS = 3.5
FONT_NAME = "Liberation Sans"  # installed in the Docker image; fontconfig falls back elsewhere


def build_ass(words: list[dict], start: float, end: float, ratio: str, quality: str,
              caption_style: str = "bold", caption_position: str = "bottom",
              hook: str = "") -> str | None:
    """Return ASS subtitle text (captions + optional hook title), or None if there is nothing to draw.

    The script's PlayRes equals the output size, so font sizes are real pixels. (Plain SRT through
    ffmpeg's `subtitles` filter is laid out on a 288px-tall canvas, which made the old FontSize=24 huge.)
    """
    width, height = output_size(ratio, quality)
    short = min(width, height)
    spec = _STYLE_SPECS.get(caption_style)
    duration = end - start

    caption_font = int(short * _BASE_FONT[ratio] * (spec["scale"] if spec else 1))
    outline = max(1, int(caption_font * (spec["outline"] if spec else 0.06)))
    if caption_position == "middle":
        cap_align, cap_margin = 5, 0
    else:
        cap_align, cap_margin = 2, int(height * _BOTTOM_MARGIN[ratio])
    side = int(width * 0.07)

    hook_font = int(short * _BASE_FONT[ratio] * 0.78)
    hook_margin = int(height * (0.09 if ratio == "9:16" else 0.06))

    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Caption,{FONT_NAME},{caption_font},{WHITE},{WHITE},{BLACK},&H64000000,"
        f"{-1 if caption_style in ('bold', 'karaoke') else 0},0,0,0,100,100,0,0,1,{outline},0,"
        f"{cap_align},{side},{side},{cap_margin},1\n"
        # BorderStyle 3 = opaque box drawn in OutlineColour: dark text on a yellow banner.
        f"Style: Hook,{FONT_NAME},{hook_font},{BLACK},{BLACK},{YELLOW},&H00000000,-1,0,0,0,100,100,0,0,3,"
        f"{max(6, hook_font // 4)},0,8,{side},{side},{hook_margin},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events: list[str] = []
    if spec:  # captions enabled
        is_vertical = ratio == "9:16"
        cards = group_words(words, start, end, max_words=3 if is_vertical else 6,
                            max_chars=20 if is_vertical else 38)
        for card in cards:
            tokens = [_ass_escape(w.upper() if spec["upper"] else w) for w, _ in card["words"]]
            if spec["highlight"]:
                times = [t for _, t in card["words"]]
                for i in range(len(tokens)):
                    t0 = card["start"] if i == 0 else times[i]
                    t1 = times[i + 1] if i + 1 < len(tokens) else card["end"]
                    t0, t1 = max(0.0, t0), min(duration, max(t1, t0 + 0.05))
                    text = " ".join(f"{{\\c{YELLOW}&}}{tok}{{\\r}}" if j == i else tok
                                    for j, tok in enumerate(tokens))
                    events.append(f"Dialogue: 0,{_ass_time(t0)},{_ass_time(t1)},Caption,,0,0,0,,{text}")
            else:
                events.append(f"Dialogue: 0,{_ass_time(card['start'])},{_ass_time(card['end'])},Caption,,0,0,0,,"
                              f"{' '.join(tokens)}")
    if hook.strip():
        events.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(min(duration, _HOOK_SECONDS))},Hook,,0,0,0,,"
                      f"{_ass_escape(hook)[:60]}")
    return header + "\n".join(events) + "\n" if events else None


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------
def _similar_aspect(source: tuple[int, int] | None, target: tuple[int, int]) -> bool:
    if not source or not source[0] or not source[1]:
        return False
    return abs(source[0] / source[1] - target[0] / target[1]) < 0.03


def render_ai_clip(source: Path, output: Path, start: float, end: float, ratio: str,
                   words: list[dict], hook: str = "", caption_style: str = "bold", *,
                   reframe: str = "crop", quality: str = "standard", caption_position: str = "bottom",
                   show_hook: bool = True, source_size: tuple[int, int] | None = None) -> Path | None:
    """Render one clip with burned-in captions. Returns the path of the side-car .srt (if any)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = output_size(ratio, quality)

    # Only blur-fit when the source actually has a different shape than the target.
    use_blur = reframe == "blur" and not _similar_aspect(source_size, (width, height))
    if use_blur:
        bw, bh = (width // 8) * 2, (height // 8) * 2  # blur a quarter-size copy: much cheaper, same look
        base = (
            f"[0:v]split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},boxblur=6:2,"
            f"scale={width}:{height},eq=brightness=-0.06[bg];"
            f"[fgsrc]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]"
        )
    else:
        base = (f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1[base]")

    ass = build_ass(words, start, end, ratio, quality,
                    caption_style=caption_style if caption_style in _STYLE_SPECS else "none",
                    caption_position=caption_position, hook=hook if show_hook else "")
    graph = base + (";[base]ass=captions.ass[v]" if ass else ";[base]null[v]")

    with tempfile.TemporaryDirectory(prefix="cr_render_") as temp:
        tempdir = Path(temp)
        if ass:
            (tempdir / "captions.ass").write_text(ass, encoding="utf-8")
        temp_out = tempdir / "rendered.mp4"
        cmd = [
            "ffmpeg", "-y", "-nostdin", "-v", "error",
            "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{end - start:.3f}",
            "-filter_complex", graph, "-map", "[v]", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-profile:v", "high",  # yuv420p keeps clips playable on phones/QuickTime
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(temp_out),
        ]
        # cwd=tempdir lets the ass filter use a short relative path (avoids quoting/escaping problems).
        try:
            p = subprocess.run(cmd, cwd=tempdir, capture_output=True, text=True, timeout=3600)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Clip rendering timed out.") from exc
        if p.returncode:
            raise RuntimeError("Clip rendering failed: " + (p.stderr or "")[-1200:])
        shutil.copy2(temp_out, output)

    srt = build_srt(words, start, end)
    if not srt:
        return None
    srt_path = output.with_suffix(".srt")
    srt_path.write_text(srt, encoding="utf-8")
    return srt_path
