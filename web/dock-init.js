/* Yan panelin ilk boyamada doğru durumda olması: app.js yüklenene kadar telefonda panel tam ekran açık görünüyordu.
   Satır içi betiğe CSP izin vermediği için ayrı dosya. Mantık app.js boot() ile aynı. */
(function () {
  var open = innerWidth > 1180;
  try {
    var saved = localStorage.getItem('nodus.dock');
    if (saved !== null) open = saved === '1' && innerWidth > 1180;
  } catch (e) { /* gizli pencere: genişliğe göre */ }
  document.getElementById('shell').dataset.dock = open ? 'open' : 'closed';
})();
