/* Sesli komutların anlamı. Saf fonksiyonlar (DOM yok): hem tarayıcıda (window.nodusIntent) hem Node testinde (require) çalışır.
   Güvenlik: sesli ONAY yalnızca kısa ve net ifadelerle verilir; olumsuz bir kelime geçiyorsa her zaman RET sayılır;
   belirsiz her şey "anlaşılmadı" olur ve onay verilmiş sayılmaz. */
(function (root) {
  'use strict';
  const norm = (t) => String(t || '').toLocaleLowerCase('tr').replace(/[.,!?;:"'’“”()]/g, ' ').replace(/\s+/g, ' ').replace(/^nodus /, '').trim();

  const NO_WORDS = new Set(['hayır', 'hayir', 'yapma', 'yapmayın', 'yapmayalım', 'reddet', 'vazgeç', 'vazgeçtim', 'iptal', 'olmaz', 'dur', 'durdur',
    'istemiyorum', 'sakın', 'değil', 'hayırdır']);
  const YES_PHRASES = new Set(['evet', 'evet yap', 'evet onayla', 'onayla', 'onaylıyorum', 'onay veriyorum', 'tamam yap', 'yap', 'yapabilirsin',
    'evet yapabilirsin', 'devam et', 'evet devam et', 'olur']);
  const ASK_PHRASES = new Set(['onay iste', 'onay sor', 'bana sor', 'önce bana sor', 'onaylı çalış', 'onaylı mod']);
  const AUTO_PHRASES = new Set(['onaysız çalış', 'onaysız mod', 'onay sorma', 'sormadan çalış']);

  // true: onay, false: ret, null: anlaşılmadı. Önce ret aranır; "yapma" gibi bir söz asla onay sayılmaz.
  function approval(text) {
    const t = norm(text), words = t.split(' ');
    if (!t || words.length > 4) return null;
    if (words.some((w) => NO_WORDS.has(w))) return false;
    return YES_PHRASES.has(t) ? true : null;
  }
  // 'ask' | 'auto' | null: yalnızca bütün cümle bu ifadelerden biriyse mod değişir (konuşmanın ortasında geçen sözcük değiştirmez)
  function mode(text) {
    const t = norm(text);
    return ASK_PHRASES.has(t) ? 'ask' : AUTO_PHRASES.has(t) ? 'auto' : null;
  }
  // Tanıma, Nodus'un az önce söylediği cümlenin (yankının) bir parçasıysa gerçek kullanıcı sözü değildir
  function isEcho(heard, spoken) {
    const h = norm(heard), s = norm(spoken);
    return h.length >= 6 && s.includes(h);
  }

  const api = { norm, approval, mode, isEcho };
  root.nodusIntent = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
