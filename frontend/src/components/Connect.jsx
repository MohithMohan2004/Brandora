import { useState } from "react";
import { api, getServer, normalizeServer, setServer } from "../api.js";
import Icon from "../icons.jsx";

// Android app only: the UI ships in the APK, the work happens on the computer
// running ./start.sh --lan. This screen pairs the two.
export default function Connect({ state, onConnected }) {
  const saved = getServer();
  const [value, setValue] = useState(saved.replace(/^http:\/\//, ""));
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState(state === "down" && saved
    ? `Can't reach ${saved}. Check that Brandora is running with ./start.sh --lan and that this phone is on the same Wi-Fi.`
    : "");

  const submit = async (e) => {
    e.preventDefault();
    const address = normalizeServer(value);
    if (!address) return setError("Enter the address shown by ./start.sh --lan.");
    setChecking(true);
    setError("");
    try {
      await api.probe(address);
      setServer(address);
      onConnected();
    } catch {
      setError(`No Brandora server answered at ${address}. Check the address, the Wi-Fi network, and that ./start.sh --lan is running.`);
    } finally {
      setChecking(false);
    }
  };

  if (state === "checking") {
    return (
      <div className="connect">
        <div className="connect-card center">
          <span className="brand-mark lg"><Icon name="sparkle" size={22} /></span>
          <p className="muted"><span className="spinner xs" /> Connecting to {saved}…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="connect">
      <form className="connect-card" onSubmit={submit}>
        <span className="brand-mark lg"><Icon name="sparkle" size={22} /></span>
        <h1>Connect to Brandora</h1>
        <p>Brandora writes and designs on your computer. Pair this phone with it once:</p>
        <ol className="connect-steps">
          <li>On the computer, run <code>./start.sh --lan</code> in the Brandora folder.</li>
          <li>Keep this phone on the same Wi-Fi network.</li>
          <li>Enter the address it prints, for example <code>192.168.1.20:8000</code>.</li>
        </ol>
        <label className="field">
          <span className="field-label">Server address</span>
          <input className="input lg" value={value} onChange={(e) => setValue(e.target.value)} inputMode="url"
            autoCapitalize="off" autoCorrect="off" spellCheck="false" placeholder="192.168.1.20:8000" autoFocus />
        </label>
        {error && <div className="inline-note warn"><Icon name="wifiOff" size={16} /><span>{error}</span></div>}
        <button className="btn primary lg block" disabled={checking || !value.trim()}>
          {checking ? <><span className="spinner xs" /> Checking…</> : <><Icon name="server" size={16} /> Connect</>}
        </button>
      </form>
    </div>
  );
}
