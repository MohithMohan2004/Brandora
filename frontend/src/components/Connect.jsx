import { useState } from "react";
import { api, DEFAULT_SERVER, getServer, normalizeServer, setServer } from "../api.js";
import Icon, { Logo } from "../icons.jsx";

// Android app only: the UI ships in the APK and talks to the hosted server on
// Render by default. This screen shows up when that server can't be reached, and
// lets the user switch to another address (e.g. a computer on ./start.sh --lan).
export default function Connect({ state, onConnected }) {
  const saved = getServer();
  const [value, setValue] = useState(saved.replace(/^http:\/\//, ""));
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState(state === "down" && saved
    ? `Can't reach ${saved}. The hosted server can take up to a minute to wake up, so try again shortly, or check your internet connection.`
    : "");

  const submit = async (e) => {
    e.preventDefault();
    const address = normalizeServer(value);
    if (!address) return setError("Enter a server address.");
    setChecking(true);
    setError("");
    try {
      await api.probe(address);
      setServer(address);
      onConnected();
    } catch {
      setError(`No Brandora server answered at ${address}. Check the address and your connection.`);
    } finally {
      setChecking(false);
    }
  };

  if (state === "checking") {
    return (
      <div className="connect">
        <div className="connect-card center">
          <span className="brand-mark lg"><Logo size={38} /></span>
          <p className="muted"><span className="spinner xs" /> Connecting to {saved}…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="connect">
      <form className="connect-card" onSubmit={submit}>
        <span className="brand-mark lg"><Logo size={38} /></span>
        <h1>Connect to Brandora</h1>
        <p>Brandora runs on <code>{DEFAULT_SERVER.replace(/^https:\/\//, "")}</code>. If it was asleep, connecting can take up to a minute.</p>
        <p className="muted">To use your own computer instead, run <code>./start.sh --lan</code> and enter the address it prints, for example <code>192.168.1.20:8000</code>.</p>
        <label className="field">
          <span className="field-label">Server address</span>
          <input className="input lg" value={value} onChange={(e) => setValue(e.target.value)} inputMode="url"
            autoCapitalize="off" autoCorrect="off" spellCheck="false" placeholder={DEFAULT_SERVER} autoFocus />
        </label>
        {error && <div className="inline-note warn"><Icon name="wifiOff" size={16} /><span>{error}</span></div>}
        <button className="btn primary lg block" disabled={checking || !value.trim()}>
          {checking ? <><span className="spinner xs" /> Checking…</> : <><Icon name="server" size={16} /> Connect</>}
        </button>
      </form>
    </div>
  );
}
