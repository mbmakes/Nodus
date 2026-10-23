/* Tema, sayfa boyanmadan once uygulanir (yanip sonmeyi onler). Tercih: 'system' | 'light' | 'dark'. */
(function () {
  var pref = 'system';
  try { pref = localStorage.getItem('nodus.theme') || 'system'; } catch (e) {}
  var dark = pref === 'dark' || (pref === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  window.nodusTheme = function (next) {
    try { localStorage.setItem('nodus.theme', next); } catch (e) {}
    var d = next === 'dark' || (next === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.setAttribute('data-theme', d ? 'dark' : 'light');
  };
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
    var p = 'system';
    try { p = localStorage.getItem('nodus.theme') || 'system'; } catch (e) {}
    if (p === 'system') window.nodusTheme('system');
  });
})();
