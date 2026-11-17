// Form furniture for the workflow systems: inputs, modals, toasts, tab sets
// whose panes stay mounted, and the banners a write path needs.

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { writeToken } from "../config.js";
import { useTheme } from "../context/ThemeContext.jsx";

export function useInputStyle() {
  const { t } = useTheme();
  return {
    background: t.surface, color: t.text, border: `1px solid ${t.border}`, borderRadius: 8,
    padding: "6px 9px", fontSize: 13, fontFamily: "inherit", minWidth: 0, width: "100%",
  };
}

export function Field({ label, children, hint, flag, width }) {
  const { t } = useTheme();
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0, width }}>
      <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase", color: flag ? t.status[flag] : t.textMuted }}>
        {label}{flag === "critical" ? " - required" : flag === "warning" ? " - advisory" : ""}
      </span>
      {children}
      {hint && <span style={{ fontSize: 11.5, color: t.textMuted }}>{hint}</span>}
    </label>
  );
}

export function Input({ value, onChange, type = "text", placeholder, disabled, label, style, ...rest }) {
  const base = useInputStyle();
  return (
    <input aria-label={label} type={type} value={value ?? ""} placeholder={placeholder} disabled={disabled}
      onChange={(e) => onChange(type === "checkbox" ? e.target.checked : e.target.value)}
      style={{ ...base, ...(type === "checkbox" ? { width: "auto" } : {}), ...style }} {...rest} />
  );
}

export function Choice({ value, onChange, options, disabled, label, style }) {
  const base = useInputStyle();
  return (
    <select aria-label={label} value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value)} style={{ ...base, ...style }}>
      {options.map((o) => {
        const v = typeof o === "string" ? o : o.value;
        return <option key={v} value={v}>{typeof o === "string" ? o : o.label}</option>;
      })}
    </select>
  );
}

export function FormGrid({ children, min = 200 }) {
  return <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fill, minmax(min(100%, ${min}px), 1fr))`, gap: "12px 14px" }}>{children}</div>;
}

// Tabs whose panes stay mounted, so a draft, a scroll position or a filter
// survives switching away and back.
export function MountedTabs({ tabs, value, onChange, right }) {
  const { t } = useTheme();
  return (
    <>
      <div role="tablist" style={{ display: "flex", gap: 2, borderBottom: `1px solid ${t.border}`, marginBottom: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
        {tabs.map((tab) => {
          const on = tab.key === value;
          return (
            <button key={tab.key} role="tab" aria-selected={on} type="button" onClick={() => onChange(tab.key)} style={{
              border: "none", background: "none", cursor: "pointer", fontFamily: "inherit", fontSize: 13, fontWeight: on ? 700 : 550,
              color: on ? t.text : t.textMuted, padding: "9px 12px", borderBottom: `2px solid ${on ? t.brand : "transparent"}`, marginBottom: -1,
            }}>
              {tab.label}{tab.count != null ? <span style={{ marginLeft: 6, fontSize: 11, color: t.textMuted }}>{tab.count}</span> : null}
            </button>
          );
        })}
        <div style={{ flex: 1 }} />
        {right}
      </div>
      {tabs.map((tab) => (
        <div key={tab.key} role="tabpanel" hidden={tab.key !== value} style={{ display: tab.key === value ? "block" : "none" }}>
          {tab.render()}
        </div>
      ))}
    </>
  );
}

export function Modal({ open, onClose, title, children, width = 760, footer }) {
  const { t } = useTheme();
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div role="dialog" aria-modal="true" aria-label={title} onClick={onClose} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 10010, display: "flex",
      alignItems: "flex-start", justifyContent: "center", padding: "4vh 12px", overflowY: "auto",
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        background: t.surface, color: t.text, borderRadius: 14, width: "100%", maxWidth: width, borderTop: `3px solid ${t.brand}`,
        boxShadow: "0 18px 50px rgba(0,0,0,0.3)", display: "flex", flexDirection: "column", maxHeight: "92vh",
      }}>
        <div style={{ display: "flex", alignItems: "center", padding: "12px 16px", borderBottom: `1px solid ${t.border}` }}>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, flex: 1 }}>{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close" style={{ border: "none", background: "none", cursor: "pointer", color: t.textMuted }}>
            <X size={18} />
          </button>
        </div>
        <div style={{ padding: 16, overflowY: "auto" }}>{children}</div>
        {footer && <div style={{ padding: "10px 16px", borderTop: `1px solid ${t.border}`, display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap" }}>{footer}</div>}
      </div>
    </div>
  );
}

// Toasts: a sentence that says what happened, with an Undo where one exists.
const ToastCtx = createContext(null);

export function ToastProvider({ children }) {
  const { t } = useTheme();
  const [items, setItems] = useState([]);
  const seq = useRef(0);
  const push = useCallback((text, { tone = "neutral", action, ms = 6000 } = {}) => {
    seq.current += 1;
    const id = seq.current;
    setItems((xs) => [...xs, { id, text, tone, action }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), ms);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div aria-live="polite" style={{ position: "fixed", left: "50%", transform: "translateX(-50%)", bottom: 16, zIndex: 10020, display: "flex", flexDirection: "column", gap: 8, maxWidth: "min(440px, calc(100vw - 32px))" }}>
        {items.map((x) => (
          <div key={x.id} role="status" style={{
            background: t.surface, color: t.text, border: `1px solid ${t.border}`, borderLeft: `3px solid ${t.status[x.tone]}`,
            borderRadius: 10, padding: "9px 12px", fontSize: 13, boxShadow: "0 8px 24px rgba(0,0,0,0.16)", display: "flex", gap: 12, alignItems: "center",
          }}>
            <span style={{ flex: 1 }}>{x.text}</span>
            {x.action && (
              <button type="button" onClick={() => { x.action.run(); setItems((xs) => xs.filter((y) => y.id !== x.id)); }} style={{
                border: "none", background: "none", color: t.accent, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
              }}>{x.action.label}</button>
            )}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}

// What the read-only role sees where a write would be.
export function ReadOnlyNotice({ what, role }) {
  const { t } = useTheme();
  if (writeToken()) return null;
  return (
    <div style={{
      background: t.statusBg.neutral, borderLeft: `3px solid ${t.status.neutral}`, borderRadius: 10,
      padding: "10px 14px", fontSize: 12.5, marginBottom: 14, lineHeight: 1.5,
    }}>
      <b>Read-only link.</b> You can see everything here; {what} needs the <b>{role}</b> role, which on this demo is the operator's
      write token. Every refusal is recorded in the audit log, so trying is safe.
    </div>
  );
}

export function canWrite() {
  return Boolean(writeToken());
}

export function useOnline() {
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);
  return online;
}

export function openBlob(blob) {
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function readLocal(key) {
  try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; }
}

export function writeLocal(key, value) {
  try {
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch { /* storage blocked */ }
}
