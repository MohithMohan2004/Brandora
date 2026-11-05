import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { canRecord, startRecording } from "./voice.js";

const MAX_SECONDS = 60;

export default function Brief({ prompt, setPrompt, topK, setTopK, example, onSubmit, busy }) {
  // idle -> recording -> transcribing -> idle
  const [voice, setVoice] = useState("idle");
  const [seconds, setSeconds] = useState(0);
  const [voiceError, setVoiceError] = useState("");
  const recording = useRef(null);
  const promptRef = useRef(prompt);
  promptRef.current = prompt;

  useEffect(() => () => recording.current?.cancel(), []);

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
  }, [voice, seconds]);

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
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onSubmit();
  };

  return (
    <section className="card">
      <div className="composer">
        <div className="field">
          <label htmlFor="brief">Campaign brief</label>
          <div className="composer-box">
            <textarea
              id="brief"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Describe the product, audience, channel, tone and goal"
              rows={3}
            />
            <div className="composer-actions">
              {canRecord() && (
                <button
                  type="button"
                  className={`round ${voice === "recording" ? "rec" : ""}`}
                  onClick={toggleVoice}
                  disabled={voice === "transcribing" || busy}
                  aria-label={voice === "recording" ? "Stop and transcribe" : "Dictate the brief"}
                  title={voice === "recording" ? "Stop and transcribe" : "Dictate the brief"}
                >
                  {voice === "transcribing" ? <span className="spinner" /> : voice === "recording" ? "■" : "🎙"}
                </button>
              )}
              <button
                type="button"
                className="round send"
                onClick={onSubmit}
                disabled={busy || !prompt.trim()}
                aria-label="Generate advertisement"
                title="Generate advertisement (Ctrl/⌘ + Enter)"
              >
                {busy ? <span className="spinner" /> : "➤"}
              </button>
            </div>
          </div>
          {voice === "recording" && (
            <p className="stage-hint" style={{ marginTop: 6 }}>
              Listening… {seconds}s. Tap ■ when you're done (stops at {MAX_SECONDS}s).
            </p>
          )}
          {voice === "transcribing" && <p className="stage-hint" style={{ marginTop: 6 }}>Transcribing your brief…</p>}
          {voiceError && <p className="stage-hint" style={{ color: "var(--warn)", marginTop: 6 }}>{voiceError}</p>}
        </div>

        <div className="composer-meta">
          <label className="range-field">
            Context records to retrieve
            <input type="range" min="2" max="10" value={topK} onChange={(e) => setTopK(Number(e.target.value))} />
            <span className="range-value">{topK}</span>
          </label>
          <div className="chips">
            <button className="chip" type="button" onClick={() => setPrompt(example)}>Use the example brief</button>
            <button className="chip" type="button" onClick={() => setPrompt("")}>Clear</button>
          </div>
        </div>

        <button className="btn primary block" onClick={onSubmit} disabled={busy || !prompt.trim()}>
          {busy ? <><span className="spinner" /> Retrieving context and writing the ad…</> : "Generate advertisement"}
        </button>
      </div>
    </section>
  );
}
