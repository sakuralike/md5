import { readonly, ref, type Ref } from "vue";

export type Theme = "light" | "dark";

export interface ThemeState {
  readonly theme: Readonly<Ref<Theme>>;
}

export const THEME_STORAGE_KEY = "pd-theme";

const mutableTheme = ref<Theme>("light");
const themeState: ThemeState = {
  theme: readonly(mutableTheme),
};

let initialized = false;
let storageListenerAttached = false;

function isTheme(value: string | null): value is Theme {
  return value === "light" || value === "dark";
}

function systemTheme(): Theme {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "light";
  }

  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function storedTheme(): Theme {
  if (typeof window === "undefined") return systemTheme();

  try {
    const storedValue = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(storedValue) ? storedValue : systemTheme();
  } catch {
    return systemTheme();
  }
}

function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;

  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
}

function updateTheme(theme: Theme, persist: boolean): void {
  mutableTheme.value = theme;
  applyTheme(theme);

  if (!persist || typeof window === "undefined") return;

  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }
}

function syncThemeFromStorage(event: StorageEvent): void {
  if (event.key !== THEME_STORAGE_KEY && event.key !== null) return;

  updateTheme(isTheme(event.newValue) ? event.newValue : systemTheme(), false);
}

export function initializeTheme(): ThemeState {
  if (typeof window === "undefined") return themeState;

  if (!initialized) {
    updateTheme(storedTheme(), false);
    initialized = true;
  } else {
    applyTheme(mutableTheme.value);
  }

  if (!storageListenerAttached) {
    window.addEventListener("storage", syncThemeFromStorage);
    storageListenerAttached = true;
  }

  return themeState;
}

export function useTheme(): ThemeState {
  return themeState;
}

export function setTheme(theme: Theme): void {
  updateTheme(theme, true);
}

export function toggleTheme(): void {
  setTheme(mutableTheme.value === "light" ? "dark" : "light");
}
