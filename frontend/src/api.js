// Thin API client: readable errors, upload progress and resilient job polling.
export const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
export const apiUrl = (path) => `${BASE}${path}`;

function errorMessage(data, status) {
  const detail = data?.detail ?? data?.message;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (d?.msg ? `${(d.loc || []).slice(1).join(" › ") || "Input"}: ${d.msg}` : String(d))).join("; ");
  }
  if (status === 401) return "Your sign-in expired. Reload the page and sign in again.";
  if (status === 413) return "That file is too large for this server.";
  if ([502, 503, 504].includes(status)) return "The server is busy or restarting. Please try again in a moment.";
  return `Request failed (${status})`;
}

export async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(apiUrl(path), { credentials: BASE ? "include" : "same-origin", ...options });
  } catch {
    throw new Error("Can't reach the server. Check your connection, or that the backend is running.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(errorMessage(data, response.status));
  return data;
}

export const jsonBody = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** Upload with real progress (fetch can't report upload progress). Returns { promise, abort }. */
export function uploadFile(file, onProgress) {
  const xhr = new XMLHttpRequest();
  const promise = new Promise((resolve, reject) => {
    xhr.open("POST", apiUrl("/api/videos"));
    xhr.withCredentials = !!BASE;
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onerror = () => reject(new Error("Upload failed. Check your connection and try again."));
    xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
    xhr.ontimeout = () => reject(new Error("The upload timed out."));
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch { /* non-JSON error page */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new Error(errorMessage(data, xhr.status)));
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
  return { promise, abort: () => xhr.abort() };
}

const sleep = (ms, signal) =>
  new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => { clearTimeout(t); reject(new DOMException("aborted", "AbortError")); }, { once: true });
  });

/**
 * Poll a job until it finishes. Tolerates brief outages (e.g. a free-tier server waking up)
 * instead of failing on the first bad response.
 */
export async function pollJob(jobId, onUpdate, { signal, intervalMs = 1500, maxFailures = 15 } = {}) {
  let failures = 0;
  for (;;) {
    await sleep(intervalMs, signal);
    let job;
    try {
      job = await request(`/api/jobs/${jobId}`);
      failures = 0;
    } catch (err) {
      if (++failures >= maxFailures) throw err;
      continue;
    }
    onUpdate(job);
    if (job.status === "completed" || job.status === "failed") return job;
  }
}
