// Thin client for the FastAPI backend (backend/app.py).
//
// In the browser the UI and the API share an origin, so paths stay relative.
// Inside the Android app the UI is bundled with the APK and the API lives on the
// computer running ./start.sh --lan, so every path is prefixed with that address.
export const isApp = typeof window !== "undefined" && window.location.hostname === "appassets.androidplatform.net";

const SERVER_KEY = "brandora.server";
const readServer = () => {
  try { return localStorage.getItem(SERVER_KEY) || ""; } catch { return ""; }
};
let base = isApp ? readServer() : "";

export const getServer = () => base;
export const normalizeServer = (value) => {
  let v = String(value || "").trim().replace(/\/+$/, "");
  if (!v) return "";
  if (!/^https?:\/\//i.test(v)) v = `http://${v}`;
  if (!/:\d+$/.test(v.replace(/^https?:\/\//i, "")) && /^http:/i.test(v)) v = `${v}:8000`;
  return v;
};
export const setServer = (value) => {
  base = normalizeServer(value);
  try { localStorage.setItem(SERVER_KEY, base); } catch { /* storage unavailable */ }
};

// Absolute URL for links and downloads (the Android app hands these to the system downloader).
export const apiUrl = (path) => `${base}/api${path}`;

async function request(path, options = {}) {
  if (isApp && !base) throw new Error("Connect to your Brandora server first.");
  let res;
  try {
    res = await fetch(apiUrl(path), options);
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new Error(isApp
      ? `Can't reach the Brandora server at ${base}. Check that ./start.sh --lan is running and the phone is on the same Wi-Fi.`
      : "Can't reach the Brandora server. Is ./start.sh still running?");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return res;
}

const json = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  config: () => request("/config").then((r) => r.json()),
  probe: (server) => fetch(`${normalizeServer(server)}/api/config`, { signal: AbortSignal.timeout(6000) })
    .then((r) => { if (!r.ok) throw new Error(`Server answered ${r.status}`); return r.json(); }),
  catalogue: () => request("/catalogue").then((r) => r.json()),
  generate: (prompt, top_k) => request("/generate", json({ prompt, top_k })).then((r) => r.json()),
  generation: (id) => request(`/generations/${id}`).then((r) => r.json()),
  history: () => request("/generations").then((r) => r.json()),
  deleteGeneration: (id) => request(`/generations/${id}`, { method: "DELETE" }).then((r) => r.json()),
  generateImage: (id) => request(`/generations/${id}/image`, { method: "POST" }).then((r) => r.json()),
  savePoster: (id, config) =>
    request(`/generations/${id}/poster/saved`, { ...json({ config }), method: "PUT" }).then((r) => r.json()),
  relayoutPoster: (id, texts) =>
    request(`/generations/${id}/poster/relayout`, json({ texts })).then((r) => r.json()),
  reopenPoster: (id) => request(`/generations/${id}/poster/reopen`, { method: "POST" }).then((r) => r.json()),
  renderPoster: (id, config, guides, signal) =>
    request(`/generations/${id}/poster/render`, { ...json({ config, guides }), signal }).then((r) => r.blob()),
  review: (id, decision, config, seconds, threshold) =>
    request(`/generations/${id}/poster/review`, json({ decision, config, seconds, threshold })).then((r) => r.json()),
  relevance: (id, refresh = false) =>
    request(`/generations/${id}/relevance${refresh ? "?refresh=true" : ""}`, { method: "POST" }).then((r) => r.json()),
  uploadFont: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/fonts", { method: "POST", body: form }).then((r) => r.json());
  },
  transcribe: (wav) => {
    const form = new FormData();
    form.append("file", wav, "brief.wav");
    return request("/transcribe", { method: "POST", body: form }).then((r) => r.json());
  },
  speech: (id, text) => request(`/generations/${id}/speech`, json({ text })).then((r) => r.blob()),
  autoLayoutUrl: (id, download = false) => apiUrl(`/generations/${id}/auto-layout.png${download ? "?download=true" : ""}`),
  downloadUrl: (id) => apiUrl(`/generations/${id}/poster/download.png`),
  briefUrl: (id) => apiUrl(`/generations/${id}/brief.txt`),
  thumbUrl: (id, version) => apiUrl(`/generations/${id}/thumb.jpg?v=${version}`),
};
