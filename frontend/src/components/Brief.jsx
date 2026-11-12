import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import Icon from "../icons.jsx";
import { Kbd, MOD } from "../ui.jsx";
import Toolbar from "./Toolbar.jsx";
import Thumb from "./Thumb.jsx";
import { tier } from "./Relevance.jsx";
import { canRecord, startRecording } from "./voice.js";

const MAX_SECONDS = 60;
const CHANNELS = ["Instagram feed ad", "Instagram story", "email header", "Instagram post"];

// Starter briefs built from real catalogue rows, so every suggestion is answerable.
function starters(products) {
  if (!products?.length) return [];
  const byCategory = {};
  products.forEach((p) => { (byCategory[p.category] ||= []).push(p); });
  const day = Math.floor(Date.now() / 86400000);
  return Object.values(byCategory).slice(0, 4).map((list, i) => {
    const p = list[(day + i * 3) % list.length];
    const audience = String(p.target_audience || "everyday shoppers").split(/[;,]/)[0].trim().toLowerCase();
    return {
      id: p.product_id,
      name: p.product_name,
      category: p.category,
      audience,
      text: `Create an ${CHANNELS[i % CHANNELS.length]} for the ${p.product_name}, aimed at ${audience}. `
        + "Tone: confident and modern. Mention the price if it helps. Do not invent discounts or claims. "
        + "Include a clear call to action and a visual direction.",
    };
  });
}

export default function Brief({ prompt, setPrompt, example, catalogue, onSubmit, busy, topK,
  recent = [], historyCount = 0, threshold = 70, onOpenAd, onOpenHistory }) {
  const [voice, setVoice] = useState("idle");   // idle -> recording -> transcribing -> idle
  const [seconds, setSeconds] = useState(0);
  const [voiceError, setVoiceError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const recording = useRef(null);
  const textRef = useRef(null);
  const promptRef = useRef(prompt);
  promptRef.current = prompt;
  const ideas = useMemo(() => starters(catalogue?.products), [catalogue]);

  useEffect(() => () => recording.current?.cancel(), []);

  // The textarea grows with the brief instead of scrolling inside a small box.
  useEffect(() => {
    const el = textRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 360)}px`;
  }, [prompt]);

  useEffect(() => {
    if (!busy) return setElapsed(0);
    const start = Date.now();
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 500);
    return () => clearInterval(t);
  }, [busy]);

  useEffect(() => {
    if (voice !== "recording") return;
    setSeconds(0);
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, [voice]);

  const finishRecording = async () => {
    const rec = recording.current;
    if (!rec) return;
    recording.current = null;
    setVoice("transcribing");
    try {
      const wav = await rec.stop();
      const { text } = await api.transcribe(wav);
      const heard = (text || "").trim();
      if (!heard) {
        setVoiceError("Didn't catch that. Try again a little closer to the mic.");
        return;
      }
      const current = promptRef.current.trim();
      // Replace the starter example on the first voice input; append afterwards.
      setPrompt(!current || current === example.trim() ? heard : `${current} ${heard}`);
    } catch (e) {
      setVoiceError(e.message || "Could not transcribe the recording.");
    } finally {
      setVoice("idle");
    }
  };

  useEffect(() => {
    if (voice === "recording" && seconds >= MAX_SECONDS) finishRecording();
  }, [voice, seconds]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleVoice = async () => {
    if (voice === "recording") return finishRecording();
    if (voice !== "idle") return;
    setVoiceError("");
    try {
      recording.current = await startRecording();
      setVoice("recording");
    } catch (e) {
      setVoiceError(e.name === "NotAllowedError" ? "Allow microphone access to dictate." : "No microphone found.");
    }
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      if (!busy && prompt.trim()) onSubmit();
    }
  };

  const words = prompt.trim() ? prompt.trim().split(/\s+/).length : 0;
  const stage = elapsed < 3 ? "Retrieving catalogue context" : "Writing the headline, copy and call to action";

  return (
    <>
      <Toolbar title="Brief" subtitle="Step 1 of 3" />
      <div className="page brief-page">
        <div className="brief-hero">
          <h2>What are we advertising?</h2>
          <p>Describe the product, audience, channel and tone. Every word is grounded in your catalogue and brand rules.</p>
        </div>

        <div className={`composer ${busy ? "busy" : ""} ${voice === "recording" ? "listening" : ""}`}>
          {busy && <div className="progress-line" aria-hidden="true" />}
          <textarea id="brief" ref={textRef} value={prompt} rows={4} disabled={busy}
            onChange={(e) => setPrompt(e.target.value)} onKeyDown={onKeyDown}
            placeholder="e.g. An Instagram ad for the Everyday Organic Cotton Tee, aimed at college students. Relaxed, confident tone."
            aria-label="Campaign brief" />

          <div className="composer-bar">
            <div className="composer-left">
              {busy ? (
                <span className="composer-status" aria-live="polite"><span className="spinner xs" /> {stage}… {elapsed}s</span>
              ) : voice === "recording" ? (
                <span className="composer-status rec" aria-live="polite"><span className="rec-dot" /> Listening · {seconds}s of {MAX_SECONDS}s</span>
              ) : voice === "transcribing" ? (
                <span className="composer-status" aria-live="polite"><span className="spinner xs" /> Transcribing…</span>
              ) : voiceError ? (
                <span className="composer-status warn-ink">{voiceError}</span>
              ) : (
                <>
                  <span className="composer-count">{words} {words === 1 ? "word" : "words"}</span>
                  {example && prompt.trim() !== example.trim() && (
                    <button className="chip" onClick={() => setPrompt(example)}>Use example brief</button>
                  )}
                  {prompt && <button className="chip" onClick={() => { setPrompt(""); textRef.current?.focus(); }}>Clear brief</button>}
                </>
              )}
            </div>
            <div className="composer-right">
              {canRecord() && (
                <button type="button" className={`icon-btn round ${voice === "recording" ? "recording" : ""}`}
                  onClick={toggleVoice} disabled={voice === "transcribing" || busy}
                  aria-label={voice === "recording" ? "Stop and transcribe" : "Dictate the brief"}
                  title={voice === "recording" ? "Stop and transcribe" : "Dictate the brief"}>
                  <Icon name={voice === "recording" ? "stop" : "mic"} />
                </button>
              )}
              <button type="button" className="btn primary" onClick={onSubmit} disabled={busy || !prompt.trim()}
                title={`Generate (${MOD} + Enter)`}>
                {busy ? <><span className="spinner xs" /> Writing</> : <>Generate ad <Kbd>{MOD} ↵</Kbd></>}
              </button>
            </div>
          </div>
        </div>
        <p className="brief-note">
          Uses {topK} retrieved records plus every mandatory brand guideline. Change this in Settings.
        </p>

        {recent.length > 0 && (
          <section className="recent-strip" aria-label="Recent ads">
            <div className="strip-head">
              <h3>Recent ads</h3>
              <button className="link-btn" onClick={onOpenHistory}>See all {historyCount} <Icon name="chevronRight" size={14} /></button>
            </div>
            <ul className="strip">
              {recent.map((h) => (
                <li key={h.id}>
                  <button className="strip-item" onClick={() => onOpenAd(h)} title={h.prompt}>
                    <span className="strip-thumb">
                      {h.thumb ? <Thumb src={api.thumbUrl(h.id, h.thumb)} /> : (
                        <span className="strip-copy">{h.headline || "Untitled ad"}</span>
                      )}
                      {h.relevance != null && (
                        <span className={`ad-score sm t-${tier(h.relevance, threshold)}`}>{h.relevance}</span>
                      )}
                    </span>
                    <span className="strip-title">{h.headline || "Untitled ad"}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {ideas.length > 0 && (
          <section className="ideas" aria-label="Start from your catalogue">
            <h3>Start from your catalogue</h3>
            <div className="idea-grid">
              {ideas.map((idea) => (
                <button key={idea.id} className="idea" disabled={busy}
                  onClick={() => { setPrompt(idea.text); textRef.current?.focus(); }}>
                  <span className="idea-cat">{idea.category}</span>
                  <span className="idea-name">{idea.name}</span>
                  <span className="idea-aud">for {idea.audience}</span>
                  <Icon name="arrowRight" size={15} className="idea-go" />
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </>
  );
}
