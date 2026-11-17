import { useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine, Check, CheckCircle2, ChevronDown, Clock3, Copy, FileText, LoaderCircle, Trash2, X,
} from "lucide-react";
import { apiUrl } from "./api";
import { copyText, formatTime, slug, socialCaption } from "./utils";

export function Select({ id, label, value, onChange, children, hint }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="select-wrap">
        <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>{children}</select>
        <ChevronDown size={15} aria-hidden="true" />
      </div>
      {hint && <small className="field-hint">{hint}</small>}
    </div>
  );
}

export function Toggle({ id, label, checked, onChange, hint }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <button id={id} type="button" role="switch" aria-checked={checked}
        className={`switch ${checked ? "on" : ""}`} onClick={() => onChange(!checked)}>
        <span className="switch-knob" />
        <span className="switch-label">{checked ? "On" : "Off"}</span>
      </button>
      {hint && <small className="field-hint">{hint}</small>}
    </div>
  );
}

const ANALYZE_STEPS = [
  ["queued", "Queued"], ["transcribing", "Transcribing"], ["selecting", "Finding highlights"], ["rendering", "Rendering clips"],
];

export function JobProgress({ job }) {
  if (!job) return null;
  const isAnalyze = job.kind === "analyze";
  const stage = Math.max(0, ANALYZE_STEPS.findIndex(([k]) => k === job.status));
  const pct = Math.max(3, Math.min(100, Math.round(job.progress || 0)));
  return (
    <div className="job-progress" role="status" aria-live="polite">
      {isAnalyze && (
        <ol className="job-steps">
          {ANALYZE_STEPS.map(([key, label], i) => (
            <li key={key} className={i < stage ? "done" : i === stage ? "current" : ""}>
              <span>{i < stage ? <Check size={12} /> : i + 1}</span>{label}
            </li>
          ))}
        </ol>
      )}
      <div className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
        <div className="bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <p><LoaderCircle size={14} className="spin" /> {job.message || "Working…"} <b>{pct}%</b></p>
      <small>You can leave this page open in the background. If you reload, ClipRush picks the job back up.</small>
    </div>
  );
}

export function Dropzone({ file, onFile, maxMb, disabled }) {
  const input = useRef(null);
  const [over, setOver] = useState(false);
  const pick = () => !disabled && input.current?.click();
  return (
    <div
      className={`dropzone ${file ? "has-file" : ""} ${over ? "is-over" : ""}`}
      role="button" tabIndex={0} aria-label="Choose a video file to upload"
      onClick={pick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } }}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f && !disabled) onFile(f); }}
    >
      <input ref={input} type="file" accept="video/*,.mkv,.mov,.mp4,.webm,.avi,.m4v" hidden
        onChange={(e) => { onFile(e.target.files?.[0] || null); e.target.value = ""; }} />
      <div className="upload-symbol"><CloudIcon /></div>
      {file ? (
        <>
          <b>{file.name}</b>
          <small>{(file.size / 1024 / 1024).toFixed(1)} MB · ready to upload</small>
          <button type="button" className="text-btn" disabled={disabled}
            onClick={(e) => { e.stopPropagation(); onFile(null); }}>Choose a different file</button>
        </>
      ) : (
        <>
          <b>Drop your video here, or <em>browse files</em></b>
          <small>MP4, MOV, MKV, WebM, AVI, M4V · up to {maxMb ? `${maxMb} MB` : "the server limit"}</small>
        </>
      )}
    </div>
  );
}

function CloudIcon() {
  return (
    <svg width="25" height="25" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 13v8" /><path d="m8 17 4-4 4 4" /><path d="M20 17.6A5 5 0 0 0 18 8h-1.3A8 8 0 1 0 4 16.3" />
    </svg>
  );
}

export function ClipCard({ clip, index, onDelete, notify }) {
  const [copied, setCopied] = useState(false);
  const score = Math.round(clip.score ?? 0); // 0–100 straight from the model
  const tone = score >= 80 ? "hot" : score >= 60 ? "good" : "ok";
  const fileName = `${slug(clip.title)}.mp4`;

  async function copy() {
    const ok = await copyText(socialCaption(clip));
    if (ok) { setCopied(true); notify("Caption copied. Paste it into your post."); setTimeout(() => setCopied(false), 2000); }
    else notify("Couldn't copy automatically. Select the text and copy it manually.", "error");
  }

  return (
    <article className="clip-card">
      <div className="clip-preview">
        <video src={apiUrl(clip.url)} controls preload="metadata" playsInline aria-label={`Preview of ${clip.title}`} />
        <span className="clip-index">CLIP {String(index + 1).padStart(2, "0")}</span>
        <span className={`score-badge ${tone}`} title="AI score for how well this moment should work as a short">
          {score}<small>/100</small>
        </span>
      </div>
      <div className="clip-info">
        <div className="clip-title-row"><b title={clip.title}>{clip.title || `Highlight ${index + 1}`}</b></div>
        {clip.hook && <p className="clip-hook">“{clip.hook}”</p>}
        <p className="clip-time"><Clock3 size={12} /> {formatTime(clip.start)} – {formatTime(clip.end)} · {Math.round(clip.duration)} s</p>
        {clip.reason && <small className="clip-reason">{clip.reason}</small>}
        {(clip.description || clip.hashtags?.length > 0) && (
          <div className="clip-caption">
            {clip.description && <span>{clip.description}</span>}
            {clip.hashtags?.length > 0 && <em>{clip.hashtags.join(" ")}</em>}
          </div>
        )}
        <div className="clip-actions">
          <a className="download-btn" href={apiUrl(clip.url)} download={fileName}><ArrowDownToLine size={15} /> Download MP4</a>
          <button type="button" className="icon-action" onClick={copy} aria-label="Copy title, description and hashtags" title="Copy caption">
            {copied ? <CheckCircle2 size={16} /> : <Copy size={16} />}
          </button>
          {clip.srt_url && (
            <a className="icon-action" href={apiUrl(clip.srt_url)} download={fileName.replace(/\.mp4$/, ".srt")}
              aria-label="Download subtitles (.srt)" title="Download subtitles (.srt)"><FileText size={16} /></a>
          )}
          <button type="button" className="icon-action danger" onClick={() => onDelete(clip)} aria-label="Delete this clip" title="Delete clip">
            <Trash2 size={16} />
          </button>
        </div>
      </div>
    </article>
  );
}

export function HelpModal({ onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="help-title" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="icon-btn modal-close" onClick={onClose} aria-label="Close help"><X size={18} /></button>
        <h2 id="help-title">How ClipRush works</h2>
        <ol className="help-steps">
          <li><b>Add a video.</b> Upload a file, or paste a YouTube, Twitch or Kick link. Only use videos you own or have permission to use.</li>
          <li><b>Pick a preset.</b> Presets set clip length, shape and caption style for Shorts, podcasts, gaming or YouTube. Tweak anything under “More options”.</li>
          <li><b>Generate.</b> Whisper transcribes the audio, AI picks the strongest moments, and each one is rendered with captions.</li>
          <li><b>Review and share.</b> Preview, download an MP4 (or all as a ZIP), copy a ready-made caption with hashtags, or get the subtitle file.</li>
        </ol>
        <h3>Tips for better clips</h3>
        <ul>
          <li>Clear speech matters most. Noisy or music-only audio gives weak results.</li>
          <li>Set the spoken <b>language</b> for non-English videos. It improves accuracy.</li>
          <li>Use <b>Blurred background</b> for widescreen gameplay or webcam footage so nothing important is cropped.</li>
          <li>Use the “Creator notes” box to steer the AI (e.g. “funny moments only”).</li>
          <li>Generating again on the same video reuses the saved transcript, so it is quicker.</li>
        </ul>
        <button type="button" className="primary-btn" onClick={onClose}>Got it</button>
      </div>
    </div>
  );
}

export function Toasts({ toasts, error, onDismissError, onDismissToast }) {
  return (
    <div className="toast-stack">
      {error && (
        <div className="error-banner" role="alert">
          <X size={16} aria-hidden="true" /><span>{error}</span>
          <button type="button" onClick={onDismissError} aria-label="Dismiss error"><X size={15} /></button>
        </div>
      )}
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.type === "error" ? "toast-error" : ""}`} role="status" onClick={() => onDismissToast(t.id)}>
          <CheckCircle2 size={16} aria-hidden="true" />{t.message}
        </div>
      ))}
    </div>
  );
}
