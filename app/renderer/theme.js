// The colour theme: "system" follows Windows, "light" and "dark" hold whatever
// Windows says. Chosen in the top bar, remembered in this browser profile like
// the language. Loaded in <head>, before the first paint, so a dark choice
// does not flash light on start. styles.css reads html[data-theme].
(function (root) {
  const STORAGE_KEY = 'work-ide-theme';
  const THEMES = ['system', 'light', 'dark'];

  function stored() {
    try {
      return root.localStorage ? root.localStorage.getItem(STORAGE_KEY) : null;
    } catch {
      return null;   // storage unavailable: the system's theme
    }
  }

  let current = THEMES.includes(stored()) ? stored() : 'system';

  function apply() {
    if (!root.document) return;
    const html = root.document.documentElement;
    if (current === 'system') delete html.dataset.theme;
    else html.dataset.theme = current;
  }

  function setTheme(theme) {
    if (!THEMES.includes(theme)) return false;
    current = theme;
    try {
      if (root.localStorage) root.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // not remembered: the choice holds until the page reloads
    }
    apply();
    return true;
  }

  apply();

  root.Theme = {
    themes: THEMES,
    theme: () => current,
    setTheme,
  };
}(typeof self !== 'undefined' ? self : this));
