import { createContext, useContext, useEffect, useState, useCallback } from 'react';

const STORAGE_KEY = 'dbcare.settings.v1';

export const DEFAULT_SETTINGS = {
  hospitalName: '',
  departmentName: '',
  accentColor: '#6366f1',
  theme: 'light',
  density: 'comfortable',
  autoScenarioDebounce: 300,
  showEnglishLabels: true,
};

// shade a hex by a positive (lighten) or negative (darken) amount [-100, 100]
function shade(hex, percent) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex || '');
  if (!m) return hex;
  let r = parseInt(m[1], 16);
  let g = parseInt(m[2], 16);
  let b = parseInt(m[3], 16);
  const t = percent < 0 ? 0 : 255;
  const p = Math.abs(percent) / 100;
  r = Math.round((t - r) * p) + r;
  g = Math.round((t - g) * p) + g;
  b = Math.round((t - b) * p) + b;
  return '#' + [r, g, b].map((x) => x.toString(16).padStart(2, '0')).join('');
}

function hexToRgba(hex, a) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex || '');
  if (!m) return `rgba(99, 102, 241, ${a})`;
  return `rgba(${parseInt(m[1], 16)}, ${parseInt(m[2], 16)}, ${parseInt(m[3], 16)}, ${a})`;
}

export function applyTheme(settings) {
  const root = document.documentElement;
  const accent = settings.accentColor || DEFAULT_SETTINGS.accentColor;
  root.style.setProperty('--db-accent', accent);
  root.style.setProperty('--db-accent-dark', shade(accent, -18));
  root.style.setProperty('--db-accent-soft', shade(accent, 88));
  root.style.setProperty('--db-accent-ring', hexToRgba(accent, 0.32));
  root.dataset.density = settings.density || 'comfortable';
}

const ThemeContext = createContext({
  settings: DEFAULT_SETTINGS,
  setSettings: () => {},
  saveSettings: () => {},
  resetSettings: () => {},
});

export function ThemeProvider({ children }) {
  const [settings, setSettingsState] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? { ...DEFAULT_SETTINGS, ...JSON.parse(raw) } : DEFAULT_SETTINGS;
    } catch (e) {
      return DEFAULT_SETTINGS;
    }
  });

  // Apply theme on every settings change
  useEffect(() => {
    applyTheme(settings);
  }, [settings]);

  const setSettings = useCallback((updater) => {
    setSettingsState((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : { ...prev, ...updater };
      return next;
    });
  }, []);

  const saveSettings = useCallback((next) => {
    const value = next || settings;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    } catch (e) { /* noop */ }
  }, [settings]);

  const resetSettings = useCallback(() => {
    setSettingsState(DEFAULT_SETTINGS);
    try { localStorage.removeItem(STORAGE_KEY); } catch (e) { /* noop */ }
  }, []);

  return (
    <ThemeContext.Provider value={{ settings, setSettings, saveSettings, resetSettings }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
