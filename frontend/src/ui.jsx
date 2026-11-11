import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Icon from "./icons.jsx";

// ---------- toasts: status, completion, warning and error feedback ----------
const ToastContext = createContext(() => {});
export const useToast = () => useContext(ToastContext);

const TOAST_ICON = { ok: "check", error: "alert", warn: "alert", info: "info" };

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef({});

  const dismiss = useCallback((id) => {
    clearTimeout(timers.current[id]);
    setToasts((list) => list.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 220);
  }, []);

  const push = useCallback((toast) => {
    const id = Math.random().toString(36).slice(2);
    const duration = toast.duration ?? (toast.kind === "error" ? 9000 : 3800);
    setToasts((list) => [...list.slice(-3), { ...toast, id }]);
    if (duration) timers.current[id] = setTimeout(() => dismiss(id), duration);
    return id;
  }, [dismiss]);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="region" aria-label="Notifications">
        {toasts.map((t) => (
          <div key={t.id} className={`toast k-${t.kind || "info"} ${t.leaving ? "leaving" : ""}`}
            role={t.kind === "error" ? "alert" : "status"}>
            <Icon name={TOAST_ICON[t.kind] || "info"} size={17} className="toast-icon" />
            <span className="toast-text">{t.text}</span>
            {t.action && (
              <button className="toast-action" onClick={() => { t.action.onClick(); dismiss(t.id); }}>
                {t.action.label}
              </button>
            )}
            <button className="toast-close" onClick={() => dismiss(t.id)} aria-label="Dismiss">
              <Icon name="x" size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

// ---------- popover: anchored to its trigger, grows out of it ----------
export function Popover({ open, onClose, anchorRef, placement = "bottom-end", width = 300, children, label }) {
  const ref = useRef(null);
  const [pos, setPos] = useState(null);

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const a = anchorRef.current?.getBoundingClientRect();
      if (!a) return;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const w = Math.min(width, vw - 24);
      const [side, align] = placement.split("-");
      let left = align === "end" ? a.right - w : a.left;
      left = Math.max(12, Math.min(left, vw - w - 12));
      const style = { width: w, left };
      if (side === "top") style.bottom = vh - a.top + 8;
      else style.top = a.bottom + 8;
      const originX = Math.max(0, Math.min(w, a.left + a.width / 2 - left));
      style.transformOrigin = `${originX}px ${side === "top" ? "100%" : "0"}`;
      if (side === "top") style.maxHeight = a.top - 20;
      else style.maxHeight = vh - a.bottom - 20;
      setPos(style);
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, anchorRef, placement, width]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (ref.current?.contains(e.target) || anchorRef.current?.contains(e.target)) return;
      onClose();
    };
    const onKey = (e) => {
      if (e.key === "Escape") { onClose(); anchorRef.current?.focus(); }
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    const first = ref.current?.querySelector("button, input, select, textarea, a[href]");
    first?.focus({ preventScroll: true });
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose, anchorRef]);

  if (!open || !pos) return null;
  return createPortal(
    <div ref={ref} className="popover material" style={pos} role="dialog" aria-label={label}>
      {children}
    </div>,
    document.body,
  );
}

// ---------- sheet: a modal task, dims the page to focus ----------
export function Sheet({ open, onClose, title, children, width = 460 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const before = document.activeElement;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      before?.focus?.();
    };
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <div className="sheet-scrim" onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} className="sheet" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} style={{ maxWidth: width }}>
        <div className="sheet-head">
          <h2>{title}</h2>
          <button className="icon-btn sm" onClick={onClose} aria-label="Close"><Icon name="x" size={16} /></button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

export function MenuItem({ icon, children, onClick, disabled, danger, hint, href, download }) {
  const body = (
    <>
      {icon && <Icon name={icon} size={16} />}
      <span className="menu-label">{children}</span>
      {hint && <span className="menu-hint">{hint}</span>}
    </>
  );
  return href ? (
    <a className={`menu-item ${danger ? "danger" : ""}`} href={href} download={download} onClick={onClick}>{body}</a>
  ) : (
    <button className={`menu-item ${danger ? "danger" : ""}`} onClick={onClick} disabled={disabled}>{body}</button>
  );
}

// ---------- inputs ----------
export function Segmented({ options, value, onChange, label, disabled, size = "md" }) {
  return (
    <div className={`segmented s-${size}`} role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value}
          className={value === o.value ? "on" : ""} disabled={disabled} onClick={() => onChange(o.value)}
          title={o.title || (typeof o.label === "string" ? o.label : undefined)}>
          {o.icon && <Icon name={o.icon} size={15} />}
          {o.label && <span>{o.label}</span>}
        </button>
      ))}
    </div>
  );
}

export function Slider({ label, value, min, max, step = 1, unit = "", onChange, disabled, format }) {
  const pct = ((value - min) / (max - min)) * 100;
  const shown = format ? format(value) : `${Number(value).toFixed(step < 1 ? 2 : 0)}${unit}`;
  return (
    <label className="slider">
      <span className="slider-top"><span>{label}</span><output>{shown}</output></span>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled}
        style={{ "--pct": `${pct}%` }} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  );
}

export function ColorField({ label, value, onChange, disabled }) {
  return (
    <label className="color-field">
      <span className="field-label">{label}</span>
      <span className="color-input">
        <input type="color" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
        <code>{String(value).toUpperCase()}</code>
      </span>
    </label>
  );
}

export function Switch({ checked, onChange, label, disabled }) {
  return (
    <label className={`switch ${disabled ? "disabled" : ""}`}>
      <input type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="switch-track" aria-hidden="true"><span className="switch-thumb" /></span>
      <span>{label}</span>
    </label>
  );
}

export function Disclosure({ title, children, defaultOpen = false, meta }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`disclosure ${open ? "open" : ""}`}>
      <button className="disclosure-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <Icon name="chevronRight" size={15} className="disclosure-chevron" />
        <span>{title}</span>
        {meta != null && <span className="disclosure-meta">{meta}</span>}
      </button>
      <div className="disclosure-body"><div>{children}</div></div>
    </div>
  );
}

export const Kbd = ({ children }) => <kbd className="kbd">{children}</kbd>;

export const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
export const MOD = isMac ? "⌘" : "Ctrl";

export function relTime(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const s = Math.round((Date.now() - then) / 1000);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.round(s / 86400)} d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
