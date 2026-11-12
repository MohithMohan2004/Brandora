import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "../icons.jsx";
import { Popover, Slider } from "../ui.jsx";

// How the 0-100 relevance score is read. The bar is the user's own;
// the bands describe the score itself.
export const band = (score) =>
  score >= 85 ? "Strong match" : score >= 70 ? "Good match" : score >= 55 ? "Partial match" : "Weak match";

// ok: meets the bar, warn: within 15 points of it, bad: further below.
export const tier = (score, threshold) =>
  score == null ? "none" : score >= threshold ? "ok" : score >= threshold - 15 ? "warn" : "bad";

const BAR_TEXT = { ok: "Meets your bar", warn: "Just under your bar", bad: "Below your bar", none: "" };

const SIGNALS = [
  ["coverage", "Brief coverage", "Share of the brief's requests the copy delivers, rated by an LLM judge."],
  ["semantic", "Meaning match", "How close the words are in meaning to the brief (embeddinggemma, calibrated)."],
  ["visual", "Photo fit", "Whether the poster photo shows the product and suits the audience, tone and message."],
  ["catalogue", "Catalogue match", "How closely your best catalogue product fits the brief."],
];

const STATUS = {
  met: ["check", "Delivered"],
  partial: ["chevronRight", "Partly delivered"],
  missed: ["x", "Not addressed"],
  withheld: ["info", "Held back by brand rules"],
};

function useCountUp(target) {
  const [value, setValue] = useState(0);
  const current = useRef(0);
  useEffect(() => {
    if (target == null) return;
    const set = (v) => { current.current = v; setValue(v); };
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return set(target);
    let frame;
    const from = current.current;
    const start = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - start) / 700);
      // critically damped approach: fast start, no overshoot
      set(Math.round(from + (target - from) * (1 - (1 + 9 * t) * Math.exp(-9 * t))));
      if (t < 1) frame = requestAnimationFrame(step);
      else set(target);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target]);
  return value;
}

// A 270° ring: the filled arc is the score, the tick is the user's bar.
export function Gauge({ score, threshold, size = 120, loading = false }) {
  const shown = useCountUp(score);
  const r = 42;
  const c = 2 * Math.PI * r;
  const arc = 0.75 * c;
  const filled = loading || score == null ? 0 : (arc * score) / 100;
  const angle = ((135 + 2.7 * threshold) * Math.PI) / 180;
  const at = (radius) => [50 + radius * Math.cos(angle), 50 + radius * Math.sin(angle)];
  const [x1, y1] = at(r - 8);
  const [x2, y2] = at(r + 8);
  return (
    <div className={`gauge t-${loading ? "none" : tier(score, threshold)} ${loading ? "loading" : ""}`}
      style={{ width: size, height: size }} role="img"
      aria-label={loading ? "Scoring relevance" : `Relevance ${score} out of 100, your bar is ${threshold}`}>
      <svg viewBox="0 0 100 100">
        <circle className="gauge-track" cx="50" cy="50" r={r} strokeDasharray={`${arc} ${c}`} transform="rotate(135 50 50)" />
        <circle className="gauge-fill" cx="50" cy="50" r={r} strokeDasharray={`${filled} ${c}`} transform="rotate(135 50 50)" />
        {!loading && <line className="gauge-tick" x1={x1} y1={y1} x2={x2} y2={y2} />}
      </svg>
      <div className="gauge-value">
        {loading ? <span className="spinner" /> : <b>{shown}</b>}
      </div>
    </div>
  );
}

function BarControl({ threshold, setThreshold }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const close = useCallback(() => setOpen(false), []);
  return (
    <>
      <button ref={ref} className="link-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        Your bar {threshold} <Icon name="chevronDown" size={13} />
      </button>
      <Popover open={open} onClose={close} anchorRef={ref} placement="bottom-end" width={260} label="Relevance bar">
        <div className="settings">
          <Slider label="Relevance bar" value={threshold} min={40} max={95} step={5} onChange={setThreshold} />
          <p className="setting-help">Posters below it ask for confirmation before approval.</p>
        </div>
      </Popover>
    </>
  );
}

// Inspector panel for the Copy step.
export default function RelevancePanel({ report, state, threshold, setThreshold, onRefresh, hasImage }) {
  const loading = state === "loading";
  const t = report ? tier(report.score, threshold) : "none";

  return (
    <section className={`panel relevance t-${t}`} aria-busy={loading}>
      <div className="panel-head">
        <h2>Relevance</h2>
        <div className="panel-head-actions">
          {setThreshold && <BarControl threshold={threshold} setThreshold={setThreshold} />}
          <button className="icon-btn sm" onClick={onRefresh} disabled={loading} title="Score again" aria-label="Score relevance again">
            <Icon name="refresh" size={15} className={loading ? "spin" : ""} />
          </button>
        </div>
      </div>

      {state === "error" && !report ? (
        <div className="inline-note warn">
          <Icon name="alert" size={16} />
          <span>Couldn't score relevance. Ollama or the judge model may be unavailable.</span>
          <button className="link-btn" onClick={onRefresh}>Retry scoring</button>
        </div>
      ) : (
        <>
          <div className="rel-summary">
            <Gauge score={report?.score} threshold={threshold} loading={!report} size={104} />
            <div className="rel-verdict">
              {report ? (
                <>
                  <strong>{band(report.score)}</strong>
                  <span className={`pill t-${t}`}>{BAR_TEXT[t]}</span>
                  <p>{report.advice}</p>
                </>
              ) : (
                <>
                  <strong>Scoring…</strong>
                  <p>Comparing the words{hasImage ? " and the photo" : ""} with your brief. This takes about ten seconds.</p>
                </>
              )}
            </div>
          </div>

          <div className="signals">
            {SIGNALS.map(([id, label, help]) => {
              const value = report?.signals[id];
              const pending = id === "visual" && !(report?.has_image ?? hasImage);
              return (
                <div key={id} className={`signal ${value == null ? "missing" : ""}`} title={help}>
                  <span className="signal-label">{label}</span>
                  <span className="signal-track">
                    {value != null && <span className={`signal-fill t-${tier(value, threshold)}`} style={{ width: `${value}%` }} />}
                  </span>
                  <span className="signal-value">{!report ? "…" : pending ? "after poster" : value == null ? "n/a" : value}</span>
                </div>
              );
            })}
          </div>
          {report?.visual?.note && <p className="rel-note"><Icon name="image" size={14} /> {report.visual.note}</p>}
          {report && (
            <p className="rel-meta">
              Scored on the {report.texts === "edited" ? "text kept in the poster studio" : "generated copy"}
              {report.unavailable?.length ? ` · ${report.unavailable.join(", ")} unavailable` : ""}. A guide, not a guarantee.
            </p>
          )}
        </>
      )}
    </section>
  );
}

// What the brief asked for, item by item.
export function AspectList({ report, state }) {
  if (!report?.aspects?.length) {
    return state === "loading" ? (
      <ul className="aspects skeleton" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => <li key={i} className="aspect"><span className="sk-line" /></li>)}
      </ul>
    ) : null;
  }
  const counted = report.aspects.filter((a) => a.status !== "withheld");
  const met = counted.filter((a) => a.status === "met").length;
  return (
    <div className="aspects-block">
      <div className="block-head">
        <h3>What the brief asked for</h3>
        {counted.length > 0 && <span className="muted">{met} of {counted.length} delivered</span>}
      </div>
      <ul className="aspects">
        {report.aspects.map((a, i) => (
          <li key={`${a.aspect}-${i}`} className={`aspect s-${a.status}`}>
            <span className="aspect-icon" title={STATUS[a.status][1]}>
              <Icon name={STATUS[a.status][0]} size={13} label={STATUS[a.status][1]} />
            </span>
            <span className="aspect-main">
              <span className="aspect-label">{a.aspect}<span className="aspect-kind">{a.kind}</span></span>
              {a.note && <span className="aspect-note">{a.note}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// Compact read-out under the poster canvas.
export function RelevanceStrip({ report, state, threshold, dirty, onRefresh }) {
  const loading = state === "loading";
  if (!report && !loading) {
    return state === "error" ? (
      <div className="rel-strip">
        <span className="rel-strip-text"><b>Relevance unavailable</b><span>The judge model could not be reached.</span></span>
        <button className="btn sm" onClick={onRefresh}>Retry scoring</button>
      </div>
    ) : null;
  }
  const t = report ? tier(report.score, threshold) : "none";
  return (
    <div className={`rel-strip t-${t}`}>
      <Gauge score={report?.score} threshold={threshold} size={46} loading={!report} />
      <div className="rel-strip-text">
        {report ? (
          <>
            <b>{band(report.score)} <span className="muted">· {BAR_TEXT[t].toLowerCase()} ({threshold})</span></b>
            <span>
              {report.signals.visual != null ? `Photo fit ${report.signals.visual}` : "Photo not scored"}
              {` · coverage ${report.signals.coverage ?? "n/a"}`}
              {dirty ? " · keep changes to score the edited text" : ""}
            </span>
          </>
        ) : (
          <><b>Scoring relevance…</b><span>Checking the words and the photo against your brief.</span></>
        )}
      </div>
      {loading && report && <span className="spinner xs" aria-label="Re-scoring" />}
    </div>
  );
}
