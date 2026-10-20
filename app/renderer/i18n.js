// t(key, params): the interface's texts come from the locale files, never
// from the markup or the code. The language is chosen in the interface and
// remembered in this browser profile; English until someone picks another
// (the owner, 2026-10-20: English first, Russian second; it was the other
// way round).
// Adding a language means adding a locale file, its flag and a line below.
(function (root) {
  const STORAGE_KEY = 'work-ide-language';
  const DEFAULT_LANGUAGE = 'en';
  const LOCALES = {
    en: root.LOCALE_EN || {},
    ru: root.LOCALE_RU || {},
  };

  function stored() {
    try {
      return root.localStorage ? root.localStorage.getItem(STORAGE_KEY) : null;
    } catch {
      return null;   // storage unavailable: the default language
    }
  }

  let current = Object.prototype.hasOwnProperty.call(LOCALES, stored()) ? stored() : DEFAULT_LANGUAGE;

  function t(key, params, language) {
    const locale = LOCALES[language || current];
    let text = Object.prototype.hasOwnProperty.call(locale, key) ? locale[key] : null;
    if (text === null) {
      console.warn(`missing text: ${key}`);
      return key;
    }
    if (params) {
      text = text.replace(/\{(\w+)\}/g, (match, name) =>
        (Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match));
    }
    return text;
  }

  function setLanguage(language) {
    if (!Object.prototype.hasOwnProperty.call(LOCALES, language)) return false;
    current = language;
    try {
      if (root.localStorage) root.localStorage.setItem(STORAGE_KEY, language);
    } catch {
      // not remembered: the choice holds until the page reloads
    }
    if (root.document) root.document.documentElement.lang = language;
    return true;
  }

  if (root.document) root.document.documentElement.lang = current;

  root.t = t;
  root.I18n = {
    languages: Object.keys(LOCALES),
    language: () => current,
    setLanguage,
  };
}(typeof self !== 'undefined' ? self : this));
