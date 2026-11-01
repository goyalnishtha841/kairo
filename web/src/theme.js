// Light / dark theme for the dashboard: follows the system setting until the user picks one, then remembers it.
const KEY = "kairo-theme";

function stored() {
  try { return localStorage.getItem(KEY); } catch { return null; }
}

export function initialTheme() {
  const s = stored();
  if (s === "light" || s === "dark") return s;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
}

export function saveTheme(theme) {
  try { localStorage.setItem(KEY, theme); } catch { /* private mode: the switch still works for this visit */ }
}
