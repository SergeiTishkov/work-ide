'use strict';
// The SQL function fold(text) the text filter compares with (WORDS in
// schemas/queries.sql; tools/db.py registers the same one for Python): lower
// case in every alphabet (Cyrillic, Greek...), accents dropped — "Zürich",
// "ZURICH" and "zurich" are one word. Lower case first: "İ" lowers to "i"
// plus a dot mark, which the second step drops.
function fold(text) {
  if (text == null) return null;
  return String(text).toLowerCase().normalize('NFKD').replace(/\p{M}/gu, '');
}

function addFold(db) {
  db.function('fold', { deterministic: true }, fold);
}

module.exports = { fold, addFold };
