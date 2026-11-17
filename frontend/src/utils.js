export function formatTime(seconds = 0) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}

export function formatBytes(bytes = 0) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function timeAgo(epochSeconds) {
  const diff = Math.max(0, Date.now() / 1000 - (epochSeconds || 0));
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return `${Math.floor(diff / 86400)} d ago`;
}

export const slug = (text, fallback = "clip") =>
  (text || "").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "").toLowerCase().slice(0, 50) || fallback;

export function socialCaption(clip) {
  return [clip.title, clip.description, (clip.hashtags || []).join(" ")].filter(Boolean).join("\n\n");
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { /* ignored */ }
    ta.remove();
    return ok;
  }
}

export const LIMITS = { minDuration: [5, 120], maxDuration: [10, 180] };

export const DEFAULT_OPTS = {
  content_type: "hybrid", clip_count: 5, aspect_ratio: "9:16", caption_style: "karaoke",
  caption_position: "bottom", reframe: "crop", quality: "standard", show_hook: true,
  min_duration: 15, max_duration: 45, language: "", guidance: "",
};

export const PRESETS = [
  { id: "shorts", label: "Shorts / Reels / TikTok", hint: "9:16 · 20–45 s · word highlight",
    set: { aspect_ratio: "9:16", min_duration: 20, max_duration: 45, caption_style: "karaoke", reframe: "crop", clip_count: 5, content_type: "hybrid" } },
  { id: "podcast", label: "Podcast clips", hint: "9:16 · 30–60 s · blurred fit",
    set: { aspect_ratio: "9:16", min_duration: 30, max_duration: 60, caption_style: "karaoke", reframe: "blur", clip_count: 5, content_type: "podcast" } },
  { id: "gaming", label: "Gaming moments", hint: "9:16 · 10–30 s · blurred fit",
    set: { aspect_ratio: "9:16", min_duration: 10, max_duration: 30, caption_style: "bold", reframe: "blur", clip_count: 8, content_type: "gaming" } },
  { id: "landscape", label: "YouTube highlights", hint: "16:9 · 30–90 s · classic",
    set: { aspect_ratio: "16:9", min_duration: 30, max_duration: 90, caption_style: "classic", reframe: "crop", clip_count: 5, content_type: "hybrid" } },
];

export const LANGUAGES = [
  ["", "Auto-detect"], ["en", "English"], ["hi", "Hindi"], ["pa", "Punjabi"], ["es", "Spanish"], ["fr", "French"],
  ["de", "German"], ["pt", "Portuguese"], ["ar", "Arabic"], ["id", "Indonesian"], ["ja", "Japanese"],
  ["ko", "Korean"], ["ru", "Russian"], ["tr", "Turkish"],
];

/** Returns a human-readable problem with the settings, or "" if they are fine. */
export function validateOpts(opts, video) {
  const min = Number(opts.min_duration), max = Number(opts.max_duration), count = Number(opts.clip_count);
  if (!Number.isFinite(min) || min < LIMITS.minDuration[0] || min > LIMITS.minDuration[1])
    return `Minimum clip length must be between ${LIMITS.minDuration[0]} and ${LIMITS.minDuration[1]} seconds.`;
  if (!Number.isFinite(max) || max < LIMITS.maxDuration[0] || max > LIMITS.maxDuration[1])
    return `Maximum clip length must be between ${LIMITS.maxDuration[0]} and ${LIMITS.maxDuration[1]} seconds.`;
  if (max < min) return "Maximum clip length can't be shorter than the minimum.";
  if (!Number.isInteger(count) || count < 1 || count > 20) return "Choose between 1 and 20 clips.";
  const duration = video?.metadata?.duration;
  if (duration && duration < min)
    return `This video is only ${Math.round(duration)} s long, shorter than your minimum clip length (${min} s). Lower the minimum.`;
  if (video?.metadata?.has_audio === false) return "This video has no audio track, so it can't be transcribed.";
  return "";
}

export function loadJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}
export function saveJSON(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode / quota */ }
}
