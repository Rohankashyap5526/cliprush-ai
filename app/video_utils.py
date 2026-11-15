import json
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np

def run_command(args: list[str]) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg/FFprobe was not found. Install FFmpeg and add its bin folder to PATH.") from exc
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1500:] or "Media command failed")
    return result

def probe_video(path: Path) -> dict:
    result = run_command([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,width,height",
        "-of", "json", str(path)
    ])
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("The uploaded file does not contain a video stream.")
    duration = float(data.get("format", {}).get("duration", 0))
    if duration <= 0:
        raise ValueError("Could not determine video duration.")
    return {
        "duration": duration,
        "width": int(video.get("width", 0)),
        "height": int(video.get("height", 0)),
        "size_bytes": int(data.get("format", {}).get("size", 0))
    }

def audio_energy_events(path: Path, duration: float) -> list[tuple[float, float]]:
    """Return 1-second windows whose RMS energy is unusually high."""
    import tempfile
    with tempfile.TemporaryDirectory() as temp_dir:
        wav_path = Path(temp_dir) / "audio.wav"
        try:
            run_command([
                "ffmpeg", "-y", "-i", str(path), "-vn", "-ac", "1",
                "-ar", "8000", "-t", str(duration), "-f", "wav", str(wav_path)
            ])
        except RuntimeError:
            # Silent/no-audio videos are valid inputs; visual detection can still run.
            return []
        with wave.open(str(wav_path), "rb") as wav:
            rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
            samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    if len(samples) < rate:
        return []
    window = rate
    count = len(samples) // window
    rms = np.array([
        np.sqrt(np.mean(samples[i*window:(i+1)*window] ** 2))
        for i in range(count)
    ])
    positive = rms[rms > 1]
    if len(positive) == 0:
        return []
    threshold = max(float(np.percentile(positive, 85)), float(np.mean(positive) * 1.35))
    return [(float(i), float(min(i + 1, duration))) for i, value in enumerate(rms) if value >= threshold]

def scene_change_events(path: Path, duration: float) -> list[tuple[float, float]]:
    """Approximate scene changes by comparing sampled frames at 1 fps."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("OpenCV could not open this video.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    frame_count = min(total, int(duration * fps))
    previous = None
    differences = []
    for second in range(max(1, int(duration))):
        cap.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        small = cv2.resize(frame, (160, 90))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        if previous is not None:
            diff = float(np.mean(cv2.absdiff(gray, previous)))
            differences.append((float(second), diff))
        previous = gray
    cap.release()
    if not differences:
        return []
    values = np.array([v for _, v in differences])
    threshold = max(float(np.percentile(values, 90)), float(np.mean(values) * 1.5))
    return [(t, min(t + 1, duration)) for t, v in differences if v >= threshold]

def build_candidates(events, duration, min_duration, max_duration, count):
    if not events:
        # Fallback: evenly spaced candidates when the video has no strong signals.
        if duration < min_duration:
            return []
        starts = np.linspace(0, max(0, duration - min_duration), min(count, max(1, int(duration // min_duration))))
        return [{"start": round(float(s), 2), "end": round(float(min(s + min_duration, duration)), 2),
                 "score": 0.1, "reason": "Fallback segment: no strong audio or scene-change signal"} for s in starts]

    centers = sorted((a + b) / 2 for a, b in events)
    # Merge nearby detections into a moment, then add context before/after.
    clusters = []
    for center in centers:
        if not clusters or center - clusters[-1][-1] > 8:
            clusters.append([center])
        else:
            clusters[-1].append(center)

    candidates = []
    for cluster in clusters:
        midpoint = float(np.mean(cluster))
        start = max(0.0, midpoint - min_duration * 0.45)
        end = min(duration, start + max_duration)
        if end - start < min_duration:
            start = max(0.0, end - min_duration)
        density = len(cluster)
        score = min(0.99, 0.25 + density * 0.12)
        candidates.append({
            "start": round(start, 2), "end": round(end, 2),
            "score": round(score, 2),
            "reason": f"Detected {density} audio/visual activity signal(s) near this moment"
        })
    candidates.sort(key=lambda x: x["score"], reverse=True)
    selected = []
    for candidate in candidates:
        if all(candidate["end"] <= item["start"] or candidate["start"] >= item["end"] for item in selected):
            selected.append(candidate)
        if len(selected) >= count:
            break
    return sorted(selected, key=lambda x: x["start"])

def render_clip(source: Path, output: Path, start: float, end: float, ratio: str):
    if ratio == "9:16":
        vf = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
    elif ratio == "1:1":
        vf = "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
    else:
        vf = "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720"
    run_command([
        "ffmpeg", "-y", "-ss", str(start), "-i", str(source),
        "-t", str(end - start), "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(output)
    ])


def _srt_time(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, rem = divmod(ms, 3600000); m, rem = divmod(rem, 60000); s, milli = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{milli:03}"


def build_srt(words: list[dict], start: float, end: float) -> str:
    """Build readable short caption cards from Groq's word timestamps."""
    selected = [w for w in words if w["end"] > start and w["start"] < end]
    rows, group = [], []
    for word in selected:
        group.append(word)
        text = " ".join(x["word"] for x in group)
        if len(group) >= 5 or len(text) >= 34 or word is selected[-1]:
            a = max(0.0, group[0]["start"] - start)
            b = min(end-start, max(a + 0.25, group[-1]["end"] - start))
            rows.append(f"{len(rows)+1}\n{_srt_time(a)} --> {_srt_time(b)}\n{text}\n")
            group = []
    return "\n".join(rows)


def render_ai_clip(source: Path, output: Path, start: float, end: float, ratio: str,
                   words: list[dict], hook: str = "", caption_style: str = "bold"):
    """Render vertical/square/landscape video with burned-in word-timed captions and a hook title."""
    import tempfile
    import shutil
    output.parent.mkdir(parents=True, exist_ok=True)
    if ratio == "9:16":
        vf = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
    elif ratio == "1:1":
        vf = "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
    else:
        vf = "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720"
    with tempfile.TemporaryDirectory(prefix="cr_render_") as temp:
        tempdir = Path(temp)
        (tempdir / "captions.srt").write_text(build_srt(words, start, end), encoding="utf-8-sig")
        # subtitles filter reads a short relative filename from this temporary working directory.
        styles = {
            "bold": "FontName=Arial,FontSize=24,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=130",
            "classic": "FontName=Arial,FontSize=21,Bold=0,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=110",
            "minimal": "FontName=Arial,FontSize=19,Bold=0,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=1,Shadow=0,Alignment=2,MarginV=90"
        }
        subtitle_filter = "subtitles=captions.srt:force_style='" + styles.get(caption_style, styles["bold"]) + "'"
        if hook.strip():
            safe_hook = hook.replace("'", "").replace(":", " ").replace("%", "")[:60]
            draw = f"drawtext=text='{safe_hook}':fontcolor=white:fontsize=42:borderw=3:bordercolor=black:x=(w-text_w)/2:y=h*0.12"
            vf = vf + "," + draw
        vf = vf + "," + subtitle_filter
        temp_out = tempdir / "rendered.mp4"
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-i", str(source), "-t", str(end-start),
               "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac",
               "-b:a", "128k", "-movflags", "+faststart", str(temp_out)]
        p = subprocess.run(cmd, cwd=tempdir, capture_output=True, text=True)
        if p.returncode:
            raise RuntimeError("Caption rendering failed: " + p.stderr[-1200:])
        shutil.copy2(temp_out, output)
