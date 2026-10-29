import { useEffect, useRef, useState } from "react";

const SpeechRecognition =
  typeof window !== "undefined" ? window.SpeechRecognition || window.webkitSpeechRecognition : null;

export default function Brief({ prompt, setPrompt, topK, setTopK, example, onSubmit, busy }) {
  const [listening, setListening] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const recognizer = useRef(null);
  const promptRef = useRef(prompt);
  promptRef.current = prompt;

  useEffect(() => () => recognizer.current?.stop(), []);

  const toggleVoice = () => {
    if (listening) {
      recognizer.current?.stop();
      return;
    }
    setVoiceError("");
    const rec = new SpeechRecognition();
    rec.lang = "en-IN";
    rec.interimResults = false;
    rec.onresult = (event) => {
      const heard = event.results[0][0].transcript.trim();
      const current = promptRef.current.trim();
      // Replace the starter example on the first voice input; append afterwards.
      setPrompt(current === example.trim() ? heard : `${current} ${heard}`.trim());
    };
    rec.onerror = (e) => setVoiceError(e.error === "not-allowed" ? "Allow microphone access to dictate." : "Voice input stopped.");
    rec.onend = () => setListening(false);
    recognizer.current = rec;
    rec.start();
    setListening(true);
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
              {SpeechRecognition && (
                <button
                  type="button"
                  className={`round ${listening ? "rec" : ""}`}
                  onClick={toggleVoice}
                  aria-label={listening ? "Stop dictation" : "Dictate the brief"}
                  title={listening ? "Stop dictation" : "Dictate the brief"}
                >
                  {listening ? "■" : "🎙"}
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
