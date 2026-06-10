import React, { createContext, useContext, useEffect, useState } from "react";

export const PALETTES = [
  { name: "Steel",  bg: "#0e1318", surface: "#090e12", border: "#1c2830", accent: "#94a3b8", muted: "#4a5a68", fg: "#e2e8f0" },
  { name: "Forest", bg: "#0d1f17", surface: "#0a1a10", border: "#1a3a25", accent: "#5fba8a", muted: "#6b8f78", fg: "#d4ede0" },
  { name: "Ocean",  bg: "#041018", surface: "#030c12", border: "#082030", accent: "#0ea5e9", muted: "#3a6880", fg: "#cceeff" },
] as const;

export type Palette = typeof PALETTES[number];

const STORAGE_KEY = "cf-theme";

function applyPalette(p: Palette) {
  const r = document.documentElement;
  r.style.setProperty("--cf-bg",      p.bg);
  r.style.setProperty("--cf-surface", p.surface);
  r.style.setProperty("--cf-border",  p.border);
  r.style.setProperty("--cf-accent",  p.accent);
  r.style.setProperty("--cf-muted",   p.muted);
  r.style.setProperty("--cf-text",    p.fg);
}

interface ThemeCtx {
  currentIndex: number;
  currentPalette: Palette;
  setPalette: (index: number) => void;
}

const ThemeContext = createContext<ThemeCtx>({
  currentIndex: 0,
  currentPalette: PALETTES[0],
  setPalette: () => {},
});

export function usePalette() {
  return useContext(ThemeContext);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    const saved = parseInt(localStorage.getItem(STORAGE_KEY) ?? "0", 10);
    const idx = Number.isFinite(saved) && saved >= 0 && saved < PALETTES.length ? saved : 0;
    setCurrentIndex(idx);
    applyPalette(PALETTES[idx]);
  }, []);

  function setPalette(index: number) {
    localStorage.setItem(STORAGE_KEY, String(index));
    setCurrentIndex(index);
    applyPalette(PALETTES[index]);
  }

  return (
    <ThemeContext.Provider value={{ currentIndex, currentPalette: PALETTES[currentIndex], setPalette }}>
      {children}
    </ThemeContext.Provider>
  );
}
