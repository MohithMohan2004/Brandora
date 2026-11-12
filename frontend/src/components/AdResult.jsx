import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import Icon from "../icons.jsx";
import { Disclosure, useToast } from "../ui.jsx";
import Toolbar from "./Toolbar.jsx";
import RelevancePanel, { AspectList } from "./Relevance.jsx";

export default function AdResult({ gen, busy, onContinue, onRegenerate, onEditBrief, relevance }) {
  const toast = useToast();
  const { sections, timing } = gen;
  const [audioUrl, setAudioUrl] = useState("");
  const [speaking, setSpeaking] = useState(false);
  const urlRef = useRef("");

  useEffect(() => () => urlRef.current && URL.revokeObjectURL(urlRef.current), []);

  const adText = [sections.headline, sections.copy, sections.cta].filter(Boolean).join("\n\n");

  const copyText = async () => {
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(adText);
      else {
        // older WebViews and non-secure pages: the textarea fallback
        const area = Object.assign(document.createElement("textarea"), { value: adText });
        document.body.append(area);
        area.select();
        const ok = document.execCommand("copy");
        area.remove();
        if (!ok) throw new Error("copy failed");
      }
      toast({ kind: "ok", text: "Headline, copy and call to action copied." });
    } catch {
      toast({ kind: "error", text: "Couldn't access the clipboard." });
    }
  };

  const voiceOver = async () => {
    setSpeaking(true);
    try {
      // Server voice-over (tts_utils.generate_speech) ...
      const blob = await api.speech(gen.id);
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = URL.createObjectURL(blob);
      setAudioUrl(urlRef.current);
    } catch (err) {
      // ... with the browser voice as a fallback if pyttsx3 is unavailable.
      if ("speechSynthesis" in window) {
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(adText.replace(/\n+/g, ". ")));
        toast({ kind: "info", text: "Playing with the browser's voice; the server voice-over is unavailable." });
      } else {
        toast({ kind: "error", text: err.message });
      }
    } finally {
      setSpeaking(false);
    }
  };

  const sources = (sections.sources || "").match(/(products|guidelines):[A-Z0-9-]+/g) || [];
  const product = gen.retrieved.find((r) => r.kind === "product");
  const productName = product?.text.match(/product_name: ([^|]+)/)?.[1].trim();

  return (
    <>
      <Toolbar title="Copy" subtitle={productName ? `${productName} · step 2 of 3` : "Step 2 of 3"}>
        <button className="btn" onClick={onRegenerate} disabled={Boolean(busy)} title="Write new ad copy from the same brief">
          {busy === "generate" ? <span className="spinner xs" /> : <Icon name="refresh" size={16} />}
          <span className="hide-sm">Rewrite copy</span>
        </button>
      </Toolbar>

      <div className="page copy-page">
        <div className="copy-main">
          <article className="ad-card">
            <span className="eyebrow">Advertisement</span>
            <h2 className="ad-headline">{sections.headline || "Untitled advertisement"}</h2>
            <p className="ad-copy">{sections.copy}</p>
            {sections.cta && <span className="ad-cta">{sections.cta}</span>}
            <div className="ad-actions">
              <button className="btn sm" onClick={copyText}><Icon name="clipboard" size={15} /> Copy ad text</button>
              <button className="btn sm" onClick={voiceOver} disabled={speaking}>
                {speaking ? <span className="spinner xs" /> : <Icon name="speaker" size={15} />} Voice-over
              </button>
              <a className="btn sm" href={api.briefUrl(gen.id)} download="brandora_advertisement.txt">
                <Icon name="download" size={15} /> Download brief
              </a>
            </div>
            {audioUrl && <audio controls autoPlay src={audioUrl} />}
            <button className="btn primary lg block next-step" onClick={onContinue}>
              <Icon name="poster" size={17} /><span>Design poster</span><Icon name="arrowRight" size={16} />
            </button>
          </article>

          <section className="brief-quote">
            <div className="block-head">
              <h3>Your brief</h3>
              <button className="link-btn" onClick={onEditBrief}><Icon name="edit" size={14} /> Edit brief</button>
            </div>
            <p>{gen.prompt}</p>
          </section>

          <AspectList report={relevance.report} state={relevance.state} />
        </div>

        <aside className="copy-side">
          <RelevancePanel {...relevance} />

          <section className="panel notes">
            <div className="panel-head"><h2>Writer's notes</h2></div>
            {sections.why_it_fits && (
              <Disclosure title="Why it fits the brand" defaultOpen><p>{sections.why_it_fits}</p></Disclosure>
            )}
            {sections.missing && (
              <Disclosure title="Assumptions and gaps"
                meta={/none identified/i.test(sections.missing) ? "None" : null}>
                <p>{sections.missing}</p>
              </Disclosure>
            )}
            {sections.visual_direction && (
              <Disclosure title="Visual direction"><p>{sections.visual_direction}</p></Disclosure>
            )}
            <Disclosure title="Sources used" meta={sources.length || null}>
              {sources.length ? (
                <div className="source-chips">
                  {sources.map((s) => (
                    <a key={s} className="chip mono" href={`#/evidence/${gen.id}`}>{s.split(":")[1]}</a>
                  ))}
                </div>
              ) : <p>{sections.sources || "Not listed."}</p>}
            </Disclosure>
            <dl className="timing">
              <div><dt>Retrieval</dt><dd>{timing.retrieval_seconds.toFixed(1)}s</dd></div>
              <div><dt>Writing</dt><dd>{timing.generation_seconds.toFixed(1)}s</dd></div>
              {gen.writer_model && <div><dt>Writer model</dt><dd title={gen.writer_model}>{gen.writer_model.split("/").pop()}</dd></div>}
            </dl>
          </section>
        </aside>
      </div>
    </>
  );
}
