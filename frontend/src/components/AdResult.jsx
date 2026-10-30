import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

export default function AdResult({ gen, onError, onContinue }) {
  const { sections, timing } = gen;
  const [audioUrl, setAudioUrl] = useState("");
  const [speaking, setSpeaking] = useState(false);
  const urlRef = useRef("");

  useEffect(() => {
    setAudioUrl("");
    return () => urlRef.current && URL.revokeObjectURL(urlRef.current);
  }, [gen.id]);

  const downloadBrief = () => {
    const url = URL.createObjectURL(new Blob([gen.ad_output], { type: "text/plain" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "brandora_advertisement.txt" });
    a.click();
    URL.revokeObjectURL(url);
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
        const text = [sections.headline, sections.copy, sections.cta].filter(Boolean).join(". ");
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
      } else {
        onError(err.message);
      }
    } finally {
      setSpeaking(false);
    }
  };

  const notes = [
    ["Why this fits the brand", sections.why_it_fits],
    ["Assumptions and missing information", sections.missing],
    ["Visual direction", sections.visual_direction],
  ].filter(([, text]) => text);

  return (
    <div className="result-grid">
      <div>
        <div className="ad-hero">
          <h2 className="headline">{sections.headline || "Untitled advertisement"}</h2>
          <p className="copy">{sections.copy}</p>
          {sections.cta && <span className="cta">{sections.cta}</span>}
          <div className="ad-hero-actions">
            <button className="btn sm" onClick={voiceOver} disabled={speaking}>
              {speaking ? <><span className="spinner" /> Recording voice-over…</> : "Hear voice-over"}
            </button>
            <button className="btn sm" onClick={downloadBrief}>Download brief (.txt)</button>
          </div>
          {audioUrl && <audio controls autoPlay src={audioUrl} />}
        </div>
        <div className="timing">
          <span>Retrieval <b>{timing.retrieval_seconds.toFixed(1)}s</b></span>
          <span>Text generation <b>{timing.generation_seconds.toFixed(1)}s</b></span>
          <span>Total <b>{timing.total_seconds.toFixed(1)}s</b></span>
          {gen.writer_model && <span>Writer <b>{gen.writer_model.split("/").pop()}</b></span>}
        </div>
      </div>

      <aside className="card">
        <div className="note-list">
          {notes.map(([title, text]) => (
            <div className="note" key={title}>
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
          ))}
          {sections.sources && (
            <div className="note">
              <h3>Sources used</h3>
              <p>{sections.sources}</p>
            </div>
          )}
        </div>
        <button className="btn primary block" style={{ marginTop: 20 }} onClick={onContinue}>
          Continue to the poster
        </button>
      </aside>
    </div>
  );
}
