import { useState } from "react";

export type Theme = "light" | "dark";

// Read the current theme from the <html> element (set before paint in index.html).
export function getTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

// A tiny hook that flips light/dark, updates <html>, and remembers the choice.
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(getTheme);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    const root = document.documentElement;
    if (next === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
    try {
      localStorage.setItem("theme", next);
    } catch {
      // Ignore storage errors (private mode, etc.) — the toggle still works.
    }
    setTheme(next);
  }

  return { theme, toggle };
}
