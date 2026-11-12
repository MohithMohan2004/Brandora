import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, apiUrl, getServer, isApp, setServer } from "./api.js";
import Thumb from "./components/Thumb.jsx";
import Icon, { Logo } from "./icons.jsx";
import { Kbd, MOD, Popover, Segmented, Sheet, Slider, ToastProvider, relTime, useToast } from "./ui.jsx";
import { ShellContext } from "./components/Toolbar.jsx";
import Brief from "./components/Brief.jsx";
import AdResult from "./components/AdResult.jsx";
import PosterView from "./components/PosterStudio.jsx";
import { keptPoster, sameConfig } from "./components/poster-state.js";
import Evidence from "./components/Evidence.jsx";
import Connect from "./components/Connect.jsx";
import History from "./components/History.jsx";
import { tier } from "./components/Relevance.jsx";

// ---------- routes: #/brief, #/ad/<id>, #/poster/<id>, #/evidence[/<id>], #/history ----------
const VIEWS = ["brief", "ad", "poster", "evidence", "history"];
const parseHash = () => {
  const [, view, id] = window.location.hash.split("/");
  return { view: VIEWS.includes(view) ? view : "brief", id: /^[0-9a-f]{32}$/.test(id || "") ? id : null };
};
const navigate = (view, id) => {
  const next = `#/${view}${id ? `/${id}` : ""}`;
  if (window.location.hash !== next) window.location.hash = next;
};

// ---------- preferences, remembered per browser ----------
const PREFS_KEY = "brandora.prefs";
const DEFAULT_PREFS = { theme: "system", threshold: 70, topK: 6, sidebar: "open" };
const readPrefs = () => {
  try {
    const stored = JSON.parse(localStorage.getItem(PREFS_KEY)) || {};
    const legacyBar = Number(localStorage.getItem("brandora.relevanceBar"));
    return { ...DEFAULT_PREFS, ...(legacyBar ? { threshold: legacyBar } : {}), ...stored };
  } catch { return DEFAULT_PREFS; }
};
// A server restart starts from a clean brief instead of reopening the last ad forever.
const BOOT_KEY = "brandora.boot";
const store = (key, value) => { try { localStorage.setItem(key, value); } catch { /* storage unavailable */ } };
const recall = (key) => { try { return localStorage.getItem(key); } catch { return null; } };
const typing = (el) => el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));

const SHORTCUTS = [
  [`${MOD} ↵`, "Generate the ad from the brief"],
  [`${MOD} S`, "Keep poster changes"],
  [`${MOD} B`, "Collapse or expand the sidebar"],
  ["Alt 1–4", "Go to Brief, Copy, Poster or Evidence"],
  ["Alt H", "Open History"],
  ["?", "Show these shortcuts"],
  ["Esc", "Close a menu or dialog"],
];

export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}

function Shell() {
  const toast = useToast();
  const [config, setConfig] = useState(null);
  const [server, setServerState] = useState(isApp && !getServer() ? "unset" : "checking"); // checking | ok | down | unset
  const [catalogue, setCatalogue] = useState(null);
  const [ready, setReady] = useState(false);
  const [route, setRoute] = useState(parseHash);
  const [prefs, setPrefs] = useState(readPrefs);
  const [prompt, setPrompt] = useState("");
  const [gen, setGen] = useState(null);
  const [loadingGen, setLoadingGen] = useState(false);
  const [editor, setEditor] = useState(null);
  const [draft, setDraft] = useState(null);
  const drafts = useRef({});                 // unsaved poster edits per ad, kept while switching
  const [imageVersion, setImageVersion] = useState(0);
  const [busy, setBusy] = useState(null);    // "generate" | "image"
  const [relevance, setRelevance] = useState(null);
  const [relevanceState, setRelevanceState] = useState("idle");
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [hidden, setHidden] = useState(() => new Set());   // deleted, waiting for undo to expire
  const pendingDeletes = useRef({});         // id -> timer, while the undo toast is up
  const [navOpen, setNavOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  const setPref = useCallback((key, value) => setPrefs((p) => {
    const next = { ...p, [key]: value };
    store(PREFS_KEY, JSON.stringify(next));
    return next;
  }), []);
  const toggleSidebar = useCallback(() => setPrefs((p) => {
    const next = { ...p, sidebar: p.sidebar === "collapsed" ? "open" : "collapsed" };
    store(PREFS_KEY, JSON.stringify(next));
    return next;
  }), []);

  // Theme: eased change between light and dark, never an abrupt flash.
  useEffect(() => {
    const root = document.documentElement;
    root.classList.add("theme-change");
    if (prefs.theme === "system") root.removeAttribute("data-theme");
    else root.dataset.theme = prefs.theme;
    const t = setTimeout(() => root.classList.remove("theme-change"), 400);
    // Android app: status-bar icons follow the theme on screen.
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => window.BrandoraNative?.setDarkTheme(prefs.theme === "dark" || (prefs.theme === "system" && mq.matches));
    sync();
    mq.addEventListener("change", sync);
    return () => { clearTimeout(t); mq.removeEventListener("change", sync); };
  }, [prefs.theme]);

  const refreshHistory = useCallback(() => {
    api.history().then((r) => setHistory(r.items)).catch(() => {}).finally(() => setHistoryLoading(false));
  }, []);

  // Connect to the server: same origin in the browser, the saved address in the Android app.
  const connect = useCallback(() => {
    if (isApp && !getServer()) { setServerState("unset"); return; }
    setServerState("checking");
    api.config()
      .then((c) => {
        setConfig(c);
        setServerState("ok");
        if (recall(BOOT_KEY) !== c.boot_id) {
          store(BOOT_KEY, c.boot_id);
          if (parseHash().id) navigate("brief");
        }
        setPrompt((p) => p || c.example_prompt);
        setReady(true);
        api.catalogue().then(setCatalogue).catch((e) => toast({ kind: "error", text: e.message }));
        refreshHistory();
      })
      .catch(() => setServerState("down"));
  }, [refreshHistory, toast]);

  useEffect(() => {
    connect();
    const onHash = () => { setRoute(parseHash()); setNavOpen(false); };
    window.addEventListener("hashchange", onHash);
    // Closing or reloading during the undo window still completes the delete.
    const flush = () => Object.keys(pendingDeletes.current).forEach((id) => {
      fetch(apiUrl(`/generations/${id}`), { method: "DELETE", keepalive: true });
      delete pendingDeletes.current[id];
    });
    window.addEventListener("pagehide", flush);
    return () => {
      window.removeEventListener("hashchange", onHash);
      window.removeEventListener("pagehide", flush);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const adopt = useCallback((result) => {
    setGen(result);
    setPrompt(result.prompt);
    setEditor(result.editor);
    setDraft(drafts.current[result.id] ?? (result.editor ? keptPoster(result.editor) : null));
    setRelevance(result.relevance || null);
  }, []);

  // Open the ad named in the URL.
  useEffect(() => {
    if (!ready || !route.id || route.id === gen?.id) return;
    let live = true;
    setLoadingGen(true);
    api.generation(route.id)
      .then((r) => live && adopt(r))
      .catch((e) => {
        if (!live) return;
        toast({ kind: "error", text: e.message });
        navigate("brief");
      })
      .finally(() => live && setLoadingGen(false));
    return () => { live = false; };
  }, [ready, route.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (gen && draft) drafts.current[gen.id] = draft;
  }, [gen, draft]);

  const unsaved = Boolean(editor && draft && !sameConfig(draft, keptPoster(editor)));
  useEffect(() => {
    if (!unsaved) return;
    const warn = (e) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);

  // Relevance follows the words and the photo: a new ad, a new image, kept edits.
  const scoredFor = gen ? `${gen.id}|${editor?.saved_at || ""}|${imageVersion}` : "";
  const loadRelevance = useCallback((refresh = false) => {
    if (!gen) return () => {};
    let live = true;
    setRelevanceState("loading");
    api.relevance(gen.id, refresh)
      .then((r) => {
        if (!live) return;
        setRelevance(r);
        setRelevanceState("idle");
        setHistory((list) => list.map((h) => (h.id === gen.id ? { ...h, relevance: r.score } : h)));
      })
      .catch(() => live && setRelevanceState("error"));
    return () => { live = false; };
  }, [gen?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!gen) { setRelevance(null); setRelevanceState("idle"); return; }
    return loadRelevance();
  }, [scoredFor]); // eslint-disable-line react-hooks/exhaustive-deps

  const generate = useCallback(async (text) => {
    const brief = (text ?? prompt).trim();
    if (!brief) return toast({ kind: "warn", text: "Write a campaign brief first." });
    setBusy("generate");
    try {
      const result = await api.generate(brief, prefs.topK);
      adopt(result);
      navigate("ad", result.id);
      refreshHistory();
      toast({ kind: "ok", text: `Ad written in ${result.timing.total_seconds.toFixed(1)}s. Scoring its relevance…` });
    } catch (err) {
      toast({ kind: "error", text: err.message });
    } finally {
      setBusy(null);
    }
  }, [prompt, prefs.topK, adopt, refreshHistory, toast]);

  const generateImage = async () => {
    setBusy("image");
    try {
      const res = await api.generateImage(gen.id);
      setEditor(res.editor);
      setDraft(keptPoster(res.editor));
      setImageVersion((v) => v + 1);
      refreshHistory();
      const check = res.editor.image_check || {};
      toast(check.fallback
        ? { kind: "warn", text: `The main image model was unavailable, so ${check.model.split("/").pop()} made the background photo.` }
        : { kind: "ok", text: "Poster generated. Your headline, copy and button are typeset on the background photo." });
    } catch (err) {
      toast({ kind: "error", text: err.message });
    } finally {
      setBusy(null);
    }
  };

  const newAd = () => {
    setPrompt("");
    navigate("brief");
    requestAnimationFrame(() => document.getElementById("brief")?.focus());
  };

  const removeAd = (item) => {
    setHidden((s) => new Set(s).add(item.id));
    if (gen?.id === item.id) {
      setGen(null); setEditor(null); setDraft(null);
      navigate("brief");
    }
    const timer = setTimeout(() => {
      delete pendingDeletes.current[item.id];
      api.deleteGeneration(item.id).catch(() => {}).finally(refreshHistory);
      delete drafts.current[item.id];
    }, 5000);
    pendingDeletes.current[item.id] = timer;
    toast({
      kind: "info", duration: 5000, text: `Deleted “${item.headline || "Untitled ad"}”.`,
      action: { label: "Undo", onClick: () => {
        clearTimeout(timer);
        delete pendingDeletes.current[item.id];
        setHidden((s) => { const n = new Set(s); n.delete(item.id); return n; });
      } },
    });
  };

  const items = history.filter((h) => !hidden.has(h.id));
  const current = gen && route.id === gen.id ? gen : null;
  const steps = useMemo(() => [
    { id: "brief", label: "Brief", icon: "brief", to: () => navigate("brief") },
    { id: "ad", label: "Copy", icon: "copy", to: () => navigate("ad", gen?.id), needsAd: true,
      badge: gen && relevance ? <span className={`score-dot t-${tier(relevance.score, prefs.threshold)}`}>{relevance.score}</span>
        : gen && relevanceState === "loading" ? <span className="spinner xs" /> : null,
      dot: gen && relevance ? `t-${tier(relevance.score, prefs.threshold)}` : null },
    { id: "poster", label: "Poster", icon: "poster", to: () => navigate("poster", gen?.id), needsAd: true,
      badge: unsaved ? <span className="dot-unsaved" title="Unsaved poster changes" />
        : gen?.editor?.status === "approved" ? <Icon name="check" size={14} className="ok-ink" /> : null,
      dot: unsaved ? "t-warn" : gen?.editor?.status === "approved" ? "t-ok" : null },
    { id: "evidence", label: "Evidence", icon: "evidence", to: () => navigate("evidence", gen?.id) },
  ], [gen, relevance, relevanceState, prefs.threshold, unsaved]);

  // Keyboard: shortcuts never fire while you type, except the modifier ones.
  useEffect(() => {
    const onKey = (e) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "b") { e.preventDefault(); toggleSidebar(); return; }
      if (e.altKey && !mod && /^Digit[1-4]$/.test(e.code)) {
        const step = steps[Number(e.code.slice(5)) - 1];
        if (step && !(step.needsAd && !gen)) { e.preventDefault(); step.to(); }
        return;
      }
      if (e.altKey && !mod && e.code === "KeyH") { e.preventDefault(); navigate("history"); return; }
      if (e.key === "?" && !typing(document.activeElement)) { e.preventDefault(); setHelpOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [steps, gen, toggleSidebar]);

  const shell = useMemo(() => ({ openNav: () => setNavOpen(true) }), []);

  // Android back gesture (MainActivity asks this first): close what's open, then step back
  // through screens; only the Brief screen lets the app go to the background.
  const navOpenRef = useRef(navOpen);
  navOpenRef.current = navOpen;
  useEffect(() => {
    window.brandoraBack = () => {
      if (document.querySelector(".popover, .sheet")) {
        document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
        return true;
      }
      if (navOpenRef.current) { setNavOpen(false); return true; }
      if (parseHash().view !== "brief") {
        if (window.history.length > 1) window.history.back();
        else navigate("brief");
        return true;
      }
      return false;
    };
    return () => { delete window.brandoraBack; };
  }, []);

  // In the Android app, nothing works until the phone reaches the computer running Brandora.
  if (isApp && server !== "ok") {
    return <Connect state={server} onConnected={() => window.location.reload()} />;
  }

  let content;
  if (server === "down") {
    content = (
      <div className="page">
        <div className="empty-state">
          <span className="empty-icon warn"><Icon name="wifiOff" size={28} /></span>
          <h2>Can't reach Brandora</h2>
          <p>The server isn't answering. Start it with <code>./start.sh</code>, then try again.</p>
          <button className="btn primary lg" onClick={connect}><Icon name="refresh" size={16} /> Try again</button>
        </div>
      </div>
    );
  } else if (route.view === "history") {
    content = (
      <History items={items} loading={historyLoading} threshold={prefs.threshold} currentId={gen?.id}
        onOpen={(h) => navigate(h.status === "copy" ? "ad" : "poster", h.id)} onRemove={removeAd} onNew={newAd} />
    );
  } else if (route.view === "brief" || (!route.id && route.view !== "evidence")) {
    content = (
      <Brief prompt={prompt} setPrompt={setPrompt} example={config?.example_prompt || ""} catalogue={catalogue}
        onSubmit={() => generate()} busy={busy === "generate"} topK={prefs.topK}
        recent={items.slice(0, 8)} historyCount={items.length} threshold={prefs.threshold}
        onOpenAd={(h) => navigate(h.status === "copy" ? "ad" : "poster", h.id)} onOpenHistory={() => navigate("history")} />
    );
  } else if (route.view === "evidence") {
    content = <Evidence retrieved={route.id && current ? current.retrieved : null} catalogue={catalogue} />;
  } else if (!current || loadingGen) {
    content = <div className="view-loading"><span className="spinner" /> Opening the ad…</div>;
  } else if (route.view === "ad") {
    content = (
      <AdResult gen={current} busy={busy}
        onContinue={() => navigate("poster", current.id)}
        onRegenerate={() => generate(current.prompt)}
        onEditBrief={() => { setPrompt(current.prompt); navigate("brief"); }}
        relevance={{ report: relevance, state: relevanceState, threshold: prefs.threshold,
          setThreshold: (v) => setPref("threshold", v), onRefresh: () => loadRelevance(true), hasImage: Boolean(editor) }} />
    );
  } else {
    content = (
      <PosterView key={`${current.id}-${imageVersion}`} gen={current} editor={editor} setEditor={setEditor}
        draft={draft} setDraft={setDraft} busy={busy === "image"} onGenerateImage={generateImage}
        cloudflareReady={config?.cloudflare_ready} onSaved={refreshHistory}
        relevance={{ report: relevance, state: relevanceState, threshold: prefs.threshold,
          onRefresh: () => loadRelevance(true) }} />
    );
  }

  const collapsed = prefs.sidebar === "collapsed";

  return (
    <ShellContext.Provider value={shell}>
      <div className={`shell ${collapsed ? "collapsed" : ""} ${navOpen ? "nav-open" : ""}`}>
        <Sidebar config={config} route={route} gen={current} steps={steps} prefs={prefs} setPref={setPref}
          items={items} onNew={newAd} busy={busy} collapsed={collapsed}
          onToggle={toggleSidebar} onHelp={() => setHelpOpen(true)} onClose={() => setNavOpen(false)} />
        <div className="scrim" onClick={() => setNavOpen(false)} aria-hidden="true" />
        <main className="main" key={`${route.view}-${route.id || ""}`}>{content}</main>
        <TabBar route={route} steps={steps} gen={current} />
      </div>
      <Sheet open={helpOpen} onClose={() => setHelpOpen(false)} title="Keyboard shortcuts">
        <dl className="shortcuts">
          {SHORTCUTS.map(([keys, what]) => (
            <div key={keys}><dt>{keys.split(" ").filter(Boolean).map((k) => <Kbd key={k}>{k}</Kbd>)}</dt><dd>{what}</dd></div>
          ))}
        </dl>
      </Sheet>
    </ShellContext.Provider>
  );
}

// ---------- phone: the workflow lives at the bottom, within thumb reach ----------
function TabBar({ route, steps, gen }) {
  return (
    <nav className="tabbar material" aria-label="Workflow">
      {steps.map((s) => {
        const disabled = s.needsAd && !gen;
        const active = route.view === s.id;
        return (
          <button key={s.id} className={`tab ${active ? "on" : ""}`} disabled={disabled} onClick={s.to}
            aria-current={active ? "page" : undefined}>
            <span className="tab-icon"><Icon name={s.icon} size={21} />{s.dot && <span className={`tab-dot ${s.dot}`} />}</span>
            <span>{s.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

// ---------- sidebar: where am I, where can I go, what's there ----------
function Sidebar({ config, route, gen, steps, prefs, setPref, items, onNew, busy, collapsed, onToggle, onHelp, onClose }) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const gearRef = useRef(null);
  const closeSettings = useCallback(() => setSettingsOpen(false), []);

  const navItem = ({ id, label, icon, to, disabled, badge, dot, hint }) => {
    const active = route.view === id;
    return (
      <li key={id}>
        <button className={`step ${active ? "on" : ""}`} disabled={disabled} onClick={to}
          aria-current={active ? "page" : undefined} title={collapsed ? `${label}${hint ? ` (${hint})` : ""}` : undefined}>
          <span className="step-icon"><Icon name={icon} size={17} />{collapsed && dot && <span className={`tab-dot ${dot}`} />}</span>
          <span className="side-text">{label}</span>
          {badge ? <span className="step-badge side-text">{badge}</span> : null}
        </button>
      </li>
    );
  };

  return (
    <aside className="sidebar material-heavy" aria-label="Navigation">
      <div className="side-top">
        <div className="brand">
          <span className="brand-mark"><Logo size={22} /></span>
          <span className="brand-name">Brandora</span>
        </div>
        <button className="icon-btn sm side-toggle" onClick={onToggle} title={`${collapsed ? "Expand" : "Collapse"} sidebar (${MOD} B)`}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed}>
          <Icon name="sidebar" size={17} />
        </button>
        <button className="icon-btn sm side-close" onClick={onClose} aria-label="Close sidebar" title="Close sidebar">
          <Icon name="sidebar" size={18} />
        </button>
      </div>

      <button className="btn primary block new-ad" onClick={onNew} disabled={busy === "generate"} title="New ad">
        <Icon name="plus" size={16} /> <span className="side-text">New ad</span>
      </button>

      <nav className="side-section" aria-label="Workflow">
        <div className="side-label side-text">
          {gen ? <span className="truncate" title={gen.sections.headline}>{gen.sections.headline || "This ad"}</span> : "Workflow"}
        </div>
        <ul className="steps">
          {steps.map((s, i) => navItem({ ...s, disabled: s.needsAd && !gen, hint: `Alt ${i + 1}` }))}
        </ul>
      </nav>

      {collapsed ? (
        <nav className="side-section rail-only" aria-label="History">
          <ul className="steps">
            {navItem({ id: "history", label: "History", icon: "clock", to: () => navigate("history"), hint: "Alt H" })}
          </ul>
        </nav>
      ) : (
        <section className="side-section side-history" aria-label="History">
          <div className="side-label">
            <span>History{items.length ? ` · ${items.length}` : ""}</span>
            {items.length > 0 && (
              <button className={`link-btn view-all ${route.view === "history" ? "on" : ""}`} onClick={() => navigate("history")}>
                View all
              </button>
            )}
          </div>
          <ul className="history-list">
            {items.slice(0, 12).map((h) => (
              <li key={h.id}>
                <button className={`history-row ${gen?.id === h.id ? "on" : ""}`} title={h.prompt}
                  onClick={() => navigate(h.status === "copy" ? "ad" : "poster", h.id)}>
                  <span className="history-thumb">
                    {h.thumb ? <Thumb src={api.thumbUrl(h.id, h.thumb)} /> : <Icon name="copy" size={14} />}
                  </span>
                  <span className="history-text">
                    <span className="history-title">{h.headline || "Untitled ad"}</span>
                    <span className="history-meta">
                      {h.status === "approved" && <Icon name="check" size={11} className="ok-ink" />}
                      <span className="truncate">{(h.product || "").replace(/\s*\(.*\)$/, "") || "No product"}</span>
                      <span aria-hidden="true">·</span>
                      <span className="nowrap">{relTime(h.updated_at)}</span>
                    </span>
                  </span>
                  {h.relevance != null && (
                    <span className={`history-score t-${tier(h.relevance, prefs.threshold)}`}>{h.relevance}</span>
                  )}
                </button>
              </li>
            ))}
            {!items.length && <li className="side-empty">Ads you create appear here.</li>}
          </ul>
          {items.length > 12 && (
            <button className="btn sm block view-more" onClick={() => navigate("history")}>
              View all {items.length} ads <Icon name="arrowRight" size={14} />
            </button>
          )}
        </section>
      )}

      <footer className="side-foot">
        <span className={`conn ${config?.cloudflare_ready ? "on" : "off"}`}
          title={config?.cloudflare_ready ? "Cloudflare connected" : "Add Cloudflare keys to .env"}>
          <span className="side-text">{config ? (config.cloudflare_ready ? "Connected" : "Posters unavailable") : "Connecting…"}</span>
        </span>
        <div className="side-foot-actions">
          <button className="icon-btn hide-touch" onClick={onHelp} aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)">
            <Icon name="keyboard" />
          </button>
          <button ref={gearRef} className="icon-btn" onClick={() => setSettingsOpen((o) => !o)}
            aria-label="Settings" aria-expanded={settingsOpen} title="Settings">
            <Icon name="gear" />
          </button>
        </div>
        <Popover open={settingsOpen} onClose={closeSettings} anchorRef={gearRef} placement="top-start" width={320} label="Settings">
          <Settings config={config} prefs={prefs} setPref={setPref} />
        </Popover>
      </footer>
    </aside>
  );
}

function Settings({ config, prefs, setPref }) {
  return (
    <div className="settings">
      <h2>Settings</h2>
      <div className="setting">
        <span className="field-label">Appearance</span>
        <Segmented label="Appearance" value={prefs.theme} onChange={(v) => setPref("theme", v)} options={[
          { value: "system", icon: "monitor", label: "Auto" },
          { value: "light", icon: "sun", label: "Light" },
          { value: "dark", icon: "moon", label: "Dark" },
        ]} />
      </div>
      <div className="setting">
        <Slider label="Relevance bar" value={prefs.threshold} min={40} max={95} step={5}
          onChange={(v) => setPref("threshold", v)} />
        <p className="setting-help">Posters scoring below this ask for confirmation before approval.</p>
      </div>
      <div className="setting">
        <Slider label="Records retrieved per brief" value={prefs.topK} min={2} max={10}
          onChange={(v) => setPref("topK", v)} />
        <p className="setting-help">Catalogue and guideline records the writer sees. Mandatory guidelines are always added.</p>
      </div>
      {isApp && (
        <div className="setting">
          <span className="field-label">Server</span>
          <div className="server-row">
            <code className="truncate">{getServer()}</code>
            <button className="btn sm" onClick={() => { setServer(""); window.location.reload(); }}>Change server</button>
          </div>
        </div>
      )}
      {config && (
        <dl className="models">
          <div><dt>Writer model</dt><dd title={config.chat_model}>{config.chat_model.split("/").pop()}</dd></div>
          <div><dt>Retrieval</dt><dd>{config.embed_model}</dd></div>
          <div><dt>Image model</dt><dd title={config.image_model}>{config.image_model.split("/").pop()}</dd></div>
          {config.image_fallbacks?.length > 0 && (
            <div><dt>Fallback image model</dt><dd>{config.image_fallbacks.map((m) => m.split("/").pop()).join(", ")}</dd></div>
          )}
          <div><dt>Cloudflare</dt><dd className={config.cloudflare_ready ? "ok-ink" : "warn-ink"}>
            {config.cloudflare_ready ? "Connected" : "Keys missing in .env"}</dd></div>
        </dl>
      )}
    </div>
  );
}
