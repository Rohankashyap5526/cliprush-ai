import { useMemo, useState } from "react";
import {
  AlertTriangle, ArrowRight, Check, CheckCircle2, Clapperboard, Film, FolderOpen, Link2, LoaderCircle, Play, Plus,
  RotateCcw, Scissors, Settings, ShieldCheck, SlidersHorizontal, Sparkles, Trash2, Upload, Video, WandSparkles,
  Youtube, ArrowDownToLine, Gauge,
} from "lucide-react";
import { BASE, apiUrl } from "./api";
import { ClipCard, Dropzone, JobProgress, Select, Toggle } from "./components";
import { DEFAULT_OPTS, LANGUAGES, PRESETS, formatBytes, formatTime, timeAgo, validateOpts } from "./utils";

/* ------------------------------------------------------------------ Overview */
export function Overview({ app }) {
  const { videos, totalClips, goCreate, openProject } = app;
  const recent = videos.slice(0, 4);
  return (
    <section>
      <div className="welcome-row">
        <div>
          <div className="eyebrow"><Sparkles size={14} /> YOUR AI CREATOR WORKSPACE</div>
          <h1>AI video clip generator for <span>short-form content.</span></h1>
          <p className="subheading">Turn long videos, podcasts and streams into YouTube Shorts, Instagram Reels and TikTok clips with AI-selected highlights, word-timed captions and ready-to-post descriptions.</p>
        </div>
        <button type="button" className="primary-btn" onClick={() => goCreate()}><Plus size={17} /> Create new clips</button>
      </div>

      <div className="hero-card">
        <div className="hero-copy">
          <div className="hero-pill"><WandSparkles size={14} /> CLIPRUSH AI STUDIO</div>
          <h2>Long videos.<br /><span>Share-ready short clips.</span></h2>
          <p>Upload or import a video. ClipRush transcribes the speech, finds the moments worth sharing, adds captions and writes the post caption for you.</p>
          <button type="button" className="hero-btn" onClick={() => goCreate()}>Start creating <ArrowRight size={16} /></button>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orb orb-one" /><div className="orb orb-two" />
          <div className="video-stack stack-back"><div className="stack-bar" /><div className="stack-lines" /></div>
          <div className="video-stack stack-front">
            <div className="play-circle"><Play fill="currentColor" size={22} /></div>
            <div className="stack-caption">YOUR NEXT SHORT</div>
            <div className="waveform">{Array.from({ length: 22 }, (_, i) => <i key={i} style={{ height: `${12 + (i * 17) % 37}px` }} />)}</div>
          </div>
          <div className="floating-tag"><Sparkles size={13} /> AI MOMENT FOUND</div>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card"><div className="stat-icon purple"><Video size={18} /></div><small>Projects</small><b className="stat-value">{videos.length}</b><span>Videos in your workspace</span></div>
        <div className="stat-card"><div className="stat-icon blue"><Scissors size={18} /></div><small>Clips generated</small><b className="stat-value">{totalClips}</b><span>Across all projects</span></div>
        <div className="stat-card"><div className="stat-icon green"><Gauge size={18} /></div><small>Processing engine</small><b className="stat-value">Groq AI</b><span>Whisper transcription + highlight selection</span></div>
      </div>

      <div className="section-heading"><div><h3>Quick start</h3><p>Choose a source and create your first clips.</p></div></div>
      <div className="quick-grid">
        <button type="button" className="quick-card" onClick={() => goCreate("upload")}>
          <div className="quick-icon violet"><Upload size={20} /></div><div><b>Upload a video</b><small>MP4, MOV, MKV, WebM and more</small></div><ArrowRight size={17} />
        </button>
        <button type="button" className="quick-card" onClick={() => goCreate("url")}>
          <div className="quick-icon red"><Youtube size={20} /></div><div><b>Import a video link</b><small>YouTube, Twitch and Kick</small></div><ArrowRight size={17} />
        </button>
      </div>

      {recent.length > 0 && (
        <>
          <div className="section-heading spaced"><div><h3>Recent projects</h3><p>Pick up where you left off.</p></div></div>
          <div className="quick-grid">
            {recent.map((v) => (
              <button type="button" key={v.id} className="quick-card" onClick={() => openProject(v.id)}>
                <div className="quick-icon violet"><Film size={20} /></div>
                <div><b className="ellipsis">{v.filename}</b><small>{v.clips?.length || 0} clips · {formatTime(v.metadata?.duration)} · {timeAgo(v.created_at)}</small></div>
                <ArrowRight size={17} />
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

/* -------------------------------------------------------------------- Create */
export function Create({ app }) {
  const {
    sourceMode, setSourceMode, file, pickFile, uploadPct, busy, uploadVideo, cancelUpload, url, setUrl, urlInfo,
    inspectUrl, importUrl, video, videos, selectVideo, clearVideo, opts, setOpt, applyPreset, job, generate, health,
  } = app;
  const problem = useMemo(() => (video ? validateOpts(opts, video) : ""), [opts, video]);
  const working = !!job || busy === "upload";
  const activePreset = PRESETS.find((p) => Object.entries(p.set).every(([k, v]) => String(opts[k]) === String(v)));
  const reusable = videos.filter((v) => v.id !== video?.id);

  return (
    <section>
      <div className="page-title-row">
        <div>
          <div className="eyebrow"><Clapperboard size={14} /> NEW PROJECT</div>
          <h1>Create <span>clips</span></h1>
          <p className="subheading">Add a video, choose a preset, and generate. It usually takes a few minutes.</p>
        </div>
        <div className="step-chip" aria-hidden="true"><span>01</span> SOURCE <i /> <span>02</span> SETTINGS <i /> <span>03</span> CLIPS</div>
      </div>

      <div className="create-layout">
        <div className="create-main">
          {/* ---------- step 1 ---------- */}
          <div className="panel">
            <div className="panel-heading"><div><h3>Choose your source</h3><p>Upload a file or import a link.</p></div><span className="step-number">01</span></div>

            {video ? (
              <div className="uploaded-source">
                <div className="uploaded-check"><Check size={16} /></div>
                <div>
                  <b>{video.filename}</b>
                  <small>{formatTime(video.metadata?.duration)} · {video.metadata?.width} × {video.metadata?.height} · {formatBytes(video.metadata?.size_bytes)} · ready</small>
                </div>
                <button type="button" className="text-btn" onClick={clearVideo} disabled={working}>Use a different video</button>
              </div>
            ) : (
              <>
                <div className="source-tabs" role="tablist">
                  <button type="button" role="tab" aria-selected={sourceMode === "upload"} className={sourceMode === "upload" ? "selected" : ""} onClick={() => setSourceMode("upload")}><Upload size={16} /> Upload video</button>
                  <button type="button" role="tab" aria-selected={sourceMode === "url"} className={sourceMode === "url" ? "selected" : ""} onClick={() => setSourceMode("url")}><Youtube size={17} /> Video link</button>
                </div>

                {sourceMode === "upload" ? (
                  <>
                    <Dropzone file={file} onFile={pickFile} maxMb={health?.max_upload_mb} disabled={busy === "upload"} />
                    {busy === "upload" && (
                      <div className="upload-progress" role="status" aria-live="polite">
                        <div className="bar" role="progressbar" aria-valuenow={uploadPct ?? 0} aria-valuemin={0} aria-valuemax={100}><div className="bar-fill" style={{ width: `${uploadPct ?? 0}%` }} /></div>
                        <span>Uploading… {uploadPct ?? 0}%</span>
                        <button type="button" className="text-btn" onClick={cancelUpload}>Cancel</button>
                      </div>
                    )}
                    <div className="upload-actions">
                      <span><ShieldCheck size={14} /> Only process content you own or are authorized to use.</span>
                      <button type="button" className="secondary-btn" onClick={uploadVideo} disabled={!file || busy === "upload"}>
                        {busy === "upload" ? <><LoaderCircle size={16} className="spin" /> Uploading…</> : <>Upload and continue <ArrowRight size={15} /></>}
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="youtube-box">
                    <label htmlFor="video-url">Video link · YouTube, Twitch or Kick</label>
                    <form className="url-form" onSubmit={inspectUrl}>
                      <div className="url-input-wrap"><Link2 size={17} aria-hidden="true" />
                        <input id="video-url" type="url" inputMode="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=…" autoComplete="off" disabled={working} />
                      </div>
                      <button type="submit" className="secondary-btn" disabled={busy === "inspect" || working || !url.trim()}>
                        {busy === "inspect" ? <LoaderCircle className="spin" size={16} /> : "Check link"}
                      </button>
                    </form>
                    <div className="notice"><ShieldCheck size={16} /><span>Imports work for public videos when the platform allows it and can fail if it blocks downloads. If that happens, upload the file instead. Only use videos you own or have permission to use.</span></div>
                    {urlInfo && (
                      <div className="youtube-preview-card">
                        <div className="url-result">
                          {urlInfo.thumbnail && <img src={urlInfo.thumbnail} alt="" referrerPolicy="no-referrer" />}
                          <div className="youtube-meta">
                            <b>{urlInfo.title}</b>
                            <small>{[urlInfo.uploader, urlInfo.provider].filter(Boolean).join(" · ")}</small>
                            <span className="authorized-label"><CheckCircle2 size={13} /> {formatTime(urlInfo.duration)} · link looks good</span>
                          </div>
                        </div>
                        <div className="youtube-upload-cta">
                          <div><b>Import this video</b><small>You confirm you have the rights to process it.</small></div>
                          <button type="button" className="secondary-btn" onClick={importUrl} disabled={working}>
                            {job?.kind === "import" ? <><LoaderCircle size={15} className="spin" /> Importing…</> : <>Import and continue <ArrowRight size={14} /></>}
                          </button>
                        </div>
                      </div>
                    )}
                    {job?.kind === "import" && <JobProgress job={job} />}
                  </div>
                )}

                {reusable.length > 0 && !working && (
                  <div className="reuse-row">
                    <FolderOpen size={15} aria-hidden="true" />
                    <label htmlFor="reuse-video">Or continue with an earlier video</label>
                    <div className="select-wrap">
                      <select id="reuse-video" value="" onChange={(e) => e.target.value && selectVideo(e.target.value)}>
                        <option value="">Choose…</option>
                        {reusable.map((v) => <option key={v.id} value={v.id}>{v.filename} ({formatTime(v.metadata?.duration)})</option>)}
                      </select>
                    </div>
                  </div>
                )}
              </>
            )}
            {video?.metadata?.has_audio === false && (
              <div className="notice warn"><AlertTriangle size={16} /><span>This video has no audio track, so there is nothing to transcribe. Upload a version with its original audio.</span></div>
            )}
          </div>

          {/* ---------- step 2 ---------- */}
          <div className="panel">
            <div className="panel-heading"><div><h3>Clip preferences</h3><p>Start from a preset, then adjust anything you like.</p></div><span className="step-number">02</span></div>

            <div className="preset-row" role="group" aria-label="Presets">
              {PRESETS.map((p) => (
                <button type="button" key={p.id} className={`preset ${activePreset?.id === p.id ? "active" : ""}`} aria-pressed={activePreset?.id === p.id} onClick={() => applyPreset(p)} disabled={working}>
                  <b>{p.label}</b><small>{p.hint}</small>
                </button>
              ))}
            </div>

            <div className="field-grid">
              <Select id="content-type" label="What kind of video is it?" value={opts.content_type} onChange={(v) => setOpt("content_type", v)}>
                <option value="hybrid">Mixed / not sure</option><option value="gaming">Gaming</option><option value="podcast">Podcast / interview</option><option value="general">General video</option>
              </Select>
              <Select id="clip-count" label="Number of clips" value={opts.clip_count} onChange={(v) => setOpt("clip_count", Number(v))}>
                {[3, 5, 8, 10, 15, 20].map((n) => <option key={n} value={n}>{n} clips</option>)}
              </Select>
              <Select id="ratio" label="Shape" value={opts.aspect_ratio} onChange={(v) => setOpt("aspect_ratio", v)}>
                <option value="9:16">Vertical 9:16 · Shorts, Reels, TikTok</option><option value="1:1">Square 1:1 · feed posts</option><option value="16:9">Landscape 16:9 · YouTube</option>
              </Select>
              <Select id="caption-style" label="Captions" value={opts.caption_style} onChange={(v) => setOpt("caption_style", v)}>
                <option value="karaoke">Word highlight (popular)</option><option value="bold">Bold creator</option><option value="classic">Classic</option><option value="minimal">Minimal</option><option value="none">No captions</option>
              </Select>
              <div className="field">
                <label htmlFor="min-dur">Clip length</label>
                <div className="duration-row">
                  <input id="min-dur" type="number" inputMode="numeric" min="5" max="120" value={opts.min_duration} onChange={(e) => setOpt("min_duration", e.target.value)} aria-label="Minimum seconds" />
                  <span>to</span>
                  <input id="max-dur" type="number" inputMode="numeric" min="10" max="180" value={opts.max_duration} onChange={(e) => setOpt("max_duration", e.target.value)} aria-label="Maximum seconds" />
                  <small>seconds</small>
                </div>
              </div>
            </div>

            <details className="more-options">
              <summary><SlidersHorizontal size={15} /> More options</summary>
              <div className="field-grid">
                <Select id="reframe" label="Fit to frame" value={opts.reframe} onChange={(v) => setOpt("reframe", v)} hint="Blurred background keeps the whole picture visible.">
                  <option value="crop">Crop to fill</option><option value="blur">Blurred background (show full frame)</option>
                </Select>
                <Select id="cap-pos" label="Caption position" value={opts.caption_position} onChange={(v) => setOpt("caption_position", v)}>
                  <option value="bottom">Lower third</option><option value="middle">Middle of screen</option>
                </Select>
                <Select id="quality" label="Quality" value={opts.quality} onChange={(v) => setOpt("quality", v)} hint="High takes longer to render.">
                  <option value="standard">Standard · 720p (faster)</option><option value="high">High · 1080p (slower)</option>
                </Select>
                <Select id="language" label="Spoken language" value={opts.language} onChange={(v) => setOpt("language", v)} hint="Set this for non-English videos.">
                  {LANGUAGES.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
                </Select>
                <Toggle id="show-hook" label="Hook title at the start" checked={opts.show_hook} onChange={(v) => setOpt("show_hook", v)} hint="Shows a short headline for the first 3 seconds." />
                <div className="field wide">
                  <label htmlFor="guidance">Creator notes (optional)</label>
                  <textarea id="guidance" rows={2} maxLength={300} value={opts.guidance} onChange={(e) => setOpt("guidance", e.target.value)} placeholder="e.g. Only funny moments. Skip anything about sponsors." />
                  <small className="field-hint">{opts.guidance.length}/300</small>
                </div>
              </div>
              <button type="button" className="text-btn" onClick={() => Object.entries(DEFAULT_OPTS).forEach(([k, v]) => setOpt(k, v))}><RotateCcw size={12} /> Reset to defaults</button>
            </details>

            {problem && <div className="notice warn" role="alert"><AlertTriangle size={16} /><span>{problem}</span></div>}

            <div className="engine-note"><Sparkles size={16} /><div><b>How it works</b><small>Groq Whisper transcribes the audio, then AI picks the strongest moments, writes hooks and captions, and each clip is rendered with burned-in subtitles. {health && !health.groq_configured ? "⚠ The server has no Groq API key yet. Add GROQ_API_KEY to enable this." : ""}</small></div></div>

            <button type="button" className="generate-btn" onClick={generate} disabled={!video || working || !!problem || health?.groq_configured === false}>
              {job?.kind === "analyze" ? <><LoaderCircle size={17} className="spin" /> Working on your clips…</> : <><WandSparkles size={17} /> Generate clips <ArrowRight size={17} /></>}
            </button>
            {!video && <p className="hint-line">Add a video in step 1 to continue.</p>}
            {job?.kind === "analyze" && <JobProgress job={job} />}
          </div>
        </div>

        <aside className="side-column">
          <div className="tips-card">
            <div className="tips-icon"><Sparkles size={17} /></div>
            <h3>Creator tip</h3>
            <p>Clear speech makes the biggest difference. Start with recordings that have a clean audio track and distinct moments.</p>
            <div className="tip-divider" />
            <div className="tip-row"><CheckCircle2 size={15} /> Clear audio track</div>
            <div className="tip-row"><CheckCircle2 size={15} /> Set the language if it isn’t English</div>
            <div className="tip-row"><CheckCircle2 size={15} /> Content you have rights to</div>
          </div>
          <div className="mini-status">
            <div className="status-head"><span>SERVER STATUS</span><span className={health ? "status-ok" : "status-bad"}>{health ? "ONLINE" : "OFFLINE"}</span></div>
            <p>{health ? (health.ffmpeg_available ? "Server is ready to process video." : "Server is online but FFmpeg is missing.") : "Can’t reach the server. Check that the backend is running."}</p>
          </div>
        </aside>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------- Library */
const SORTS = [["newest", "Newest first"], ["score", "Highest score"], ["time", "Order in video"]];

export function Library({ app }) {
  const { videos, selectedId, openProject, goCreate, deleteProject, deleteClip, notify, job } = app;
  const [sort, setSort] = useState("newest");
  const current = videos.find((v) => v.id === selectedId) || videos[0];
  const clips = useMemo(() => {
    const list = [...(current?.clips || [])];
    if (sort === "score") list.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    else if (sort === "time") list.sort((a, b) => a.start - b.start);
    else list.sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0));
    return list;
  }, [current, sort]);

  return (
    <section>
      <div className="page-title-row">
        <div>
          <div className="eyebrow"><Film size={14} /> YOUR LIBRARY</div>
          <h1>My <span>clips</span></h1>
          <p className="subheading">Everything you’ve generated, saved across visits. Files are removed automatically after {app.health?.retention_hours ? `${app.health.retention_hours} hours` : "a while"}, so download what you want to keep.</p>
        </div>
        <button type="button" className="primary-btn" onClick={() => goCreate()}><Plus size={17} /> New project</button>
      </div>

      {videos.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon"><Film size={28} /></div>
          <h3>No projects yet</h3>
          <p>Upload or import a video you’re allowed to use, and your clips will show up here.</p>
          <button type="button" className="primary-btn" onClick={() => goCreate()}>Create your first clips <ArrowRight size={16} /></button>
        </div>
      ) : (
        <>
          <div className="project-row" role="tablist" aria-label="Projects">
            {videos.map((v) => (
              <button type="button" role="tab" aria-selected={v.id === current?.id} key={v.id} className={`project-chip ${v.id === current?.id ? "active" : ""}`} onClick={() => openProject(v.id, false)}>
                <b className="ellipsis">{v.filename}</b>
                <small>{v.clips?.length || 0} clips · {timeAgo(v.created_at)}{v.status === "failed" ? " · failed" : ""}</small>
              </button>
            ))}
          </div>

          {current && (
            <div className="project-toolbar">
              <div className="project-meta">
                <b className="ellipsis">{current.filename}</b>
                <small>{formatTime(current.metadata?.duration)} · {current.metadata?.width} × {current.metadata?.height}</small>
              </div>
              <div className="project-actions">
                {clips.length > 1 && (
                  <div className="select-wrap compact"><select aria-label="Sort clips" value={sort} onChange={(e) => setSort(e.target.value)}>{SORTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
                )}
                <button type="button" className="secondary-btn" onClick={() => goCreate(null, current.id)} disabled={!!job}><WandSparkles size={14} /> Make more clips</button>
                {clips.length > 0 && <a className="secondary-btn" href={apiUrl(`/api/videos/${current.id}/clips.zip`)}><ArrowDownToLine size={14} /> Download all (ZIP)</a>}
                <button type="button" className="secondary-btn danger" onClick={() => deleteProject(current)}><Trash2 size={14} /> Delete project</button>
              </div>
            </div>
          )}

          {clips.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon"><Film size={28} /></div>
              <h3>{current?.status === "failed" ? "That run didn’t produce clips" : "No clips for this video yet"}</h3>
              <p>{current?.status === "failed" ? "Something went wrong last time. Try again, possibly with a wider clip-length range." : "Generate clips from this video to see them here."}</p>
              <button type="button" className="primary-btn" onClick={() => goCreate(null, current.id)}>Generate clips <ArrowRight size={16} /></button>
            </div>
          ) : (
            <div className="clips-grid">
              {clips.map((clip, i) => <ClipCard key={clip.id} clip={clip} index={i} notify={notify} onDelete={(c) => deleteClip(current, c)} />)}
            </div>
          )}
        </>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ Settings */
export function SettingsView({ app }) {
  const { health, videos, clearAll, resetPrefs } = app;
  const rows = [
    ["Backend URL", "Set VITE_API_BASE in frontend/.env for local development.", <code>{BASE || "Same origin"}</code>],
    ["AI provider", "Transcription and highlight selection both use Groq.", <span>{health ? (health.groq_configured ? "Groq connected" : "Groq API key missing") : "Unknown"}</span>],
    ["Models", "Change with GROQ_CHAT_MODEL and GROQ_STT_MODEL.", <span>{health ? `${health.chat_model} · ${health.transcription_model}` : "—"}</span>],
    ["Video tools", "FFmpeg renders clips; yt-dlp imports links.", <span>{health ? `FFmpeg ${health.ffmpeg_available ? "✓" : "✗"} · yt-dlp ${health.yt_dlp_available ? "✓" : "✗"}` : "—"}</span>],
    ["Upload limit", "Set with CLIPRUSH_MAX_UPLOAD_MB.", <span>{health ? `${health.max_upload_mb} MB` : "—"}</span>],
    ["Automatic cleanup", "Set with CLIPRUSH_RETENTION_HOURS (0 keeps files).", <span>{health ? (health.retention_hours ? `After ${health.retention_hours} h` : "Never") : "—"}</span>],
    ["Version", "", <span>{health?.version || "—"}</span>],
  ];
  return (
    <section>
      <div className="page-title-row"><div><div className="eyebrow"><Settings size={14} /> PREFERENCES</div><h1>Workspace <span>settings</span></h1><p className="subheading">What this server is running, and your saved preferences.</p></div></div>
      <div className="panel settings-panel">
        <div className="panel-heading"><div><h3>Server</h3><p>Read-only status from the backend.</p></div><span className={`status-pill ${health ? "good" : "bad"}`}>{health ? "Connected" : "Not connected"}</span></div>
        {rows.map(([title, hint, value]) => (
          <div className="setting-row" key={title}><div><b>{title}</b>{hint && <small>{hint}</small>}</div>{value}</div>
        ))}
      </div>
      <div className="panel settings-panel spaced">
        <div className="panel-heading"><div><h3>Your data</h3><p>Preferences are stored in this browser only.</p></div></div>
        <div className="setting-row"><div><b>Reset clip preferences</b><small>Restore the default presets and options.</small></div><button type="button" className="secondary-btn" onClick={resetPrefs}><RotateCcw size={14} /> Reset</button></div>
        <div className="setting-row"><div><b>Delete all projects</b><small>Removes every uploaded video and generated clip from the server ({videos.length} project{videos.length === 1 ? "" : "s"}).</small></div><button type="button" className="secondary-btn danger" onClick={clearAll} disabled={videos.length === 0}><Trash2 size={14} /> Delete all</button></div>
      </div>
    </section>
  );
}
