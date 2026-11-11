import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import Icon from "../icons.jsx";
import { ColorField, Kbd, MOD, MenuItem, Popover, Segmented, Slider, Switch, useToast } from "../ui.jsx";
import Toolbar from "./Toolbar.jsx";
import { RelevanceStrip, band } from "./Relevance.jsx";
import { keptPoster, sameConfig } from "./poster-state.js";

const TABS = [
  { value: "headline", label: "Headline" },
  { value: "copy", label: "Copy" },
  { value: "cta", label: "Button" },
  { value: "background", label: "Bands" },
];

// Poster step: the photo prompt until an image exists, then the studio.
export default function PosterView(props) {
  const { editor, draft } = props;
  return editor && draft ? <Studio {...props} /> : <EmptyPoster {...props} />;
}

function EmptyPoster({ busy, onGenerateImage, cloudflareReady }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!busy) return setElapsed(0);
    const start = Date.now();
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 500);
    return () => clearInterval(t);
  }, [busy]);

  return (
    <>
      <Toolbar title="Poster" subtitle="Step 3 of 3" />
      <div className="page">
        <div className="empty-state">
          <span className="empty-icon"><Icon name="image" size={28} /></span>
          <h2>Generate the photo</h2>
          <p>
            Brandora turns the visual direction into a plain photo description with no words or logos, checks each
            photo for stray lettering and clutter, then typesets your headline, copy and button around the product.
          </p>
          {cloudflareReady === false && (
            <div className="inline-note warn"><Icon name="alert" size={16} />
              <span>Add CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN to .env to enable image generation.</span></div>
          )}
          <button className="btn primary lg" onClick={onGenerateImage} disabled={busy}>
            {busy ? <><span className="spinner xs" /> {elapsed < 6 ? "Describing the scene" : "Generating and checking the photo"}… {elapsed}s</>
              : <><Icon name="sparkle" size={16} /> Generate photo</>}
          </button>
        </div>
      </div>
    </>
  );
}

function Studio({ gen, editor, setEditor, draft, setDraft, busy, onGenerateImage, onSaved, relevance }) {
  const toast = useToast();
  const { layers, scrim } = draft;
  const [fonts, setFonts] = useState(editor.fonts);
  const [tab, setTab] = useState("headline");
  const [guides, setGuides] = useState(false);
  const [preview, setPreview] = useState("");
  const [rendering, setRendering] = useState(false);
  const [saving, setSaving] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const shownAt = useRef(Date.now());
  const previewUrl = useRef("");
  const menuRef = useRef(null);
  const approveRef = useRef(null);

  const status = editor.status || "review"; // review | approved | rejected
  const locked = status !== "review";
  const kept = keptPoster(editor);
  const dirty = !sameConfig(draft, kept);
  const designed = { layers: editor.layers, scrim: editor.scrim };
  const report = relevance?.report;
  const belowBar = Boolean(report && report.score < relevance.threshold);

  const setLayers = (fn) => setDraft((d) => ({ ...d, layers: fn(d.layers) }));
  const setScrim = (next) => setDraft((d) => ({ ...d, scrim: next }));
  const setLayer = (name, patch) => setLayers((prev) => ({ ...prev, [name]: { ...prev[name], ...patch } }));

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
        if (err.name !== "AbortError") toast({ kind: "error", text: err.message });
      } finally {
        if (!controller.signal.aborted) setRendering(false);
      }
    }, 220);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [layers, scrim, guides, locked, gen.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => previewUrl.current && URL.revokeObjectURL(previewUrl.current), []);

  const keep = useCallback(async () => {
    if (!dirty || saving || locked) return;
    setSaving(true);
    try {
      const res = await api.savePoster(gen.id, draft);
      setEditor((e) => ({ ...e, saved: structuredClone(draft), saved_at: res.saved_at, status: "review" }));
      toast({ kind: "ok", text: "Changes kept. Relevance will update for the new text." });
      onSaved?.();
    } catch (err) {
      toast({ kind: "error", text: err.message });
    } finally {
      setSaving(false);
    }
  }, [dirty, saving, locked, gen.id, draft, setEditor, toast, onSaved]);

  // Cmd/Ctrl+S keeps changes, as in any editor.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        keep();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [keep]);

  const decide = async (decision) => {
    setConfirmOpen(false);
    setSaving(true);
    try {
      const seconds = (Date.now() - shownAt.current) / 1000;
      const res = await api.review(gen.id, decision, draft, seconds, relevance?.threshold);
      setEditor((e) => ({ ...e, saved: structuredClone(draft), saved_at: res.saved_at, status: decision }));
      toast(decision === "approved"
        ? { kind: "ok", text: "Approved and logged. The download is ready." }
        : { kind: "info", text: "Rejected and logged. Edit the brief or rewrite the copy to try again." });
      onSaved?.();
    } catch (err) {
      toast({ kind: "error", text: err.message });
    } finally {
      setSaving(false);
    }
  };

  // A poster under the user's relevance bar gets one explicit confirmation first.
  const approve = () => (belowBar ? setConfirmOpen(true) : decide("approved"));

  const reopen = async () => {
    try {
      await api.reopenPoster(gen.id);
      setEditor((e) => ({ ...e, status: "review" }));
    } catch (err) {
      toast({ kind: "error", text: err.message });
    }
  };

  const addFont = async (file) => {
    if (!file) return;
    try {
      const res = await api.uploadFont(file);
      setFonts(res.fonts);
      setLayer(tab === "background" ? "headline" : tab, { font: res.font });
      toast({ kind: "ok", text: `Added ${res.font}.` });
    } catch (err) {
      toast({ kind: "error", text: err.message });
    }
  };

  const newPhoto = () => {
    setMenuOpen(false);
    if (dirty && !window.confirm("A new photo restarts the layout. Your text is kept, but other unsaved changes are lost. Continue?")) return;
    onGenerateImage();
  };

  const closeMenu = useCallback(() => setMenuOpen(false), []);
  const closeConfirm = useCallback(() => setConfirmOpen(false), []);

  const saveState = status === "approved" ? "Approved"
    : status === "rejected" ? "Rejected"
    : dirty ? "Unsaved changes"
    : editor.saved_at ? `Kept ${editor.saved_at.slice(11, 16)}` : "Generated design";

  const L = layers[tab];
  const check = editor.image_check || {};

  return (
    <>
      <Toolbar title="Poster" subtitle={<span className={`save-state ${dirty && !locked ? "dirty" : ""} s-${status}`}>{saveState}</span>}>
        <button ref={menuRef} className="icon-btn" onClick={() => setMenuOpen((o) => !o)} aria-label="More poster actions"
          aria-expanded={menuOpen} title="More">
          <Icon name="more" />
        </button>
        <Popover open={menuOpen} onClose={closeMenu} anchorRef={menuRef} placement="bottom-end" width={250} label="Poster actions">
          <div className="menu">
            <MenuItem icon="sparkle" onClick={newPhoto} disabled={busy || locked}>New photo</MenuItem>
            <MenuItem icon="undo" onClick={() => { setDraft(structuredClone(designed)); setMenuOpen(false); }}
              disabled={locked || sameConfig(draft, designed)}>Reset to generated design</MenuItem>
            <div className="menu-sep" />
            <MenuItem icon="download" href={api.autoLayoutUrl(gen.id, true)} download onClick={() => setMenuOpen(false)}>
              Download auto-layout
            </MenuItem>
          </div>
        </Popover>

        {status === "review" && (
          <>
            {dirty && <button className="btn ghost hide-sm" onClick={() => setDraft(kept)} disabled={saving}>Discard</button>}
            <button className="btn" onClick={keep} disabled={!dirty || saving} title={`Keep changes (${MOD} + S)`}>
              {saving && dirty ? <span className="spinner xs" /> : <Icon name="check" size={16} />}
              <span className="hide-sm">Keep</span>{dirty && <Kbd>{MOD} S</Kbd>}
            </button>
            <span className="toolbar-sep" />
            <button className="btn ghost danger" onClick={() => decide("rejected")} disabled={saving}>Reject</button>
            <button ref={approveRef} className={`btn ${belowBar ? "warn" : "ok"}`} onClick={approve} disabled={saving || rendering || busy}>
              <Icon name="thumbUp" size={16} /> Approve
            </button>
            <Popover open={confirmOpen} onClose={closeConfirm} anchorRef={approveRef} placement="bottom-end" width={320} label="Approve below your bar">
              {report && (
                <div className="confirm">
                  <h2>Approve below your bar?</h2>
                  <p>
                    This poster scores <b>{report.score}</b> ({band(report.score).toLowerCase()}), under your bar of {relevance.threshold}.
                    {report.advice ? ` ${report.advice}` : ""}
                  </p>
                  <div className="confirm-actions">
                    <button className="btn" onClick={closeConfirm}>Keep editing</button>
                    <button className="btn warn" onClick={() => decide("approved")}>Approve anyway</button>
                  </div>
                </div>
              )}
            </Popover>
          </>
        )}
        {status === "approved" && (
          <>
            <button className="btn" onClick={reopen}><Icon name="edit" size={16} /> <span className="hide-sm">Edit again</span></button>
            <a className="btn primary" href={api.downloadUrl(gen.id)} download><Icon name="download" size={16} /> Download PNG</a>
          </>
        )}
        {status === "rejected" && (
          <button className="btn primary" onClick={reopen}><Icon name="edit" size={16} /> Keep editing</button>
        )}
      </Toolbar>

      <div className="studio">
        <section className="panel inspector" aria-label="Poster editor">
          <div className="inspector-tabs">
            <Segmented label="Layer" options={TABS} value={tab} onChange={setTab} size="sm" />
          </div>

          <div className="inspector-body">
            {tab !== "background" && L && (
              <>
                <div className="group">
                  <label className="field">
                    <span className="field-label">{tab === "cta" ? "Button text" : tab === "copy" ? "Ad copy" : "Headline"}</span>
                    <textarea className="input" rows={tab === "copy" ? 4 : 2} value={L.text} disabled={locked}
                      onChange={(e) => setLayer(tab, { text: e.target.value })} />
                  </label>
                </div>

                <div className="group">
                  <h3 className="group-title">Type</h3>
                  <div className="font-row">
                    <select className="input" value={L.font} disabled={locked} aria-label="Font"
                      onChange={(e) => setLayer(tab, { font: e.target.value })}>
                      {fonts.map((f) => <option key={f} value={f}>{f}</option>)}
                      {!fonts.length && <option value="">Built-in default</option>}
                    </select>
                    <label className={`icon-btn bordered ${locked ? "disabled" : ""}`} title="Add a font file (.ttf / .otf)">
                      <Icon name="upload" size={16} />
                      <input type="file" accept=".ttf,.otf" hidden disabled={locked}
                        onChange={(e) => { addFont(e.target.files[0]); e.target.value = ""; }} />
                    </label>
                  </div>
                  <div className="row2">
                    <Slider label="Size" value={L.size} min={12} max={160} disabled={locked} onChange={(v) => setLayer(tab, { size: v })} />
                    <ColorField label="Colour" value={L.color} disabled={locked} onChange={(v) => setLayer(tab, { color: v })} />
                  </div>
                </div>

                <div className="group">
                  <h3 className="group-title">Position</h3>
                  <div className="row2">
                    <Slider label="Across" unit="%" value={L.x} min={0} max={100} disabled={locked} onChange={(v) => setLayer(tab, { x: v })} />
                    <Slider label="Down" unit="%" value={L.y} min={0} max={100} disabled={locked} onChange={(v) => setLayer(tab, { y: v })} />
                  </div>
                  {tab !== "cta" && (
                    <>
                      <Slider label="Box width" unit="%" value={L.width} min={20} max={100} disabled={locked} onChange={(v) => setLayer(tab, { width: v })} />
                      <Segmented label="Alignment" size="sm" disabled={locked} value={L.align} onChange={(a) => setLayer(tab, { align: a })}
                        options={[{ value: "left", label: "Left" }, { value: "center", label: "Centre" }, { value: "right", label: "Right" }]} />
                    </>
                  )}
                </div>

                {tab !== "cta" ? (
                  <div className="group">
                    <h3 className="group-title">Style</h3>
                    <div className="row2">
                      <Slider label="Line spacing" value={L.line_spacing} min={0.9} max={2} step={0.05} disabled={locked} onChange={(v) => setLayer(tab, { line_spacing: v })} />
                      <Slider label="Opacity" value={L.opacity} min={0.1} max={1} step={0.05} disabled={locked} onChange={(v) => setLayer(tab, { opacity: v })} />
                    </div>
                    <div className="row2">
                      <Slider label="Outline" value={L.stroke} min={0} max={8} disabled={locked} onChange={(v) => setLayer(tab, { stroke: v })} />
                      <ColorField label="Outline colour" value={L.stroke_color} disabled={locked} onChange={(v) => setLayer(tab, { stroke_color: v })} />
                    </div>
                    <Switch label="Drop shadow" checked={L.shadow} disabled={locked} onChange={(v) => setLayer(tab, { shadow: v })} />
                  </div>
                ) : (
                  <div className="group">
                    <h3 className="group-title">Button</h3>
                    <ColorField label="Button colour" value={L.button_color} disabled={locked} onChange={(v) => setLayer("cta", { button_color: v })} />
                    <div className="row2">
                      <Slider label="Corner radius" value={L.radius} min={0} max={60} disabled={locked} onChange={(v) => setLayer("cta", { radius: v })} />
                      <Slider label="Padding" value={L.pad} min={10} max={80} disabled={locked} onChange={(v) => setLayer("cta", { pad: v })} />
                    </div>
                  </div>
                )}
              </>
            )}

            {tab === "background" && (
              <div className="group">
                <p className="muted small">Soft colour bands behind the text keep it readable on any photo.</p>
                <ColorField label="Band colour" value={scrim.color} disabled={locked} onChange={(v) => setScrim({ ...scrim, color: v })} />
                <Slider label="Strength" value={scrim.strength} min={0} max={1} step={0.05} disabled={locked} onChange={(v) => setScrim({ ...scrim, strength: v })} />
                <div className="row2">
                  <Slider label="Top band" unit="px" value={scrim.top_h} min={0} max={600} disabled={locked} onChange={(v) => setScrim({ ...scrim, top_h: v })} />
                  <Slider label="Bottom band" unit="px" value={scrim.bottom_h} min={0} max={700} disabled={locked} onChange={(v) => setScrim({ ...scrim, bottom_h: v })} />
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="stage" aria-label="Poster preview">
          <div className="canvas">
            {preview ? <img src={preview} alt="Poster preview" /> : <div className="canvas-placeholder"><span className="spinner" /></div>}
          </div>

          <div className="stage-bar">
            <ul className="facts">
              {editor.design && (
                <li title={`${editor.design.headline} with ${editor.design.body}`}>
                  <Icon name="copy" size={13} /> <span><span className="cap">{editor.design.style}</span> type</span> · {editor.design.headline} / {editor.design.body}
                </li>
              )}
              {check.verdict && (
                check.verdict.lettering
                  ? <li className="warn-ink"><Icon name="alert" size={13} /> Photo may contain stray lettering. Try a new photo.</li>
                  : <li><Icon name="check" size={13} /> No lettering{check.verdict.cluttered ? "" : ", tidy"}
                    {check.attempts > 1 ? ` · best of ${check.attempts}` : ""}</li>
              )}
              {check.fallback && (
                <li className="warn-ink" title="The main image model was unavailable">
                  <Icon name="info" size={13} /> Made with {check.model.split("/").pop()}
                </li>
              )}
            </ul>
            <div className="stage-tools">
              {(rendering || busy) && <span className="muted small nowrap"><span className="spinner xs" /> {busy ? "New photo…" : "Updating"}</span>}
              {!locked && (
                <button className={`chip-btn ${guides ? "on" : ""}`} onClick={() => setGuides((g) => !g)} aria-pressed={guides}
                  title="Show position guides on the preview">
                  <Icon name="grid" size={14} /> Guides
                </button>
              )}
            </div>
          </div>

          <RelevanceStrip report={report} state={relevance?.state} threshold={relevance?.threshold ?? 70}
            dirty={dirty && status === "review"} onRefresh={relevance?.onRefresh} />
        </section>
      </div>
    </>
  );
}
