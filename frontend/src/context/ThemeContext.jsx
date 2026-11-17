import { createContext, useContext, useEffect, useState } from "react";

// Plexxcon's palette, taken from their public website (plexxcon.com.au) and
// logo, for an application demo that is not affiliated with them - the sidebar
// says so on every page.
//
//   black  #000000   chrome: sidebar, hero tiles, primary buttons
//   teal   #4AB7C3   the logo's colour; brand accents - active nav, card
//                    rules, button hover. Chrome only: never the only signal
//                    of a status, and badges always carry their label.
//   deep teal #1B7F8B  the same hue darkened to 4.5:1 on white, for links,
//                    controls and chart series
//   violet #5847C9   anything the AI produced, so "the model said this" is
//                    never confused with "the data says this"

export const light = {
  name: "light",
  bg: "#F2F5F5",
  surface: "#FFFFFF",
  surfaceRaised: "#F7FAFA",
  border: "rgba(0,0,0,0.11)",
  borderBright: "rgba(0,0,0,0.26)",
  accent: "#1B7F8B",
  accentText: "#FFFFFF",
  accentGlow: "rgba(74,183,195,0.14)",
  accent2: "#5847C9",
  accent2Glow: "rgba(88,71,201,0.10)",
  brand: "#4AB7C3",
  text: "#0D1516",
  textMuted: "rgba(13,21,22,0.66)",
  textDim: "rgba(13,21,22,0.34)",

  sidebarBg: "#000000",
  sidebarText: "rgba(255,255,255,0.80)",
  sidebarActive: "rgba(74,183,195,0.26)",
  sidebarActiveText: "#FFFFFF",
  sidebarBorder: "rgba(255,255,255,0.12)",
  sidebarMark: "#4AB7C3",
  sidebarMuted: "rgba(255,255,255,0.62)",
  sidebarGroup: "rgba(255,255,255,0.48)",

  headerBg: "#FFFFFF",
  headerText: "#0D1516",
  headerMuted: "rgba(13,21,22,0.62)",
  headerBorder: "rgba(0,0,0,0.10)",
  headerAccent: "#1B7F8B",

  ctaBg: "#000000",
  ctaText: "#FFFFFF",
  ctaHoverBg: "#4AB7C3",
  ctaHoverText: "#000000",

  cardRule: "#4AB7C3",
  tableHead: "#EDF2F2",
  statHeroBg: "#000000",
  statHeroText: "#FFFFFF",
  statHeroMuted: "rgba(255,255,255,0.74)",
  rowHover: "rgba(74,183,195,0.08)",
  rowDivider: "rgba(0,0,0,0.08)",
  grid: "rgba(0,0,0,0.09)",
  code: "rgba(0,0,0,0.06)",
  labelColBg: "rgba(0,0,0,0.05)",
  series: ["#1B7F8B", "#0D1516", "#8FA5A8", "#B4562A"],
  status: { good: "#1F7A5A", warning: "#8A6410", serious: "#B4562A", critical: "#B0122B", neutral: "#566266", ai: "#5847C9" },
  statusBg: {
    good: "rgba(31,122,90,0.10)", warning: "rgba(227,162,59,0.20)", serious: "rgba(180,86,42,0.12)",
    critical: "rgba(176,18,43,0.09)", neutral: "rgba(0,0,0,0.06)", ai: "rgba(88,71,201,0.10)",
  },
  // Tokens the assistant panel inherited from the template it came from.
  dot: { grey: "rgba(13,21,22,0.20)", green: "#1F7A5A", yellow: "#8A6410", blue: "#1B7F8B", red: "#B0122B" },
  dotGlow: { green: "rgba(31,122,90,0.14)", yellow: "rgba(227,162,59,0.20)", blue: "rgba(74,183,195,0.16)", red: "rgba(176,18,43,0.09)" },
};

export const dark = {
  name: "dark",
  bg: "#0B1011",
  surface: "#141B1C",
  surfaceRaised: "#1A2324",
  border: "rgba(226,236,237,0.12)",
  borderBright: "rgba(226,236,237,0.26)",
  accent: "#5CC6D1",
  accentText: "#06110F",
  accentGlow: "rgba(92,198,209,0.16)",
  accent2: "#A99BFF",
  accent2Glow: "rgba(169,155,255,0.14)",
  brand: "#4AB7C3",
  text: "#E7EEEE",
  textMuted: "rgba(231,238,238,0.66)",
  textDim: "rgba(231,238,238,0.32)",

  sidebarBg: "#000000",
  sidebarText: "rgba(231,238,238,0.78)",
  sidebarActive: "rgba(74,183,195,0.28)",
  sidebarActiveText: "#FFFFFF",
  sidebarBorder: "rgba(231,238,238,0.12)",
  sidebarMark: "#4AB7C3",
  sidebarMuted: "rgba(231,238,238,0.60)",
  sidebarGroup: "rgba(231,238,238,0.44)",

  headerBg: "#101617",
  headerText: "#E7EEEE",
  headerMuted: "rgba(231,238,238,0.62)",
  headerBorder: "rgba(231,238,238,0.10)",
  headerAccent: "#5CC6D1",

  ctaBg: "#4AB7C3",
  ctaText: "#000000",
  ctaHoverBg: "#FFFFFF",
  ctaHoverText: "#000000",

  cardRule: "#4AB7C3",
  tableHead: "#1B2526",
  statHeroBg: "#1D4F55",
  statHeroText: "#FFFFFF",
  statHeroMuted: "rgba(255,255,255,0.76)",
  rowHover: "rgba(92,198,209,0.08)",
  rowDivider: "rgba(231,238,238,0.08)",
  grid: "rgba(231,238,238,0.10)",
  code: "rgba(231,238,238,0.08)",
  labelColBg: "rgba(0,0,0,0.26)",
  series: ["#5CC6D1", "#E7EEEE", "#7E9396", "#E0935F"],
  status: { good: "#5FCFA4", warning: "#E6B655", serious: "#E0935F", critical: "#F0808F", neutral: "#A9B8BA", ai: "#A99BFF" },
  statusBg: {
    good: "rgba(95,207,164,0.14)", warning: "rgba(230,182,85,0.16)", serious: "rgba(224,147,95,0.16)",
    critical: "rgba(240,128,143,0.14)", neutral: "rgba(231,238,238,0.08)", ai: "rgba(169,155,255,0.16)",
  },
  dot: { grey: "rgba(255,255,255,0.22)", green: "#5FCFA4", yellow: "#E6B655", blue: "#5CC6D1", red: "#F0808F" },
  dotGlow: { green: "rgba(95,207,164,0.14)", yellow: "rgba(230,182,85,0.16)", blue: "rgba(92,198,209,0.16)", red: "rgba(240,128,143,0.14)" },
};

const Ctx = createContext(null);
const KEY = "plexxcon-demo:theme";

export function ThemeProvider({ children }) {
  const [isDark, setIsDark] = useState(() => {
    try { return localStorage.getItem(KEY) === "dark"; } catch { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem(KEY, isDark ? "dark" : "light"); } catch { /* storage blocked */ }
    document.body.style.background = (isDark ? dark : light).bg;
  }, [isDark]);
  return (
    <Ctx.Provider value={{ t: isDark ? dark : light, isDark, toggle: () => setIsDark((v) => !v) }}>
      {children}
    </Ctx.Provider>
  );
}

export function useTheme() {
  return useContext(Ctx);
}
