import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";

const HEALTH = { status: "ok", version: "1.1.0", groq_configured: true, chat_model: "m", transcription_model: "w",
  ffmpeg_available: true, yt_dlp_available: true, max_upload_mb: 500, retention_hours: 12, max_concurrent_jobs: 1 };
const VIDEO = { id: "v1", filename: "podcast.mp4", status: "uploaded", created_at: Date.now() / 1000, clips: [],
  metadata: { duration: 600, width: 1920, height: 1080, size_bytes: 5e6, has_audio: true } };
const CLIP = { id: "c1", filename: "v1_c1.mp4", url: "/clips/v1_c1.mp4", srt_url: "/clips/v1_c1.srt", start: 10, end: 40,
  duration: 30, score: 91, title: "The big reveal", hook: "Wait for it", reason: "Strong payoff", description: "You won't believe it",
  hashtags: ["#wow"], created_at: 1 };

function mockApi(routes) {
  global.fetch = vi.fn(async (url, init = {}) => {
    const path = String(url);
    const key = `${init.method || "GET"} ${path}`;
    const handler = Object.entries(routes).find(([k]) => key === k || (k.endsWith("*") && key.startsWith(k.slice(0, -1))));
    const body = handler ? (typeof handler[1] === "function" ? handler[1](init) : handler[1]) : { detail: `no mock for ${key}` };
    const status = body?.__status || 200;
    return { ok: status < 400, status, json: async () => body };
  });
}

beforeEach(() => vi.restoreAllMocks());

describe("App", () => {
  it("renders overview with live status and navigates every view without crashing", async () => {
    mockApi({ "GET /health": HEALTH, "GET /api/videos": [{ ...VIDEO, clips: [CLIP] }] });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Server connected");
    expect(screen.getByText("Recent projects")).toBeInTheDocument();
    for (const name of ["Create clips", "My clips", "Settings", "Overview"]) {
      await user.click(screen.getByRole("button", { name: new RegExp(name) }));
    }
    expect(screen.getByText("Quick start")).toBeInTheDocument();
  });

  it("shows the score as 0–100 (the old UI multiplied it by 100)", async () => {
    mockApi({ "GET /health": HEALTH, "GET /api/videos": [{ ...VIDEO, clips: [CLIP] }] });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /My clips/ }));
    expect(await screen.findByText("The big reveal")).toBeInTheDocument();
    expect(screen.getByText("91")).toBeInTheDocument();
    expect(screen.queryByText(/9100/)).toBeNull();
    expect(screen.getByRole("link", { name: /Download MP4/ })).toHaveAttribute("href", "/clips/v1_c1.mp4");
    expect(screen.getByText("#wow")).toBeInTheDocument();
  });

  it("generate flow: sends the right payload, shows progress, lands in the library", async () => {
    let analyzeBody;
    let polls = 0;
    mockApi({
      "GET /health": HEALTH,
      "GET /api/videos": () => (polls >= 2 ? [{ ...VIDEO, clips: [CLIP] }] : [VIDEO]),
      "POST /api/videos/v1/analyze": (init) => { analyzeBody = JSON.parse(init.body); return { job_id: "j1", status: "queued" }; },
      "GET /api/jobs/j1": () => {
        polls += 1;
        return polls < 2 ? { id: "j1", status: "rendering", progress: 70, message: "Rendering clip 1 of 2…" }
          : { id: "j1", status: "completed", progress: 100, video_id: "v1", clips: [CLIP] };
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Server connected");
    await user.click(screen.getByRole("button", { name: /Create clips/ }));
    await user.selectOptions(await screen.findByLabelText(/continue with an earlier video/), "v1");
    await user.click(await screen.findByRole("button", { name: /Podcast clips/ }));
    const generate = screen.getByRole("button", { name: /Generate clips/ });
    expect(generate).toBeEnabled();
    await user.click(generate);
    await screen.findByText(/Rendering clip 1 of 2/, {}, { timeout: 5000 });
    expect(screen.getAllByRole("progressbar").length).toBeGreaterThan(0);
    expect(analyzeBody).toMatchObject({ content_type: "podcast", aspect_ratio: "9:16", reframe: "blur", min_duration: 30,
      max_duration: 60, language: null, caption_style: "karaoke" });
    await screen.findByText("The big reveal", {}, { timeout: 8000 });
  }, 15000);

  it("blocks generation and explains why when settings are invalid", async () => {
    mockApi({ "GET /health": HEALTH, "GET /api/videos": [VIDEO] });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Server connected");
    await user.click(screen.getByRole("button", { name: /Create clips/ }));
    await user.selectOptions(await screen.findByLabelText(/continue with an earlier video/), "v1");
    const max = screen.getByLabelText("Maximum seconds");
    await user.clear(max); await user.type(max, "12");
    expect(await screen.findByRole("alert")).toHaveTextContent(/can't be shorter than the minimum/);
    expect(screen.getByRole("button", { name: /Generate clips/ })).toBeDisabled();
  });

  it("surfaces server errors readably and offline state", async () => {
    global.fetch = vi.fn(async () => { throw new TypeError("network"); });
    render(<App />);
    await waitFor(() => expect(screen.getAllByText("Server offline").length).toBeGreaterThan(0));
  });

  it("rejects unsupported files before uploading", async () => {
    mockApi({ "GET /health": HEALTH, "GET /api/videos": [] });
    const user = userEvent.setup({ applyAccept: false });
    const { container } = render(<App />);
    await screen.findByText("Server connected");
    await user.click(screen.getAllByRole("button", { name: /Create clips|Create new clips/ })[0]);
    const input = container.querySelector('input[type="file"]');
    await user.upload(input, new File(["x"], "notes.txt", { type: "text/plain" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/isn’t supported/);
  });
});
