import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import Brief from "./components/Brief.jsx";
import AdResult from "./components/AdResult.jsx";
import PosterStudio, { keptPoster, sameConfig } from "./components/PosterStudio.jsx";
import Evidence from "./components/Evidence.jsx";

const VIEWS = {
  brief: { title: "Write the brief", hint: "Product, audience, tone" },
  ad: { title: "Review the copy", hint: "Headline, copy, CTA" },
  poster: { title: "Design the poster", hint: "Image, layout, approval" },
};

const HEADINGS = {
  brief: ["Brief your campaign", "Describe the product, audience and tone. Brandora checks your catalogue and brand rules before it writes a word."],
  ad: ["Your advertisement", "Copy grounded in your catalogue and guidelines. Read the notes on the right before you build the poster."],
  poster: ["Poster studio", "Generate the visual, then edit the type, colours and layout. Keep your changes, then approve to unlock the download."],
  evidence: ["Evidence", "The exact records Brandora retrieved, plus the full catalogue and guidelines it works from."],
};

// The open advertisement is remembered so a reload (or a server restart) brings it back.
const SESSION_KEY = "brandora.session";
const readSession = () => {
  try { return JSON.parse(localStorage.getItem(SESSION_KEY)) || null; } catch { return null; }
};
const writeSession = (value) => {
  try { localStorage.setItem(SESSION_KEY, JSON.stringify(value)); } catch { /* storage unavailable */ }
};

export default function App() {
  const [config, setConfig] = useState(null);
  const [catalogue, setCatalogue] = useState(null);
  const [view, setView] = useState("brief");
  const [prompt, setPrompt] = useState("");
  const [topK, setTopK] = useState(6);
  const [gen, setGen] = useState(null);
  const [editor, setEditor] = useState(null);
  const [draft, setDraft] = useState(null);   // poster edits in progress (kept ones live in editor.saved)
  const [imageVersion, setImageVersion] = useState(0);
  const [busy, setBusy] = useState(null); // "generate" | "image"
  const [error, setError] = useState("");

  useEffect(() => {
    api.config().then((c) => { setConfig(c); setPrompt((p) => p || c.example_prompt); }).catch((e) => setError(e.message));
    api.catalogue().then(setCatalogue).catch((e) => setError(e.message));

    const session = readSession();
    if (session?.id) {
      api.generation(session.id)
        .then((result) => {
          setGen(result);
          setPrompt(result.prompt);
          openEditor(result.editor);
          setView(session.view === "poster" || session.view === "ad" ? session.view : "ad");
        })
        .catch(() => writeSession(null));
    }
  }, []);

  useEffect(() => { if (gen) writeSession({ id: gen.id, view }); }, [gen, view]);

  const openEditor = (next) => {
    setEditor(next);
    setDraft(next ? keptPoster(next) : null);
  };

  const unsaved = Boolean(editor && draft && !sameConfig(draft, keptPoster(editor)));
  useEffect(() => {
    if (!unsaved) return;
    const warn = (e) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);

  const generate = useCallback(async () => {
    if (!prompt.trim()) return setError("Enter a campaign brief first.");
    setError("");
    setBusy("generate");
    try {
      const result = await api.generate(prompt.trim(), topK);
      setGen(result);
      openEditor(null);
      setView("ad");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  }, [prompt, topK]);

  const generateImage = async () => {
    setError("");
    setBusy("image");
    try {
      const res = await api.generateImage(gen.id);
      openEditor(res.editor);
      setImageVersion((v) => v + 1);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const stepState = (id) => {
    if (id === view) return "current";
    if (id === "brief" && gen) return "done";
    if (id === "ad" && editor) return "done";
    return "";
  };
  const enabled = (id) => id === "brief" || (id === "ad" && gen) || (id === "poster" && gen);

  const [title, intro] = HEADINGS[view];

  return (
    <div className="shell">
      <nav className="rail" aria-label="Workflow">
        <div className="brand"><span className="brand-mark">✦</span> Brandora</div>

        <ol className="steps">
          {Object.entries(VIEWS).map(([id, v], i) => (
            <li key={id}>
              <button className={`step ${stepState(id)}`} disabled={!enabled(id)} onClick={() => setView(id)}
                aria-current={view === id ? "step" : undefined}>
                <span className="step-dot">{stepState(id) === "done" ? "✓" : i + 1}</span>
                <span>
                  <span className="step-title">{v.title}</span>
                  <span className="step-hint">{id === "poster" && unsaved ? "Unsaved poster changes" : v.hint}</span>
                </span>
              </button>
            </li>
          ))}
          <li>
            <button className={`step ${view === "evidence" ? "current" : ""}`} onClick={() => setView("evidence")}>
              <span className="step-dot">◎</span>
              <span>
                <span className="step-title">Evidence</span>
                <span className="step-hint">Sources and catalogue</span>
              </span>
            </button>
          </li>
        </ol>

        {config && (
          <div className="rail-foot">
            <div className="model-row"><span>Writer</span><b title={config.chat_model}>{config.chat_model}</b></div>
            <div className="model-row"><span>Retrieval</span><b title={config.embed_model}>{config.embed_model}</b></div>
            <div className="model-row"><span>Image</span><b title={config.image_model}>{config.image_model.split("/").pop()}</b></div>
            <span className={`status ${config.cloudflare_ready ? "on" : "off"}`}>
              {config.cloudflare_ready ? "Cloudflare connected" : "Add Cloudflare keys to .env"}
            </span>
          </div>
        )}
      </nav>

      <main className="main">
        <header className="page-head">
          <h1>{title}</h1>
          <p>{intro}</p>
        </header>

        {error && (
          <div className="alert error" role="alert" style={{ marginBottom: 20 }}>
            <span>{error}</span>
            <button aria-label="Dismiss" onClick={() => setError("")}>×</button>
          </div>
        )}

        {view === "brief" && config && (
          <Brief prompt={prompt} setPrompt={setPrompt} topK={topK} setTopK={setTopK}
            example={config.example_prompt} onSubmit={generate} busy={busy === "generate"} />
        )}

        {view === "ad" && gen && (
          <AdResult gen={gen} onError={setError} onContinue={() => setView("poster")} />
        )}

        {view === "poster" && gen && (
          editor && draft ? (
            <>
              <PosterStudio key={`${gen.id}-${imageVersion}`} gen={gen} editor={editor} setEditor={setEditor}
                draft={draft} setDraft={setDraft} onError={setError} />
              <p className="foot-note">
                Prefer the layout exactly as designed? <a href={api.autoLayoutUrl(gen.id, true)} download>Download the auto-layout version</a>.
                The raw photo stays hidden; only the typeset poster is shown.
              </p>
            </>
          ) : (
            <section className="card">
              <div className="image-prompt">
                <h2>Generate the ad image</h2>
                <p>
                  Brandora turns the visual direction into a plain photo description, with no words, logos or layout
                  in it, and checks every photo for stray lettering and clutter. Your headline, copy and button are
                  typeset afterwards, placed around the product.
                </p>
                {config && !config.cloudflare_ready && (
                  <div className="alert warn">Add CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN to .env to enable image generation.</div>
                )}
                <button className="btn primary" onClick={generateImage} disabled={busy === "image"}>
                  {busy === "image" ? <><span className="spinner" /> Generating and checking the photo…</> : "Generate image with Cloudflare"}
                </button>
              </div>
            </section>
          )
        )}

        {view === "evidence" && <Evidence retrieved={gen?.retrieved} catalogue={catalogue} />}

        <p className="foot-note">Capstone prototype. Generated content should be reviewed before real-world publication.</p>
      </main>
    </div>
  );
}
