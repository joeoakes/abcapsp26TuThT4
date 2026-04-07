const STORAGE_KEY = "dashboard.theme";
const DEFAULT_THEME = "obsidian";
const ALLOWED_THEMES = new Set(["obsidian", "polar", "monolith"]);

function normalizeTheme(themeName) {
  if (!themeName) {
    return DEFAULT_THEME;
  }
  return ALLOWED_THEMES.has(themeName) ? themeName : DEFAULT_THEME;
}

function setTheme(themeName) {
  const theme = normalizeTheme(themeName);
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(STORAGE_KEY, theme);
  return theme;
}

function getStoredTheme() {
  return normalizeTheme(localStorage.getItem(STORAGE_KEY));
}

export function initThemeEngine(selectElement) {
  const initialTheme = setTheme(getStoredTheme());
  if (selectElement) {
    selectElement.value = initialTheme;
    selectElement.addEventListener("change", (event) => {
      setTheme(event.target.value);
    });
  }
  return {
    getTheme: () => normalizeTheme(document.documentElement.getAttribute("data-theme")),
    setTheme
  };
}
