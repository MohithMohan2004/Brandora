import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

function Slider({ label, value, min, max, step = 1, unit = "", onChange, disabled }) {
  return (
    <div className="slider-row">
      <div className="top">
        <span>{label}</span>
        <span>{Number(value).toFixed(step < 1 ? 2 : 0)}{unit}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))} aria-label={label} />
    </div>
  );
}

function Color({ label, value, onChange, disabled }) {
  return (
    <div className="field">
      <label>{label}</label>
      <input type="color" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

const TABS = [
  ["headline", "Headline"],
  ["copy", "Ad copy"],
  ["cta", "CTA button"],
  ["background", "Bands"],
];

// The poster as last kept by the user, or the generated design if nothing was kept yet.
export const keptPoster = (editor) => structuredClone(editor.saved ?? { layers: editor.layers, scrim: editor.scrim });
export const sameConfig = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// The draft lives in App, so edits survive switching steps; "Keep changes" stores it on the server.
export default function PosterStudio({ gen, editor, setEditor, draft, setDraft, onError }) {
  const { layers, scrim } = draft;
  const [fonts, setFonts] = useState(editor.fonts);
  const [tab, setTab] = useState("headline");
  const [guides, setGuides] = useState(true);
  const [preview, setPreview] = useState("");
  const [rendering, setRendering] = useState(false);
  const [saving, setSaving] = useState(false);
  const shownAt = useRef(Date.now());
  const previewUrl = useRef("");

  const status = editor.status || "review"; // review | approved | rejected
  const locked = status !== "review";
  const kept = keptPoster(editor);
  const dirty = !sameConfig(draft, kept);
  const designed = { layers: editor.layers, scrim: editor.scrim };
  const setLayers = (fn) => setDraft((d) => ({ ...d, layers: fn(d.layers) }));
  const setScrim = (next) => setDraft((d) => ({ ...d, scrim: next }));

  // Live preview: debounce edits, cancel stale requests, never show the raw image.
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setRendering(true);
      try {
        const blob = await api.renderPoster(gen.id, { layers, scrim }, guides && !locked, controller.signal);
        const url = URL.createObjectURL(blob);
        if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
        previewUrl.current = url;
        setPreview(url);
      } catch (err) {
        if (err.name !== "AbortError") onError(err.message);
      } finally {
        if (!controller.signal.aborted) setRendering(false);
      }
    }, 280);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [layers, scrim, guides, locked, gen.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => previewUrl.current && URL.revokeObjectURL(previewUrl.current), []);

  const setLayer = (name, patch) => setLayers((prev) => ({ ...prev, [name]: { ...prev[name], ...patch } }));
  const resetToDesign = () => setDraft(structuredClone(designed));
  const discard = () => setDraft(kept);

  const keep = async () => {
    setSaving(true);
    try {
      const res = await api.savePoster(gen.id, draft);
      setEditor((e) => ({ ...e, saved: structuredClone(draft), saved_at: res.saved_at, status: "review" }));
    } catch (err) {
      onError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const decide = async (decision) => {
    setSaving(true);
    try {
      const seconds = (Date.now() - shownAt.current) / 1000;
      const res = await api.review(gen.id, decision, draft, seconds);
      setEditor((e) => ({ ...e, saved: structuredClone(draft), saved_at: res.saved_at, status: decision }));
    } catch (err) {
      onError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const reopen = async () => {
    try {
      await api.reopenPoster(gen.id);
      setEditor((e) => ({ ...e, status: "review" }));
    } catch (err) {
      onError(err.message);
    }
  };

  const addFont = async (file) => {
    if (!file) return;
    try {
      const res = await api.uploadFont(file);
      setFonts(res.fonts);
      setLayer(tab === "background" ? "headline" : tab, { font: res.font });
    } catch (err) {
      onError(err.message);
    }
  };

  const L = layers[tab];

  return (
    <div className="studio">
      <div className="panel">
        <div className="tabs" role="tablist">
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} className={`tab ${tab === id ? "active" : ""}`} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </div>

        <div className="panel-body">
          {tab !== "background" && L && (
            <>
              <div className="field">
                <label htmlFor={`text-${tab}`}>{tab === "cta" ? "Button text" : tab === "copy" ? "Ad copy" : "Headline"}</label>
                <textarea id={`text-${tab}`} className="textarea" rows={tab === "copy" ? 4 : 2} value={L.text} disabled={locked}
                  onChange={(e) => setLayer(tab, { text: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor={`font-${tab}`}>Font</label>
                <select id={`font-${tab}`} className="select" value={L.font} disabled={locked}
                  onChange={(e) => setLayer(tab, { font: e.target.value })}>
                  {fonts.map((f) => <option key={f} value={f}>{f}</option>)}
                  {!fonts.length && <option value="">Built-in default</option>}
                </select>
                <label className="btn sm ghost" style={{ marginTop: 6, cursor: "pointer" }}>
                  Add a font file (.ttf / .otf)
                  <input type="file" accept=".ttf,.otf" hidden disabled={locked} onChange={(e) => { addFont(e.target.files[0]); e.target.value = ""; }} />
                </label>
              </div>
              <div className="row2">
                <Slider label="Size" value={L.size} min={12} max={160} disabled={locked} onChange={(v) => setLayer(tab, { size: v })} />
                <Color label="Text colour" value={L.color} disabled={locked} onChange={(v) => setLayer(tab, { color: v })} />
              </div>
              <Slider label="Horizontal position" unit="%" value={L.x} min={0} max={100} disabled={locked} onChange={(v) => setLayer(tab, { x: v })} />
              <Slider label="Vertical position" unit="%" value={L.y} min={0} max={100} disabled={locked} onChange={(v) => setLayer(tab, { y: v })} />

              {tab !== "cta" ? (
                <>
                  <Slider label="Text box width" unit="%" value={L.width} min={20} max={100} disabled={locked} onChange={(v) => setLayer(tab, { width: v })} />
                  <div className="field">
                    <label>Alignment</label>
                    <div className="segmented" role="radiogroup" aria-label="Alignment">
                      {["left", "center", "right"].map((a) => (
                        <button key={a} role="radio" aria-checked={L.align === a} className={L.align === a ? "on" : ""} disabled={locked} onClick={() => setLayer(tab, { align: a })}>{a}</button>
                      ))}
                    </div>
                  </div>
                  <Slider label="Line spacing" value={L.line_spacing} min={0.9} max={2} step={0.05} disabled={locked} onChange={(v) => setLayer(tab, { line_spacing: v })} />
                  <Slider label="Text opacity" value={L.opacity} min={0.1} max={1} step={0.05} disabled={locked} onChange={(v) => setLayer(tab, { opacity: v })} />
                  <label className="check">
                    <input type="checkbox" checked={L.shadow} disabled={locked} onChange={(e) => setLayer(tab, { shadow: e.target.checked })} />
                    Drop shadow
                  </label>
                  <div className="row2">
                    <Slider label="Outline" value={L.stroke} min={0} max={8} disabled={locked} onChange={(v) => setLayer(tab, { stroke: v })} />
                    <Color label="Outline colour" value={L.stroke_color} disabled={locked} onChange={(v) => setLayer(tab, { stroke_color: v })} />
                  </div>
                </>
              ) : (
                <>
                  <Color label="Button colour" value={L.button_color} disabled={locked} onChange={(v) => setLayer("cta", { button_color: v })} />
                  <div className="row2">
                    <Slider label="Corner radius" value={L.radius} min={0} max={60} disabled={locked} onChange={(v) => setLayer("cta", { radius: v })} />
                    <Slider label="Padding" value={L.pad} min={10} max={80} disabled={locked} onChange={(v) => setLayer("cta", { pad: v })} />
                  </div>
                </>
              )}
            </>
          )}

          {tab === "background" && (
            <>
              <p className="stage-hint" style={{ color: "var(--ink-3)" }}>
                Soft colour bands behind the text keep it readable on any photo.
              </p>
              <Color label="Band colour" value={scrim.color} disabled={locked} onChange={(v) => setScrim({ ...scrim, color: v })} />
              <Slider label="Band strength" value={scrim.strength} min={0} max={1} step={0.05} disabled={locked} onChange={(v) => setScrim({ ...scrim, strength: v })} />
              <Slider label="Top band height" unit="px" value={scrim.top_h} min={0} max={600} disabled={locked} onChange={(v) => setScrim({ ...scrim, top_h: v })} />
              <Slider label="Bottom band height" unit="px" value={scrim.bottom_h} min={0} max={700} disabled={locked} onChange={(v) => setScrim({ ...scrim, bottom_h: v })} />
            </>
          )}
        </div>

        <div className="panel-foot">
          <label className="check">
            <input type="checkbox" checked={guides} disabled={locked} onChange={(e) => setGuides(e.target.checked)} />
            Show position guides
          </label>
          <button className="btn sm" onClick={resetToDesign} disabled={locked || sameConfig(draft, designed)}
            title="Go back to the generated design (keep changes afterwards to make it stick)">
            Reset to design
          </button>
        </div>
      </div>

      <div className="stage">
        <div className="stage-canvas">
          {preview && <img src={preview} alt="Poster preview" />}
          {rendering && <div className="busy"><span className="spinner" /> Updating</div>}
        </div>

        {editor.design && (
          <p className="stage-hint">
            Designed in a <b>{editor.design.style}</b> style: {editor.design.headline} with {editor.design.body}.
          </p>
        )}
        {editor.image_check?.verdict && (
          editor.image_check.verdict.lettering ? (
            <div className="alert warn">
              The photo may still contain stray lettering after {editor.image_check.attempts} tries. Generate the image again for a cleaner one.
            </div>
          ) : (
            <p className="stage-hint">
              Photo checked: no lettering{editor.image_check.verdict.cluttered ? "" : ", tidy composition"}
              {editor.image_check.attempts > 1 ? ` (best of ${editor.image_check.attempts} tries)` : ""}. All words are typeset by Brandora.
            </p>
          )
        )}

        {status === "review" && (
          <>
            <div className="save-bar">
              <span className={`save-state ${dirty ? "dirty" : ""}`}>
                {dirty ? "Unsaved changes" : editor.saved_at ? `Changes kept · ${editor.saved_at.replace("T", " ").slice(0, 16)}` : "Generated design"}
              </span>
              <button className="btn sm" onClick={discard} disabled={!dirty || saving}>Discard</button>
              <button className="btn sm primary" onClick={keep} disabled={!dirty || saving}>
                {saving ? <><span className="spinner" /> Keeping…</> : "Keep changes"}
              </button>
            </div>
            <div className="stage-actions">
              <button className="btn ok" onClick={() => decide("approved")} disabled={saving || rendering}>Approve poster</button>
              <button className="btn" onClick={() => decide("rejected")} disabled={saving}>Reject</button>
            </div>
            <p className="stage-hint">
              Kept changes come back when you return to this step or reopen Brandora. Approving also keeps them and unlocks
              the download. Every decision, and whether you edited the text, is saved to review_log.jsonl.
            </p>
          </>
        )}
        {status === "approved" && (
          <>
            <div className="alert ok">Approved and logged. The final poster is ready.</div>
            <div className="stage-actions">
              <a className="btn primary" href={api.downloadUrl(gen.id)} download>Download poster</a>
              <button className="btn" onClick={reopen}>Edit again</button>
            </div>
          </>
        )}
        {status === "rejected" && (
          <>
            <div className="alert warn">Rejected and logged. Edit your brief and generate again.</div>
            <button className="btn" onClick={reopen}>Keep editing</button>
          </>
        )}
      </div>
    </div>
  );
}
