import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Film, HelpCircle, Home, Menu, Scissors, Settings, WandSparkles, X, Zap } from "lucide-react";
import { jsonBody, pollJob, request, uploadFile } from "./api";
import { HelpModal, Toasts } from "./components";
import { Create, Library, Overview, SettingsView } from "./views";
import { DEFAULT_OPTS, loadJSON, saveJSON, validateOpts } from "./utils";

const PREFS_KEY = "cliprush.prefs";
const ACTIVE_JOB_KEY = "cliprush.activeJob";
const ALLOWED_EXT = [".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"];

const NAV = [
  { id: "overview", name: "Overview", icon: Home },
  { id: "create", name: "Create clips", icon: WandSparkles },
  { id: "library", name: "My clips", icon: Film },
  { id: "settings", name: "Settings", icon: Settings },
];

export default function App() {
  const [view, setView] = useState("overview");
  const [mobileNav, setMobileNav] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [health, setHealth] = useState(null);
  const [videos, setVideos] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [opts, setOpts] = useState(() => loadJSON(PREFS_KEY, DEFAULT_OPTS));
  const [sourceMode, setSourceMode] = useState("upload");
  const [file, setFile] = useState(null);
  const [uploadPct, setUploadPct] = useState(null);
  const [url, setUrl] = useState("");
  const [urlInfo, setUrlInfo] = useState(null);
  const [busy, setBusy] = useState("");
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [toasts, setToasts] = useState([]);
  const uploadRef = useRef(null);
  const pollRef = useRef(null);

  const video = useMemo(() => videos.find((v) => v.id === selectedId) || null, [videos, selectedId]);
  const totalClips = useMemo(() => videos.reduce((n, v) => n + (v.clips?.length || 0), 0), [videos]);

  /* ----------------------------------------------------------- helpers */
  const notify = useCallback((message, type = "ok") => {
    const id = crypto.randomUUID?.() ?? String(Math.random());
    setToasts((t) => [...t.slice(-2), { id, message, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), type === "error" ? 6500 : 3500);
  }, []);

  const refreshVideos = useCallback(async () => {
    try {
      const list = await request("/api/videos");
      setVideos(list);
      return list;
    } catch (err) {
      return [];
    }
  }, []);

  const loadHealth = useCallback(async () => {
    try { setHealth(await request("/health")); } catch { setHealth(null); }
  }, []);

  const setOpt = useCallback((key, value) => {
    setOpts((prev) => {
      const next = { ...prev, [key]: value };
      saveJSON(PREFS_KEY, next);
      return next;
    });
  }, []);
  const applyPreset = (preset) => {
    setOpts((prev) => { const next = { ...prev, ...preset.set }; saveJSON(PREFS_KEY, next); return next; });
  };
  const resetPrefs = () => { setOpts(DEFAULT_OPTS); saveJSON(PREFS_KEY, DEFAULT_OPTS); notify("Preferences reset."); };

  const go = (next) => { setView(next); setMobileNav(false); window.scrollTo?.({ top: 0 }); };
  const goCreate = (mode, videoId = null) => {
    if (mode) setSourceMode(mode);
    setSelectedId(videoId);
    setFile(null); setUrl(""); setUrlInfo(null);
    go("create");
  };
  const openProject = (id, navigate = true) => { setSelectedId(id); if (navigate) go("library"); };

  /* ------------------------------------------------------------- jobs */
  async function watchJob(kind, jobId) {
    const controller = new AbortController();
    pollRef.current = controller;
    setJob({ kind, id: jobId, status: "queued", progress: 0, message: "Starting…" });
    saveJSON(ACTIVE_JOB_KEY, { kind, id: jobId });
    let aborted = false;
    try {
      const done = await pollJob(jobId, (j) => setJob({ kind, ...j }), { signal: controller.signal });
      if (done.status === "failed") throw new Error(done.error || "Something went wrong.");
      const list = await refreshVideos();
      setSelectedId(done.video_id);
      if (kind === "import") {
        setUrl(""); setUrlInfo(null);
        notify("Video imported. Choose your settings next.");
      } else {
        const count = done.clips?.length || 0;
        notify(`${count} clip${count === 1 ? "" : "s"} ready.`);
        if (list.some((v) => v.id === done.video_id)) go("library");
      }
    } catch (err) {
      if (err.name === "AbortError") { aborted = true; return; }
      setError(err.message);
      refreshVideos();
    } finally {
      if (!aborted) { setJob(null); localStorage.removeItem(ACTIVE_JOB_KEY); }
    }
  }

  /* ------------------------------------------------------------ actions */
  function pickFile(f) {
    if (!f) { setFile(null); return; }
    const ext = (f.name.toLowerCase().match(/\.[^.]+$/) || [""])[0];
    if (!ALLOWED_EXT.includes(ext)) { setError(`“${ext || f.name}” isn’t supported. Use one of: ${ALLOWED_EXT.join(", ")}.`); return; }
    const limit = health?.max_upload_mb;
    if (limit && f.size > limit * 1024 * 1024) {
      setError(`That file is ${(f.size / 1024 / 1024).toFixed(0)} MB, but this server accepts up to ${limit} MB. Trim or compress it first.`);
      return;
    }
    setError(""); setFile(f);
  }

  async function uploadVideo() {
    if (!file) return setError("Choose a video file first.");
    setError(""); setBusy("upload"); setUploadPct(0);
    const { promise, abort } = uploadFile(file, setUploadPct);
    uploadRef.current = abort;
    try {
      const data = await promise;
      await refreshVideos();
      setSelectedId(data.id);
      setFile(null);
      notify("Video uploaded. Choose your settings next.");
    } catch (err) {
      if (err.name !== "AbortError") setError(err.message);
    } finally { setBusy(""); setUploadPct(null); uploadRef.current = null; }
  }
  const cancelUpload = () => uploadRef.current?.();

  async function inspectUrl(e) {
    e?.preventDefault();
    setError(""); setUrlInfo(null);
    if (!url.trim()) return setError("Paste a YouTube, Twitch or Kick link first.");
    setBusy("inspect");
    try { setUrlInfo(await request("/api/sources/inspect", jsonBody("POST", { url: url.trim() }))); }
    catch (err) { setError(err.message); }
    finally { setBusy(""); }
  }

  async function importUrl() {
    setError("");
    try {
      const started = await request("/api/sources/download", jsonBody("POST", { url: url.trim() }));
      watchJob("import", started.job_id);
    } catch (err) { setError(err.message); }
  }

  async function generate() {
    const problem = validateOpts(opts, video);
    if (problem) return setError(problem);
    setError("");
    try {
      const started = await request(`/api/videos/${video.id}/analyze`, jsonBody("POST", {
        ...opts,
        clip_count: Number(opts.clip_count), min_duration: Number(opts.min_duration), max_duration: Number(opts.max_duration),
        language: opts.language || null, guidance: opts.guidance.trim(),
      }));
      watchJob("analyze", started.job_id);
    } catch (err) { setError(err.message); }
  }

  async function deleteProject(v) {
    if (!window.confirm(`Delete “${v.filename}” and all of its clips? This can’t be undone.`)) return;
    try {
      await request(`/api/videos/${v.id}`, { method: "DELETE" });
      if (selectedId === v.id) setSelectedId(null);
      await refreshVideos();
      notify("Project deleted.");
    } catch (err) { setError(err.message); }
  }

  async function deleteClip(v, clip) {
    if (!window.confirm("Delete this clip? This can’t be undone.")) return;
    try {
      await request(`/api/videos/${v.id}/clips/${clip.id}`, { method: "DELETE" });
      await refreshVideos();
      notify("Clip deleted.");
    } catch (err) { setError(err.message); }
  }

  async function clearAll() {
    if (!window.confirm(`Delete all ${videos.length} project(s) and every generated clip? This can’t be undone.`)) return;
    const results = await Promise.allSettled(videos.map((v) => request(`/api/videos/${v.id}`, { method: "DELETE" })));
    setSelectedId(null);
    await refreshVideos();
    const failed = results.filter((r) => r.status === "rejected").length;
    failed ? setError(`${failed} project(s) couldn’t be deleted because they are still being processed.`) : notify("All projects deleted.");
  }

  /* ----------------------------------------------------------- effects */
  useEffect(() => {
    loadHealth();
    refreshVideos();
    const timer = setInterval(loadHealth, 30000);
    // Resume a job that was running when the page was closed or reloaded.
    const active = loadJSON(ACTIVE_JOB_KEY, null);
    if (active?.id) watchJob(active.kind, active.id);
    return () => { clearInterval(timer); pollRef.current?.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (busy !== "upload") return undefined;
    const warn = (e) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [busy]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && setMobileNav(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  /* ------------------------------------------------------------- render */
  const appCtx = {
    view, health, videos, totalClips, selectedId, video, opts, setOpt, applyPreset, resetPrefs,
    sourceMode, setSourceMode, file, pickFile, uploadPct, busy, uploadVideo, cancelUpload,
    url, setUrl, urlInfo, inspectUrl, importUrl, job, generate, notify,
    goCreate, openProject, selectVideo: (id) => setSelectedId(id), clearVideo: () => setSelectedId(null),
    deleteProject, deleteClip, clearAll,
  };
  const current = NAV.find((n) => n.id === view);
  const online = !!health;

  return (
    <div className="app-shell">
      {mobileNav && <div className="nav-backdrop" onClick={() => setMobileNav(false)} />}
      <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`} aria-label="Main navigation">
        <div className="brand">
          <div className="brand-mark"><Scissors size={20} /></div>
          <div><strong>cliprush<span>.ai</span></strong><small>CREATOR STUDIO</small></div>
          <button type="button" className="icon-btn mobile-close" onClick={() => setMobileNav(false)} aria-label="Close menu"><X size={18} /></button>
        </div>
        <div className="workspace-label">WORKSPACE</div>
        <nav>
          {NAV.map(({ id, name, icon: Icon }) => (
            <button type="button" key={id} className={`nav-item ${view === id ? "active" : ""}`} aria-current={view === id ? "page" : undefined}
              onClick={() => { if (id === "create" && view !== "create" && !video) setSelectedId(null); go(id); }}>
              <Icon size={18} /><span>{name}</span>
              {id === "library" && totalClips > 0 && <b className="nav-count">{totalClips}</b>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="plan-card">
            <div className="plan-icon"><Zap size={16} /></div>
            <div>
              <b>{health ? (health.groq_configured ? "Groq connected" : "Groq key missing") : "Server offline"}</b>
              <small>{health?.retention_hours ? `Files auto-delete after ${health.retention_hours} h` : "Private workspace"}</small>
            </div>
            <span className={`plan-dot ${health?.groq_configured ? "" : "warn"}`} />
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <button type="button" className="icon-btn mobile-menu" onClick={() => setMobileNav(true)} aria-label="Open menu"><Menu size={20} /></button>
          <div className="breadcrumb">Workspace <span>/</span> <b>{current?.name}</b></div>
          <div className="top-actions">
            <div className={`api-status ${online ? "online" : "offline"}`} role="status"><span />{online ? "Server connected" : "Server offline"}</div>
            <button type="button" className="help-btn" onClick={() => setHelpOpen(true)} aria-label="How ClipRush works"><HelpCircle size={17} /></button>
          </div>
        </header>

        <div className="page-content" id="main">
          {view === "overview" && <Overview app={appCtx} />}
          {view === "create" && <Create app={appCtx} />}
          {view === "library" && <Library app={appCtx} />}
          {view === "settings" && <SettingsView app={appCtx} />}

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
            <span className="footer-version">v{health?.version || "1.1"}</span>
          </footer>
        </div>
      </main>

      {helpOpen && <HelpModal onClose={() => setHelpOpen(false)} />}
      <Toasts toasts={toasts} error={error} onDismissError={() => setError("")} onDismissToast={(id) => setToasts((t) => t.filter((x) => x.id !== id))} />
    </div>
  );
}
