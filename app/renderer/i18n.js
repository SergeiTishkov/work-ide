// t(key, params): the interface's texts come from the locale file, never
// from the markup or the code. Only Russian exists today; adding a language
// means adding a locale file and choosing it here.
(function (root) {
  const locale = root.LOCALE_RU || {};

  function t(key, params) {
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

  root.t = t;
}(typeof self !== 'undefined' ? self : this));
