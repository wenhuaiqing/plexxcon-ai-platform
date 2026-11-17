import { useEffect, useState } from "react";
import { Menu, Moon, Sun, X } from "lucide-react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import UnifiedOrb from "./components/common/UnifiedOrb.jsx";
import { DISCLAIMER, PUBLIC_WRITES, actorName, setActorName, writeToken } from "./config.js";
import { useTheme } from "./context/ThemeContext.jsx";
import { useApi } from "./lib/api.js";
import { useIsMobile } from "./lib/useMediaQuery.js";
import { getRoutes } from "./navigation.js";

const ROUTES = getRoutes();

function NavList({ onPick }) {
  const { t } = useTheme();
  const groups = [];
  for (const r of ROUTES) {
    if (!groups.length || groups[groups.length - 1].name !== r.group) groups.push({ name: r.group, items: [] });
    groups[groups.length - 1].items.push(r);
  }
  return (
    <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {groups.map((g) => (
        <div key={g.name} style={{ marginBottom: 8 }}>
          <div style={{
            fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase",
            color: t.sidebarGroup, padding: "6px 10px 4px",
          }}>{g.name}</div>
          {g.items.map((r) => {
            const Icon = r.icon;
            return (
              <NavLink key={r.to} to={r.to} onClick={onPick} style={({ isActive }) => ({
                display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", borderRadius: 8,
                fontSize: 13.5, fontWeight: 500,
                color: isActive ? t.sidebarActiveText : t.sidebarText,
                background: isActive ? t.sidebarActive : "transparent",
                boxShadow: isActive ? `inset 3px 0 0 ${t.sidebarMark}` : "none",
              })}>
                {Icon && <Icon size={15} strokeWidth={1.9} />}
                <span>{r.label}</span>
              </NavLink>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

function Brand({ compact }) {
  const { t } = useTheme();
  // Plexxcon's own logo (the version they publish for dark backgrounds), used
  // with the not-affiliated line beneath the navigation on every page.
  if (compact) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <img src="/plexxcon-mark.png" alt="Plexxcon" style={{ width: 28, height: 28, borderRadius: 6, display: "block" }} />
        <span style={{ fontSize: 12, color: "#FFFFFF", fontWeight: 650 }}>AI operations platform</span>
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>
      <img src="/plexxcon-logo-negative.png" alt="Plexxcon" style={{ width: 150, height: "auto", display: "block", marginLeft: -6 }} />
      <span style={{ fontSize: 10.5, color: t.sidebarMuted, fontWeight: 600, letterSpacing: "0.02em" }}>
        AI operations platform - demo
      </span>
    </div>
  );
}

function ThemeButton() {
  const { t, isDark, toggle } = useTheme();
  return (
    <button onClick={toggle} aria-label={isDark ? "Use the light theme" : "Use the dark theme"} style={{
      display: "flex", alignItems: "center", gap: 6, background: "none", cursor: "pointer",
      border: `1px solid ${t.sidebarBorder}`, color: t.sidebarMuted,
      borderRadius: 999, padding: "6px 11px", fontSize: 12, fontFamily: "inherit",
    }}>
      {isDark ? <Sun size={13} /> : <Moon size={13} />}
      {isDark ? "Light" : "Dark"}
    </button>
  );
}

function Pill({ tone, children }) {
  const { t } = useTheme();
  return (
    <span style={{
      background: t.statusBg[tone], color: t.status[tone], borderRadius: 999, padding: "3px 9px",
      fontWeight: 650, whiteSpace: "nowrap",
    }}>{children}</span>
  );
}

// Who the operator is acting as. It exists so separation of duties can be
// shown - submit a request as one person, try to approve it as the same one.
function ActingAs({ people }) {
  const { t } = useTheme();
  const [name, setName] = useState(actorName());
  const all = [...(people?.estimators || []), ...(people?.admins || []), ...(people?.supervisors || []), ...(people?.managers || [])];
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11.5, color: t.headerMuted }}>
      Acting as
      <select aria-label="Acting as" value={name} onChange={(e) => { setActorName(e.target.value); setName(e.target.value); window.location.reload(); }} style={{
        background: t.surface, color: t.text, border: `1px solid ${t.border}`, borderRadius: 8, padding: "4px 6px",
        fontSize: 12, fontFamily: "inherit",
      }}>
        {all.map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
    </label>
  );
}

function Header({ narrow, onMenu, menuOpen }) {
  const { t } = useTheme();
  const location = useLocation();
  const { data: meta } = useApi("/api/meta");
  const current = ROUTES.find((r) => location.pathname.startsWith(r.to)) || ROUTES[0];
  const operator = Boolean(writeToken());
  const writable = PUBLIC_WRITES || operator;
  return (
    <header style={{
      minHeight: 56, borderBottom: `1px solid ${t.headerBorder}`, background: narrow ? t.sidebarBg : t.headerBg,
      display: "flex", alignItems: "center", padding: narrow ? "10px 14px" : "0 24px", gap: 14, flexWrap: "wrap", flexShrink: 0,
    }}>
      {narrow ? (
        <>
          <button onClick={onMenu} aria-label={menuOpen ? "Close the menu" : "Open the menu"} style={{
            background: "none", border: "none", color: "#FFFFFF", cursor: "pointer", padding: 4, display: "flex",
          }}>
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <Brand compact />
        </>
      ) : (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {current?.icon && <current.icon size={17} color={t.headerAccent} strokeWidth={2} />}
          <span style={{ fontSize: 16, fontWeight: 650, color: t.headerText }}>{current?.label}</span>
        </div>
      )}
      <div style={{ flex: 1 }} />
      {!narrow && meta && (
        <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 11.5, color: t.headerMuted, flexWrap: "wrap" }}>
          <Pill tone="neutral">Synthetic data</Pill>
          {writable ? <ActingAs people={meta.people} /> : null}
          <Pill tone={writable ? "good" : "neutral"}>{operator ? "Operator" : writable ? "Open demo: changes reset when idle" : "Read-only link"}</Pill>
          <Pill tone={meta.llm_configured ? "ai" : "neutral"}>{meta.llm_configured ? `Model: ${meta.llm_model}` : "No model key: catalogue answers only"}</Pill>
        </div>
      )}
    </header>
  );
}

export default function App() {
  const { t } = useTheme();
  const narrow = useIsMobile();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMenuOpen(false), [location.pathname]);

  const routes = (
    <Routes>
      <Route path="/" element={<Navigate to="/overview" replace />} />
      {ROUTES.map((r) => (
        <Route key={r.to} path={r.to} element={<ErrorBoundary key={r.to} theme={t}><r.component /></ErrorBoundary>} />
      ))}
      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  );

  if (narrow) {
    return (
      <div style={{ minHeight: "100%", background: t.bg, color: t.text }}>
        <Header narrow onMenu={() => setMenuOpen((v) => !v)} menuOpen={menuOpen} />
        {menuOpen && (
          <div style={{ background: t.sidebarBg, padding: "8px 10px 14px", borderBottom: `1px solid ${t.sidebarBorder}` }}>
            <NavList onPick={() => setMenuOpen(false)} />
            <div style={{ padding: "4px 10px" }}><ThemeButton /></div>
          </div>
        )}
        <main style={{ padding: "16px 14px 96px", minWidth: 0, overflowX: "hidden" }}>
          {routes}
          <p style={{ fontSize: 11, lineHeight: 1.45, color: t.textMuted, margin: "26px 0 0" }}>{DISCLAIMER}</p>
        </main>
        <UnifiedOrb />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", height: "100vh", background: t.bg, color: t.text }}>
      <aside style={{
        width: 252, background: t.sidebarBg, borderRight: `1px solid ${t.sidebarBorder}`,
        display: "flex", flexDirection: "column", padding: "16px 12px", overflowY: "auto", flexShrink: 0,
      }}>
        <div style={{ padding: "0 8px 16px" }}><Brand /></div>
        <NavList />
        <div style={{ flex: 1 }} />
        <p style={{ fontSize: 10.5, lineHeight: 1.45, color: t.sidebarMuted, padding: "0 10px", margin: "12px 0 10px" }}>
          {DISCLAIMER}
        </p>
        <div style={{ padding: "0 8px" }}><ThemeButton /></div>
      </aside>
      <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <Header />
        <div style={{ flex: 1, overflow: "auto" }}>
          <div style={{ padding: "22px 28px 110px", maxWidth: 1520 }}>{routes}</div>
        </div>
      </main>
      <UnifiedOrb />
    </div>
  );
}
