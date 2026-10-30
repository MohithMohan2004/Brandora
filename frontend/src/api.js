// Thin client for the FastAPI backend (backend/app.py).
async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, options);
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
  catalogue: () => request("/catalogue").then((r) => r.json()),
  generate: (prompt, top_k) => request("/generate", json({ prompt, top_k })).then((r) => r.json()),
  generation: (id) => request(`/generations/${id}`).then((r) => r.json()),
  generateImage: (id) => request(`/generations/${id}/image`, { method: "POST" }).then((r) => r.json()),
  savePoster: (id, config) =>
    request(`/generations/${id}/poster/saved`, { ...json({ config }), method: "PUT" }).then((r) => r.json()),
  reopenPoster: (id) => request(`/generations/${id}/poster/reopen`, { method: "POST" }).then((r) => r.json()),
  renderPoster: (id, config, guides, signal) =>
    request(`/generations/${id}/poster/render`, { ...json({ config, guides }), signal }).then((r) => r.blob()),
  review: (id, decision, config, seconds) =>
    request(`/generations/${id}/poster/review`, json({ decision, config, seconds })).then((r) => r.json()),
  uploadFont: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/fonts", { method: "POST", body: form }).then((r) => r.json());
  },
  speech: (id, text) => request(`/generations/${id}/speech`, json({ text })).then((r) => r.blob()),
  autoLayoutUrl: (id, download = false) => `/api/generations/${id}/auto-layout.png${download ? "?download=true" : ""}`,
  downloadUrl: (id) => `/api/generations/${id}/poster/download.png`,
};
