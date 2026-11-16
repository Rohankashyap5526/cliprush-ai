import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, ArrowDownToLine, ArrowLeft, ArrowRight, Check, CheckCircle2,
  ChevronDown, Clapperboard, Clock3, CloudUpload, Film, FolderOpen,
  Gauge, HelpCircle, Home, Image as ImageIcon, Link2, LoaderCircle,
  Menu, MoreHorizontal, Play, Plus, Scissors, Settings, ShieldCheck,
  Sparkles, Upload, Video, WandSparkles, X, Youtube, Zap
} from "lucide-react";

const API = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

function formatTime(seconds = 0) {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}
function App() {
  const [active, setActive] = useState("Overview");
  const [mobileNav, setMobileNav] = useState(false);
  const [sourceMode, setSourceMode] = useState("upload");
  const [file, setFile] = useState(null);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [youtubeInfo, setYoutubeInfo] = useState(null);
  const [groqConfigured, setGroqConfigured] = useState(false);
  const [video, setVideo] = useState(null);
  const [clips, setClips] = useState([]);
  const [contentType, setContentType] = useState("hybrid");
  const [clipCount, setClipCount] = useState(5);
  const [ratio, setRatio] = useState("9:16");
  const [captionStyle, setCaptionStyle] = useState("bold");
  const [minDuration, setMinDuration] = useState(15);
  const [maxDuration, setMaxDuration] = useState(45);
  const [busy, setBusy] = useState("");
  const [progressText, setProgressText] = useState("");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [apiOnline, setApiOnline] = useState(false);
  const fileInput = useRef(null);

  useEffect(() => {
    fetch(`${API}/health`).then(async r => { setApiOnline(r.ok); if (r.ok) { const d = await r.json(); setGroqConfigured(!!d.groq_configured); } }).catch(() => setApiOnline(false));
  }, []);

  const notify = (message) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 3200);
  };
  const request = async (url, options = {}) => {
    const response = await fetch(`${API}${url}`, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
    return data;
  };

  async function inspectYoutube(e) {
    e?.preventDefault();
    setError("");
    setYoutubeInfo(null);
    if (!youtubeUrl.trim()) return setError("Paste a YouTube, Twitch or Kick video URL first.");
    setBusy("inspect");
    try {
      const data = await request("/api/sources/inspect", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: youtubeUrl.trim() })
      });
      setYoutubeInfo(data);
    } catch (err) { setError(err.message); }
    finally { setBusy(""); }
  }

  async function importSource() {
    setError("");
    if (!youtubeUrl.trim()) return setError("Paste a supported video URL first.");
    setBusy("download");
    setProgressText("Retrieving source video. This can take a while for long videos…");
    try {
      const data = await request("/api/sources/download", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: youtubeUrl.trim() })
      });
      setVideo(data); setClips([]); setProgressText("");
      notify("Source video imported successfully."); setActive("Create clips");
    } catch (err) { setError(err.message); }
    finally { setBusy(""); setProgressText(""); }
  }

  async function uploadVideo() {
    setError("");
    if (!file) return setError("Choose a video file to upload.");
    setBusy("upload");
    setProgressText("Uploading your source video…");
    try {
      const form = new FormData();
      form.append("file", file);
      const data = await request("/api/videos", { method: "POST", body: form });
      setVideo(data);
      setClips([]);
      setProgressText("");
      notify("Video uploaded successfully.");
      setActive("Create clips");
    } catch (err) { setError(err.message); }
    finally { setBusy(""); setProgressText(""); }
  }

  async function generateClips() {
    if (!video?.id) return setError("Upload an authorized source video before generating clips.");
    setError("");
    setBusy("process");
    setProgressText("Groq is transcribing speech, selecting highlights and rendering captions…");
    try {
      const started = await request(`/api/videos/${video.id}/analyze`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          clip_count: Number(clipCount), min_duration: Number(minDuration), max_duration: Number(maxDuration),
          aspect_ratio: ratio, content_type: contentType, caption_style: captionStyle
        })
      });
      let job;
      do {
        await new Promise(resolve => window.setTimeout(resolve, 1800));
        job = await request(`/api/jobs/${started.job_id}`);
        setProgressText(job.message || "Processing your video…");
      } while (!["completed", "failed"].includes(job.status));
      if (job.status === "failed") throw new Error(job.error || "Clip generation failed.");
      setClips(job.clips || []);
      setActive("My clips");
      notify(`${(job.clips || []).length} clips generated with Groq AI.`);
    } catch (err) { setError(err.message); }
    finally { setBusy(""); setProgressText(""); }
  }

  const stats = useMemo(() => ({
    clips: clips.length,
    source: video ? video.filename : "No source selected"
  }), [clips, video]);

  const navItems = [
    { name: "Overview", icon: Home },
    { name: "Create clips", icon: WandSparkles },
    { name: "My clips", icon: Film },
    { name: "Settings", icon: Settings }
  ];

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><Scissors size={20}/></div>
          <div><strong>cliprush<span>.ai</span></strong><small>CREATOR STUDIO</small></div>
          <button className="icon-btn mobile-close" onClick={() => setMobileNav(false)}><X size={18}/></button>
        </div>
        <div className="workspace-label">WORKSPACE</div>
        <nav>
          {navItems.map(item => {
            const Icon = item.icon;
            return <button key={item.name} className={`nav-item ${active === item.name ? "active" : ""}`} onClick={() => { setActive(item.name); setMobileNav(false); }}>
              <Icon size={18}/><span>{item.name}</span>{item.name === "My clips" && clips.length > 0 && <b className="nav-count">{clips.length}</b>}
            </button>;
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="plan-card">
            <div className="plan-icon"><Zap size={16}/></div>
            <div><b>Free workspace</b><small>Local development mode</small></div>
            <span className="plan-dot"/>
          </div>
          <div className="profile-row">
            <div className="avatar">CR</div>
            <div><b>Creator workspace</b><small>Local MVP</small></div>
            <MoreHorizontal size={18} className="muted"/>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <button className="icon-btn mobile-menu" onClick={() => setMobileNav(true)}><Menu size={20}/></button>
          <div className="breadcrumb">Workspace <span>/</span> <b>{active}</b></div>
          <div className="top-actions">
            <div className={`api-status ${apiOnline ? "online" : "offline"}`}><span/>{apiOnline ? "API connected" : "API offline"}</div>
            <button className="help-btn" onClick={() => notify("Upload a video you own or are authorized to process.")}><HelpCircle size={17}/></button>
            <div className="avatar top-avatar">CR</div>
          </div>
        </header>

        <div className="page-content">
          {active === "Overview" && <section>
            <div className="welcome-row">
              <div><div className="eyebrow"><Sparkles size={14}/> YOUR AI CREATOR WORKSPACE</div><h1>AI video clip generator for <span>short-form content.</span></h1><p className="subheading">Turn long videos, podcasts and streams into engaging YouTube Shorts, Instagram Reels and TikTok clips with AI-selected highlights and timed captions.</p></div>
              <button className="primary-btn" onClick={() => setActive("Create clips")}><Plus size={17}/> Create new clips</button>
            </div>
            <div className="hero-card">
              <div className="hero-copy"><div className="hero-pill"><WandSparkles size={14}/> CLIPRUSH AI STUDIO</div><h2>Long videos.<br/><span>Share-ready short clips.</span></h2><p>Upload or import a video. ClipRush AI transcribes speech, identifies engaging moments, adds timed captions and helps you create short-form videos for social media.</p><button className="hero-btn" onClick={() => setActive("Create clips")}>Start creating <ArrowRight size={16}/></button></div>
              <div className="hero-art">
                <div className="orb orb-one"/><div className="orb orb-two"/>
                <div className="video-stack stack-back"><div className="stack-bar"/><div className="stack-lines"/></div>
                <div className="video-stack stack-front"><div className="play-circle"><Play fill="currentColor" size={22}/></div><div className="stack-caption">YOUR NEXT SHORT</div><div className="waveform">{Array.from({length:22},(_,i)=><i key={i} style={{height:`${12+(i*17)%37}px`}}/>)}</div></div>
                <div className="floating-tag"><Sparkles size={13}/> AI MOMENT FOUND</div>
              </div>
            </div>
            <div className="stats-grid">
              <div className="stat-card"><div className="stat-icon purple"><Video size={18}/></div><small>Current source</small><b className="stat-value source-stat">{stats.source}</b><span>Uploaded in this session</span></div>
              <div className="stat-card"><div className="stat-icon blue"><Scissors size={18}/></div><small>Clips generated</small><b className="stat-value">{stats.clips}</b><span>From your current source</span></div>
              <div className="stat-card"><div className="stat-icon green"><Gauge size={18}/></div><small>Processing engine</small><b className="stat-value">Groq AI</b><span>Whisper transcription + AI highlight selection</span></div>
            </div>
            <div className="section-heading"><div><h3>Quick start</h3><p>Choose a source and create your first clips.</p></div></div>
            <div className="quick-grid">
              <button className="quick-card" onClick={() => { setSourceMode("upload"); setActive("Create clips"); }}><div className="quick-icon violet"><CloudUpload size={20}/></div><div><b>Upload a video</b><small>MP4, MOV, MKV and more</small></div><ArrowRight size={17}/></button>
              <button className="quick-card" onClick={() => { setSourceMode("youtube"); setActive("Create clips"); }}><div className="quick-icon red"><Youtube size={20}/></div><div><b>Import video URL</b><small>YouTube, Twitch and Kick links</small></div><ArrowRight size={17}/></button>
            </div>
          </section>}

          {active === "Create clips" && <section>
            <div className="page-title-row"><div><div className="eyebrow"><Clapperboard size={14}/> NEW PROJECT</div><h1>Create <span>clips</span></h1><p className="subheading">Choose a source, configure your output, and generate candidate highlights.</p></div><div className="step-chip"><span>01</span> SOURCE <i/> <span>02</span> SETTINGS <i/> <span>03</span> EXPORT</div></div>
            <div className="create-layout">
              <div className="create-main">
                <div className="panel">
                  <div className="panel-heading"><div><h3>Choose your source</h3><p>Upload a video or import a YouTube, Twitch or Kick link.</p></div><span className="step-number">01</span></div>
                  <div className="source-tabs">
                    <button className={sourceMode === "upload" ? "selected" : ""} onClick={() => setSourceMode("upload")}><Upload size={16}/> Upload video</button>
                    <button className={sourceMode === "youtube" ? "selected" : ""} onClick={() => setSourceMode("youtube")}><Youtube size={17}/> Video URL</button>
                  </div>
                  {sourceMode === "upload" ? <div className={`dropzone ${file ? "has-file" : ""}`} onClick={() => fileInput.current?.click()} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); const f=e.dataTransfer.files?.[0]; if(f) setFile(f); }}>
                    <input ref={fileInput} type="file" accept="video/*,.mkv,.mov,.mp4,.webm" hidden onChange={e => setFile(e.target.files?.[0] || null)}/>
                    <div className="upload-symbol"><CloudUpload size={25}/></div>
                    {file ? <><b>{file.name}</b><small>{(file.size/1024/1024).toFixed(1)} MB · Ready to upload</small><button className="text-btn" onClick={e => {e.stopPropagation();setFile(null);}}>Remove file</button></> : <><b>Drop your video here, or <em>browse files</em></b><small>MP4, MOV, MKV, WEBM · Max 1 GB by default</small></>}
                  </div> : <div className="youtube-box">
                    <label htmlFor="youtube-url">Video URL · YouTube, Twitch or Kick</label>
                    <form className="url-form" onSubmit={inspectYoutube}><div className="url-input-wrap"><Link2 size={17}/><input id="youtube-url" value={youtubeUrl} onChange={e => setYoutubeUrl(e.target.value)} placeholder="Paste a YouTube, Twitch or Kick video URL…" /></div><button className="secondary-btn" disabled={busy === "inspect"}>{busy === "inspect" ? <LoaderCircle className="spin" size={16}/> : "Inspect URL"}</button></form>
                    <div className="notice"><ShieldCheck size={16}/><span>ClipRush attempts retrieval through yt-dlp for supported public sources. Downloads can fail when a platform blocks access. Only process videos you own or have permission to use; no DRM or access-control bypasses are used.</span></div>
                    {youtubeInfo && <div className="youtube-preview-card">
                      {youtubeInfo.thumbnail && <div className="youtube-preview"><img src={youtubeInfo.thumbnail} alt="Video thumbnail" style={{width:"100%",height:"100%",objectFit:"cover"}}/></div>}
                      <div className="youtube-result"><div className="youtube-meta"><b>{youtubeInfo.title}</b><small>{youtubeInfo.uploader} · {youtubeInfo.provider}</small><span className="authorized-label"><CheckCircle2 size={13}/> {formatTime(youtubeInfo.duration)} · Source inspected</span></div></div>
                      <div className="youtube-upload-cta"><div><b>Import this source</b><small>ClipRush will try to retrieve the video if the source permits it. You confirm you have the necessary rights to process it.</small></div><button className="secondary-btn" onClick={importSource} disabled={busy === "download"}>{busy === "download" ? <><LoaderCircle size={15} className="spin"/> Importing…</> : <>Download & use <ArrowRight size={14}/></>}</button></div>
                    </div>}
                  </div>}
                  {sourceMode === "upload" && <div className="upload-actions"><span><ShieldCheck size={14}/> Only process content you own or are authorized to use.</span><button className="secondary-btn" onClick={uploadVideo} disabled={!file || busy === "upload"}>{busy === "upload" ? <><LoaderCircle size={16} className="spin"/> Uploading…</> : "Upload source"} <ArrowRight size={15}/></button></div>}
                  {video && <div className="uploaded-source"><div className="uploaded-check"><Check size={16}/></div><div><b>{video.filename}</b><small>{formatTime(video.metadata?.duration)} · {video.metadata?.width} × {video.metadata?.height} · Source ready</small></div><button className="text-btn" onClick={() => {setVideo(null);setClips([]);}}>Replace</button></div>}
                </div>

                <div className="panel">
                  <div className="panel-heading"><div><h3>Clip preferences</h3><p>Choose settings for your generated videos.</p></div><span className="step-number">02</span></div>
                  <div className="field-grid">
                    <div className="field"><label>Content type</label><div className="select-wrap"><select value={contentType} onChange={e => setContentType(e.target.value)}><option value="hybrid">Hybrid — general</option><option value="gaming">Gaming</option><option value="podcast">Podcast / interview</option><option value="general">General video</option></select><ChevronDown size={15}/></div></div>
                    <div className="field"><label>Number of clips</label><div className="select-wrap"><select value={clipCount} onChange={e => setClipCount(e.target.value)}>{[3,5,8,10,15,20].map(n=><option key={n} value={n}>{n} clips</option>)}</select><ChevronDown size={15}/></div></div>
                    <div className="field"><label>Output format</label><div className="select-wrap"><select value={ratio} onChange={e => setRatio(e.target.value)}><option value="9:16">9:16 · Shorts / Reels</option><option value="1:1">1:1 · Square</option><option value="16:9">16:9 · Landscape</option></select><ChevronDown size={15}/></div></div>
                    <div className="field"><label>Caption style</label><div className="select-wrap"><select value={captionStyle} onChange={e => setCaptionStyle(e.target.value)}><option value="bold">Bold creator</option><option value="classic">Classic</option><option value="minimal">Minimal</option></select><ChevronDown size={15}/></div></div>
                    <div className="field"><label>Clip duration</label><div className="duration-row"><input type="number" min="5" max="120" value={minDuration} onChange={e => setMinDuration(e.target.value)}/><span>to</span><input type="number" min="10" max="180" value={maxDuration} onChange={e => setMaxDuration(e.target.value)}/><small>sec</small></div></div>
                  </div>
                  <div className="engine-note"><Sparkles size={16}/><div><b>Groq AI pipeline</b><small>Groq Whisper creates word-level timestamps; Groq LLM selects highlights and writes hooks. Captions are burned into the exported video. {groqConfigured ? "Groq API key detected." : "Add GROQ_API_KEY to your backend .env file."}</small></div></div>
                  <button className="generate-btn" onClick={generateClips} disabled={!video || busy === "process"}>{busy === "process" ? <><LoaderCircle size={17} className="spin"/> Processing video…</> : <><WandSparkles size={17}/> Generate clips <ArrowRight size={17}/></>}</button>
                  {progressText && <div className="progress-line"><LoaderCircle size={15} className="spin"/>{progressText}</div>}
                </div>
              </div>
              <aside className="side-column">
                <div className="tips-card"><div className="tips-icon"><Sparkles size={17}/></div><h3>Creator tip</h3><p>Start with recordings that have clear audio and distinct moments. Groq transcribes speech, selects moments and generates word-timed captions.</p><div className="tip-divider"/><div className="tip-row"><CheckCircle2 size={15}/> Clear audio track</div><div className="tip-row"><CheckCircle2 size={15}/> Stable video recording</div><div className="tip-row"><CheckCircle2 size={15}/> Content you can use</div></div>
                <div className="mini-status"><div className="status-head"><span>BACKEND STATUS</span><span className={apiOnline ? "status-ok" : "status-bad"}>{apiOnline ? "ONLINE" : "OFFLINE"}</span></div><p>{apiOnline ? "ClipRush API is responding on your configured local address." : "Start the FastAPI server at 127.0.0.1:8000 to upload and process videos."}</p></div>
              </aside>
            </div>
          </section>}

          {active === "My clips" && <section>
            <div className="page-title-row"><div><div className="eyebrow"><Film size={14}/> YOUR LIBRARY</div><h1>My <span>clips</span></h1><p className="subheading">Preview and download clips generated in this session.</p></div><button className="primary-btn" onClick={() => setActive("Create clips")}><Plus size={17}/> New project</button></div>
            {clips.length === 0 ? <div className="empty-state"><div className="empty-icon"><Film size={28}/></div><h3>No clips yet</h3><p>Upload or import a video you are authorized to process and run Groq AI clipping to see your clips here.</p><button className="primary-btn" onClick={() => setActive("Create clips")}>Create your first clips <ArrowRight size={16}/></button></div> :
              <div className="clips-grid">{clips.map((clip, i) => <article className="clip-card" key={clip.id}><div className="clip-preview"><video src={`${API}${clip.url}`} controls preload="metadata"/><span className="clip-index">CLIP {String(i+1).padStart(2,"0")}</span></div><div className="clip-info"><div className="clip-title-row"><b>Highlight {i+1}</b><span className="score-pill">{Math.round((clip.score || 0)*100)} signal</span></div><p>{formatTime(clip.start)} – {formatTime(clip.end)} · {clip.duration}s</p><small>{clip.reason}</small><a className="download-btn" href={`${API}${clip.url}`} download><ArrowDownToLine size={15}/> Download MP4</a></div></article>)}</div>}
          </section>}

          {active === "Settings" && <section>
            <div className="page-title-row"><div><div className="eyebrow"><Settings size={14}/> PREFERENCES</div><h1>Workspace <span>settings</span></h1><p className="subheading">Groq AI configuration and local storage.</p></div></div>
            <div className="panel settings-panel"><div className="panel-heading"><div><h3>API connection</h3><p>Frontend backend endpoint.</p></div><span className={`status-pill ${apiOnline ? "good" : "bad"}`}>{apiOnline ? "Connected" : "Not connected"}</span></div><div className="setting-row"><div><b>Backend URL</b><small>Set VITE_API_BASE in frontend/.env to change this address.</small></div><code>{API}</code></div><div className="setting-row"><div><b>AI provider</b><small>All transcription and highlight selection calls use Groq only.</small></div><span>{groqConfigured ? "Groq configured" : "Groq API key missing"}</span></div><div className="setting-row"><div><b>Storage mode</b><small>Files are stored by your local FastAPI backend.</small></div><span>Local filesystem</span></div><div className="setting-row"><div><b>Account system</b><small>Authentication and subscriptions are not included in this MVP.</small></div><span className="coming-soon">Coming later</span></div></div>
          </section>}

          {error && <div className="error-banner"><X size={16}/><span>{error}</span><button onClick={() => setError("")}><X size={15}/></button></div>}
          {toast && <div className="toast"><CheckCircle2 size={16}/>{toast}</div>}
          <footer className="footer">
            <span>© 2026 ClipRush AI</span>
            <nav className="footer-guides" aria-label="Creator guides">
              <a href="/blog/">Creator Guides</a>
              <a href="/gta-clipping/">GTA Clipping</a>
              <a href="/ai-video-clip-generator/">AI Clip Generator</a>
              <a href="/youtube-shorts-generator/">YouTube Shorts</a>
              <a href="/podcast-clip-maker/">Podcast Clips</a>
              <a href="/long-video-to-short-clips/">Long to Short</a>
              <a href="/ai-video-highlights/">AI Highlights</a>
            </nav>
            <span className="footer-version">MVP · v0.2</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
export default App;
