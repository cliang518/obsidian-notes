import { reactive } from "vue";

const THEME_KEY = "yj_v2_theme";

function normalizeTheme(value) {
  return value === "dark" ? "dark" : "light";
}

function syncDocumentTheme(mode) {
  if (typeof document === "undefined") {
    return;
  }

  const root = document.documentElement;
  root.classList.toggle("dark", mode === "dark");
  root.dataset.theme = mode;
}

export const themeState = reactive({
  mode: normalizeTheme(typeof window !== "undefined" ? localStorage.getItem(THEME_KEY) || "dark" : "dark"),
});

export function setThemeMode(mode) {
  const nextMode = normalizeTheme(mode);
  themeState.mode = nextMode;
  if (typeof window !== "undefined") {
    localStorage.setItem(THEME_KEY, nextMode);
  }
  syncDocumentTheme(nextMode);
}

export function syncThemeDocument() {
  syncDocumentTheme(themeState.mode);
}
