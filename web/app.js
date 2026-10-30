/* Nodus arayuzu. Sunucu: server.py (/api/*). Bagimlilik: marked, DOMPurify, highlight.js, KaTeX (web/vendor). */
(() => {
'use strict';

// ------------------------------------------------------------------ yardimcilar
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
function el(tag, props, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'text') n.textContent = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) n.append(c.nodeType ? c : document.createTextNode(c));
  return n;
}
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const LS = {
  get(k, d) { try { const v = localStorage.getItem('nodus.' + k); return v === null ? d : v; } catch { return d; } },
  set(k, v) { try { localStorage.setItem('nodus.' + k, v); } catch { /* gizli pencere */ } },
};
const fileUrl = (p, dl) => '/api/file?path=' + encodeURIComponent(p) + (dl ? '&download=1' : '');
const secs = (ms) => (ms < 1000 ? '<1 sn' : Math.round(ms / 1000) + ' sn');

const TOOL_LABEL = {
  execute_code: 'Kod çalıştır', execute_python_code: 'Kod çalıştır', run_file: 'Dosya çalıştır', run_shell: 'Komut çalıştır', open_app: 'Uygulama aç', save_user_file: 'Dosya yaz (masaüstü vb.)',
  web_search: 'Web araması', fetch_url: 'Sayfa oku', browse_url: 'Tarayıcıda aç', read_file: 'Dosya oku', write_file: 'Dosya yaz',
  list_files: 'Dosyaları listele', apply_patch: 'Yama uygula', search_codebase: 'Dosyalarda ara', solve_math: 'Sembolik çözüm',
  solve_symbolic_math: 'Sembolik çözüm', read_document: 'Belge oku', export_report: 'Rapor üret', delete_file: 'Dosya sil',
  self_improve: 'Yeni araç ekle', eng_calc: 'Mühendislik hesabı', call_custom_tool: 'Özel araç', update_plan: 'Plan güncelle', remember: 'Not al', recall: 'Notlarda ara',
};
const STARTERS = [
  { cat: 'Akışkanlar', title: 'Borudaki basınç kaybını hesapla', desc: 'Darcy-Weisbach, Reynolds sayısı ve sürtünme katsayısıyla',
    prompt: 'Çapı 50 mm, uzunluğu 100 m olan pürüzsüz bir borudan 20 °C suyla 5 L/s akarken basınç kaybını hesapla.' },
  { cat: 'Mukavemet', title: 'Ankastre kirişin sehimini çöz', desc: 'Uç yükü altında maksimum sehim ve gerilme',
    prompt: 'Boyu 2 m, 40x40 mm çelik kare profilli ankastre bir kirişin ucuna 500 N yük gelirse maksimum sehim ve gerilmeyi hesapla.' },
  { cat: 'Termodinamik', title: 'Su buharı özelliklerini tabloya dök', desc: 'CoolProp ile doymuş buhar, 1 – 10 bar',
    prompt: 'Doymuş su buharının 1 ile 10 bar arasındaki sıcaklık, entalpi ve entropi değerlerini tablo olarak ver.' },
  { cat: 'Veri', title: 'Excel ya da PDF yükleyip analiz et', desc: 'Dosyayı ekle, ne yapılacağını yaz', attach: true },
];

// ------------------------------------------------------------------ durum
const S = {
  sid: null, sessions: [], msgs: [], pending: null, busy: false, run: null,
  models: ['auto'], model: LS.get('model', 'auto'), verify: LS.get('verify', '1') === '1', autoExec: LS.get('auto', '0') === '1',
  facts: [], files: [], plan: [], sandbox: { ok: false, why: '' }, providers: [], usage: [], audio: false,
  attach: [], tab: LS.get('tab', 'out'), preview: null, search: '', hits: null, rested: null, version: '', update: null, keys: {}, needsKeys: false,
};

// ------------------------------------------------------------------ ag
async function api(path, opts = {}) {
  const r = await fetch('/api' + path, { ...opts, headers: { 'X-Nodus': '1', ...(opts.headers || {}) } });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}
const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });

async function stream(path, body, isJson) {
  const r = await fetch('/api' + path, {
    method: 'POST', body: isJson ? JSON.stringify(body) : body,
    headers: { 'X-Nodus': '1', ...(isJson ? { 'Content-Type': 'application/json' } : {}) },
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  const reader = r.body.getReader(), dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
      if (chunk.startsWith('data: ')) onEvent(JSON.parse(chunk.slice(6)));
    }
  }
}

function toast(msg) {
  const t = el('div', { class: 'toast', text: msg });
  $('#toasts').append(t);
  setTimeout(() => t.remove(), 6000);
}

// ------------------------------------------------------------------ markdown
function mdToHtml(src) {
  const math = [];
  const guarded = String(src).replace(/\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$(?=[^\s$])[^$\n]*?[^\s$]\$(?!\d)|\$[^\s$]\$/g, (m) => { math.push(m); return `@@M${math.length - 1}@@`; });
  const html = DOMPurify.sanitize(marked.parse(guarded, { gfm: true, breaks: true }));
  return html.replace(/@@M(\d+)@@/g, (_, i) => esc(math[+i]));
}

function enhance(root, final) {
  $$('pre', root).forEach((pre) => {
    if (pre.parentElement.classList.contains('code')) return;
    const code = $('code', pre);
    const lang = ((code && code.className.match(/language-([\w+-]+)/)) || [])[1] || '';
    const head = el('div', { class: 'code-head' }, el('span', { text: lang || 'kod' }),
      el('button', { type: 'button', text: 'Kopyala', onclick: (e) => copy(pre.innerText, e.currentTarget) }));
    const wrap = el('div', { class: 'code' });
    pre.replaceWith(wrap);
    wrap.append(head, pre);
    if (final && code && lang && window.hljs && hljs.getLanguage(lang)) { try { hljs.highlightElement(code); } catch { /* vurgulama olmadan da okunur */ } }
  });
  $$('table', root).forEach((t) => {
    if (t.parentElement.classList.contains('table-wrap')) return;
    const w = el('div', { class: 'table-wrap' });
    t.replaceWith(w); w.append(t);
  });
  $$('p', root).forEach((p) => {
    const t = p.textContent;
    if (t.startsWith('Bağımsız model doğrulaması')) p.classList.add('verdict');
    else if (t.startsWith('Çapraz doğrulama uyarısı')) p.classList.add('verdict', 'warn');
  });
  $$('a', root).forEach((a) => { a.target = '_blank'; a.rel = 'noopener noreferrer'; });
  $$('img', root).forEach((img) => {
    const src = img.getAttribute('src') || '';
    if (src && !/^(https?:|data:|blob:|\/)/.test(src)) img.src = fileUrl(src);
    img.addEventListener('click', () => openLightbox(img.src));
  });
  if (final && window.renderMathInElement) {
    renderMathInElement(root, {
      delimiters: [{ left: '$$', right: '$$', display: true }, { left: '\\[', right: '\\]', display: true }, { left: '\\(', right: '\\)', display: false }, { left: '$', right: '$', display: false }],
      throwOnError: false,
    });
  }
}

async function exportReport(format, btn) {
  const old = btn.textContent; btn.textContent = 'Hazırlanıyor…'; btn.disabled = true;
  try {
    const d = await post('/export', { sid: S.sid, format });
    const a = el('a', { href: fileUrl(d.path, true), download: d.path.split('/').pop() });
    document.body.append(a); a.click(); a.remove();
    refreshData();
  } catch (e) { toast(e.message); }
  btn.textContent = old; btn.disabled = false;
}

async function copy(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    if (btn) { const old = btn.textContent; btn.textContent = 'Kopyalandı'; setTimeout(() => (btn.textContent = old), 1400); }
  } catch { toast('Panoya kopyalanamadı.'); }
}

// ------------------------------------------------------------------ tema / yerlesim
function applyTheme(pref) { window.nodusTheme(pref); renderSettingsIfOpen(); }
function setDock(open) {
  $('#shell').dataset.dock = open ? 'open' : 'closed';
  $('#dock-toggle').setAttribute('aria-pressed', String(open));
  LS.set('dock', open ? '1' : '0');
}
const dockOpen = () => $('#shell').dataset.dock === 'open';
function setRail(open) { $('#shell').dataset.rail = open ? 'open' : 'closed'; }

// ------------------------------------------------------------------ sol ray
function groupOf(mtime) {
  const now = new Date(), d = new Date(mtime * 1000);
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 864e5);
  return diff <= 0 ? 'Bugün' : diff === 1 ? 'Dün' : diff < 7 ? 'Bu hafta' : 'Daha eski';
}

function renderRail() {
  const list = $('#session-list');
  list.replaceChildren();
  const q = S.search.trim().toLocaleLowerCase('tr');
  const items = S.sessions.filter((s) => !q || s.title.toLocaleLowerCase('tr').includes(q) || (S.hits && S.hits.has(s.id)));
  if (!items.length) list.append(el('div', { class: 'rail-empty', text: q ? 'Eşleşen görev yok.' : 'Henüz görev yok.' }));
  let last = '';
  for (const s of items) {
    const g = groupOf(s.mtime);
    if (g !== last) { list.append(el('div', { class: 'grp', text: g })); last = g; }
    list.append(el('div', { class: 's-item', ...(s.id === S.sid ? { 'aria-current': 'true' } : {}) },
      el('button', { class: 's-open', type: 'button', title: s.title, text: s.title, onclick: () => openSession(s.id) }),
      el('button', { class: 'icon-btn s-del', type: 'button', 'aria-label': 'Görevi sil', onclick: () => removeSession(s.id),
        html: null }, delIcon())));
  }
  const pv = $('#provider-line');
  pv.replaceChildren(...S.providers.map((p) => el('span', { class: 'pv', title: `${p.model_sayisi} model` + (p.dinlenen ? ' (dinleniyor)' : '') },
    el('i', { class: 'dot ' + (p.dinlenen ? 'rest' : 'ok') }), p.saglayici)));
}
function delIcon() {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 20 20'); s.setAttribute('aria-hidden', 'true');
  s.innerHTML = '<path d="m6 6 8 8M14 6l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>';
  return s;
}

function currentTitle() {
  const s = S.sessions.find((x) => x.id === S.sid);
  if (s) return s.title;
  const first = S.msgs.find((m) => m.role === 'user');
  return first ? first.content.replace(/\s+/g, ' ').slice(0, 50) : 'Yeni görev';
}
function modelLabel(v) { return v === 'auto' ? 'Otomatik' : v.includes('::') ? v.split('::')[1] : v.replace(' (Yerel Ollama)', ' · yerel'); }
function modelProv(v) { return v.includes('::') ? v.split('::')[0] : v === 'auto' ? 'yönlendirici' : 'yerel'; }

function renderTitle() {
  $('#task-title').textContent = currentTitle();
  document.title = (S.msgs.length ? currentTitle() + ' · ' : '') + 'Nodus';
  $('#model-label').textContent = modelLabel(S.model);
  const c = $('#sandbox-cell');
  $('i', c).className = 'dot ' + (S.sandbox.ok ? 'ok' : '');
  $('span', c).textContent = S.sandbox.ok ? 'Sandbox açık' : 'Sandbox kapalı';
  c.title = S.sandbox.why || '';
}

// ------------------------------------------------------------------ hesap foyu
function splitFiles(content) {
  const files = [];
  const text = content.replace(/\n*Ek: `([^`]+)`/g, (_, p) => { files.push(p); return ''; }).trim();
  return { text, files };
}

function taskEl(m) {
  const parsed = splitFiles(m.content);
  const files = m.files && m.files.length ? m.files : parsed.files;
  return el('article', { class: 'turn' }, el('div', { class: 'task' }, parsed.text,
    files.length ? el('div', { class: 'task-files' }, files.map((f) => el('span', { text: f }))) : null));
}

function figsEl(images, figNo) {
  return el('div', { class: 'figs' }, images.map((p) => {
    const n = figNo.get(p) || 1, name = p.split('/').pop();
    const img = el('img', { src: fileUrl(p), alt: 'Şekil ' + n + ': ' + name });
    img.addEventListener('click', () => openLightbox(fileUrl(p)));
    return el('figure', { class: 'fig' }, img, el('figcaption', {}, el('span', {}, el('b', { text: 'Şekil ' + n }), name),
      el('a', { href: fileUrl(p, true), download: name, text: 'İndir' })));
  }));
}

function stepsEl(steps, running) {
  const tools = steps.filter((s) => s.tool);
  if (!tools.length) return null;
  const total = steps.reduce((a, s) => a + (s.ms || 0), 0);
  const summary = el('summary', {},
    running ? el('i', { class: 'spin' }) : chevron(),
    running ? ((S.run && S.run.label) || 'Çalışıyor') : `Hesaplama adımları · ${tools.length} adım${total ? ' · ' + secs(total) : ''}`);
  const ol = el('ol', {}, steps.map((s) => s.tool
    ? el('li', { class: s.state }, el('span', { class: 'n', text: s.n }),
        el('span', { class: 't' }, TOOL_LABEL[s.tool] || s.tool, el('code', { text: s.tool })),
        el('span', { class: 's', text: s.state === 'run' ? 'çalışıyor' : s.ms ? secs(s.ms) : 'tamam' }))
    : el('li', { class: 'note' + (s.warn ? ' warn' : '') }, el('span', { class: 'n', text: '·' }), el('span', { class: 't', text: s.note }))));
  return el('details', { class: 'steps', ...(running ? { open: '' } : {}) }, summary, ol);
}
function chevron() {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('class', 'tw'); s.setAttribute('viewBox', '0 0 12 12'); s.setAttribute('aria-hidden', 'true');
  s.innerHTML = '<path d="m4 2 4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>';
  return s;
}

function botEl(m, figNo, last) {
  const art = el('article', { class: 'turn bot' });
  const st = m.steps && stepsEl(m.steps, false);
  if (st) art.append(st);
  if (m.content) {
    const prose = el('div', { class: 'prose' });
    prose.innerHTML = mdToHtml(m.content);
    enhance(prose, true);
    art.append(prose);
  }
  if (m.images && m.images.length) art.append(figsEl(m.images, figNo));
  if (m.content) {
    art.append(el('div', { class: 'turn-actions' }, el('button', { type: 'button', text: 'Kopyala', onclick: (e) => copy(m.content, e.currentTarget) }),
      last ? el('button', { type: 'button', text: 'Rapor (Word)', onclick: (e) => exportReport('docx', e.currentTarget) }) : null,
      last ? el('button', { type: 'button', text: 'Rapor (PDF)', onclick: (e) => exportReport('pdf', e.currentTarget) }) : null));
  }
  return art;
}

function figureNumbers() {
  const map = new Map();
  for (const m of S.msgs) for (const p of m.images || []) if (!map.has(p)) map.set(p, map.size + 1);
  return map;
}

function userTemplates() { try { return JSON.parse(LS.get('templates', '[]')).filter((t) => t && t.title && t.prompt).slice(0, 12); } catch { return []; } }
function saveTemplates(list) { LS.set('templates', JSON.stringify(list)); renderSheet(); }

function templateForm() {
  const title = el('input', { type: 'text', placeholder: 'Şablon adı', 'aria-label': 'Şablon adı', maxlength: '60' });
  const prompt = el('textarea', { rows: '3', placeholder: 'Görev metni', 'aria-label': 'Görev metni', maxlength: '2000' });
  return el('form', { class: 'tpl-form', onsubmit: (e) => {
    e.preventDefault();
    if (!title.value.trim() || !prompt.value.trim()) return;
    saveTemplates([...userTemplates(), { title: title.value.trim(), prompt: prompt.value.trim() }]);
  } }, title, prompt, el('div', { class: 'row-btns' },
    el('button', { class: 'btn btn-ink btn-sm', type: 'submit', text: 'Şablonu kaydet' }),
    el('button', { class: 'btn btn-sm', type: 'button', text: 'Vazgeç', onclick: () => renderSheet() })));
}

function emptyEl() {
  const mine = userTemplates();
  return el('section', { class: 'empty' },
    el('h1', { text: 'Ne üzerinde çalışıyoruz?' }),
    el('p', { text: 'Hesabı, analizi ya da araştırmayı yaz. Görsel, PDF, Excel veya Word dosyası ekleyebilirsin.' }),
    el('div', { class: 'register' }, STARTERS.map((s) => el('button', { class: 'reg-row', type: 'button',
      onclick: () => (s.attach ? $('#file-input').click() : sendText(s.prompt)) },
      el('span', { class: 'reg-cat', text: s.cat }), el('span', { class: 'reg-main' }, el('b', { text: s.title }), el('small', { text: s.desc })))),
      mine.map((t, i) => el('div', { class: 'reg-mine' },
        el('button', { class: 'reg-row', type: 'button', onclick: () => sendText(t.prompt) },
          el('span', { class: 'reg-cat', text: 'Şablonum' }), el('span', { class: 'reg-main' }, el('b', { text: t.title }), el('small', { text: t.prompt.slice(0, 90) }))),
        el('button', { class: 'icon-btn', type: 'button', 'aria-label': t.title + ' şablonunu sil', onclick: () => saveTemplates(mine.filter((_, j) => j !== i)) }, delIcon())))),
    el('div', { class: 'tpl-add' }, el('button', { class: 'btn btn-sm', type: 'button', text: '+ Kendi şablonunu ekle',
      onclick: (e) => e.currentTarget.replaceWith(templateForm()) })));
}

function renderSheet(keepScroll) {
  const sheet = $('#sheet'), inner = $('#sheet-inner');
  const near = sheet.scrollHeight - sheet.scrollTop - sheet.clientHeight < 140;
  const figNo = figureNumbers();
  inner.replaceChildren();
  if (!S.msgs.length && !S.run && !S.pending) inner.append(emptyEl());
  const lastBot = S.msgs.map((m) => m.role).lastIndexOf('assistant');
  S.msgs.forEach((m, i) => inner.append(m.role === 'user' ? taskEl(m) : botEl(m, figNo, i === lastBot && !S.pending)));
  if (S.run) { inner.append(el('article', { class: 'turn bot', id: 'run-block' })); paintRun(); }
  if (!keepScroll || near) sheet.scrollTop = sheet.scrollHeight;
}

let paintQueued = false;
function schedulePaint() { if (!paintQueued) { paintQueued = true; requestAnimationFrame(() => { paintQueued = false; paintRun(); }); } }

function paintRun() {
  const b = $('#run-block');
  if (!b || !S.run) return;
  const sheet = $('#sheet');
  const near = sheet.scrollHeight - sheet.scrollTop - sheet.clientHeight < 140;
  const open = $('details', b) ? $('details', b).open : true;
  b.replaceChildren();
  const hasTools = S.run.steps.some((s) => s.tool);
  const st = stepsEl(S.run.steps, true);
  if (st) { st.open = open; b.append(st); }
  if (!hasTools && !S.run.live) b.append(el('div', { class: 'status-line' }, el('i', { class: 'spin' }), S.run.label || 'Başlıyor…'));
  if (S.run.live) {
    const prose = el('div', { class: 'prose live' });
    prose.innerHTML = mdToHtml(S.run.live);
    enhance(prose, false);
    b.append(prose);
  }
  if (near) sheet.scrollTop = sheet.scrollHeight;
}

// ------------------------------------------------------------------ olaylar (SSE)
function addStep(text) {
  const run = S.run, m = text.match(/Adım (\d+)\/(\d+): `([^`]+)`/);
  closeStep();
  if (m) run.steps.push({ n: +m[1], tool: m[3], state: 'run', t0: Date.now() });
  else run.steps.push({ note: text.replace(/[`*]|⚠️|⚙️/g, '').trim(), warn: /hata|onar/i.test(text) });
}
function closeStep() {
  const last = S.run && S.run.steps[S.run.steps.length - 1];
  if (last && last.tool && last.state === 'run') { last.state = 'ok'; last.ms = Date.now() - last.t0; }
}

function onEvent(ev) {
  if (!S.run && ev.type !== 'error') return;
  switch (ev.type) {
    case 'accepted': {
      if (ev.problems && ev.problems.length) toast(ev.problems.join(' '));
      const last = S.msgs[S.msgs.length - 1];
      if (last && last.role === 'user' && ev.saved && ev.saved.length) last.content += ev.saved.map((p) => `\n\nEk: \`${p}\``).join('');
      break;
    }
    case 'start': S.run.label = 'Çalışıyor · ' + ev.model; break;
    case 'step': addStep(ev.text); break;
    case 'plan': S.plan = ev.steps || []; if (S.tab === 'out') renderDock(); break;
    case 'status': if (ev.label) S.run.label = ev.label; break;
    case 'token': S.run.live = ev.text; break;
    case 'final': finishRun(ev); return;
    case 'error': toast(ev.message || 'Beklenmeyen bir hata oluştu.'); S.run && (S.run.error = ev.message); break;
  }
  schedulePaint();
}

function finishRun(ev) {
  closeStep();
  const steps = S.run.steps;
  S.run = null; S.busy = false;
  const m = ev.message;
  if (m && (m.content || (m.images && m.images.length))) S.msgs.push({ steps, ...m });
  S.pending = ev.pending || null;
  renderAll();
  // uzun cevap: okuma cevabin basindan baslasin; kisa cevap: altta kalsin
  const bots = $$('#sheet-inner .turn.bot'), last = bots[bots.length - 1], sheet = $('#sheet');
  if (last && last.offsetHeight > sheet.clientHeight * 0.8) sheet.scrollTop = last.offsetTop - 20;
  refreshData();
}

function endStreamFallback() {
  if (!S.run) return;
  closeStep();
  if (S.run.live) S.msgs.push({ role: 'assistant', content: S.run.live, images: [], steps: S.run.steps });
  S.run = null; S.busy = false;
  renderAll();
}

// ------------------------------------------------------------------ gonderim
function startRun() { S.busy = true; S.run = { steps: [], live: '', label: 'Başlıyor…' }; }

async function sendText(text) {
  const files = S.attach.slice();
  text = (text || '').trim();
  if ((!text && !files.length) || S.busy || S.pending) return;
  if (S.needsKeys) { toast('Önce yapay zekâ anahtarını eklemen gerekiyor; adımlar ekranda.'); return showSetup(); }   // anahtarsiz gonderim teknik hata yerine kurulum ekranini acar
  S.msgs.push({ role: 'user', content: text || 'Yüklenen dosyaları analiz et.', files: files.map((f) => f.name) });
  S.attach = []; $('#prompt').value = ''; autosize();
  startRun(); renderAll();
  const fd = new FormData();
  fd.append('sid', S.sid); fd.append('text', text); fd.append('model', S.model);
  fd.append('auto_exec', S.autoExec ? '1' : '0'); fd.append('verify', S.verify ? '1' : '0');
  files.forEach((f) => fd.append('files', f, f.name));
  try { await stream('/chat', fd, false); } catch (e) { toast(e.message); }
  endStreamFallback();
}

async function stopRun() {
  if (!S.run || S.run.stopping) return;
  S.run.stopping = true; S.run.label = 'Durduruluyor…'; schedulePaint();
  try { await post('/stop', { sid: S.sid }); } catch (e) { S.run.stopping = false; toast(e.message); }
}

async function decide(approve) {
  if (!S.pending || S.busy) return;
  S.pending = null; startRun(); renderAll();
  try { await stream('/decision', { sid: S.sid, approve, model: S.model, auto_exec: S.autoExec, verify: S.verify }, true); } catch (e) { toast(e.message); }
  endStreamFallback();
}

// ------------------------------------------------------------------ onay kapisi
function renderGate() {
  const slot = $('#gate-slot'), p = S.pending;
  if (!p) { slot.replaceChildren(); return; }
  if ($('.gate', slot)) return;
  const code = el('code', { class: p.lang ? 'language-' + p.lang : '' }, p.detail || JSON.stringify(p.params, null, 2));
  if (window.hljs && p.lang && hljs.getLanguage(p.lang)) { try { hljs.highlightElement(code); } catch { /* düz metin */ } }
  const gate = el('section', { class: 'gate', role: 'alertdialog', 'aria-labelledby': 'gate-h', 'aria-describedby': 'gate-why', tabindex: '-1' },
    el('div', { class: 'gate-body' },
      el('h3', { id: 'gate-h' }, 'Onay gerekiyor', el('span', { class: 'tool', text: p.action || 'eylem' })),
      el('p', { class: 'why', id: 'gate-why', text: p.reason }),
      el('pre', {}, code)),
    el('div', { class: 'gate-actions' },
      el('button', { class: 'btn btn-ink', type: 'button', text: 'İnceledim, çalıştır', onclick: () => decide(true) }),
      el('button', { class: 'btn', type: 'button', text: 'Reddet', onclick: () => decide(false) }),
      el('span', { class: 'hint', text: 'Kod yalnızca sen onaylayınca çalışır.' })));
  slot.replaceChildren(gate);
  gate.focus({ preventScroll: true });
}

// ------------------------------------------------------------------ giris alani
function autosize() { const t = $('#prompt'); t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 220) + 'px'; }

function renderComposer() {
  const locked = S.busy || !!S.pending;
  const c = $('#composer');
  c.dataset.locked = String(locked);
  $('#prompt').placeholder = S.pending ? 'Önce bekleyen işlemi onayla veya reddet…' : S.busy ? 'Görev çalışıyor…' : 'Görevi yaz…';
  const send = $('#send'), running = S.busy && !S.pending;
  send.disabled = running ? false : locked || !($('#prompt').value.trim() || S.attach.length);
  send.dataset.run = String(running);
  send.setAttribute('aria-label', running ? 'Görevi durdur' : 'Gönder');
  send.title = running ? 'Görevi durdur' : 'Gönder';
  $('#opt-verify').setAttribute('aria-pressed', String(S.verify));
  $('#opt-auto').setAttribute('aria-pressed', String(S.autoExec));
  $('#mic').hidden = !S.audio;
  const chips = $('#chips');
  chips.replaceChildren(...S.attach.map((f, i) => el('span', { class: 'chip' },
    f.type.startsWith('image/') ? el('img', { src: URL.createObjectURL(f), alt: '' }) : null, f.name,
    el('button', { type: 'button', 'aria-label': f.name + ' dosyasını kaldır', text: '×', onclick: () => { S.attach.splice(i, 1); renderComposer(); } }))));
}

function addFiles(list) {
  for (const f of list) if (!S.attach.some((x) => x.name === f.name && x.size === f.size)) S.attach.push(f);
  renderComposer();
}

// ------------------------------------------------------------------ yan pano
function renderDock() {
  $$('.tabs [role=tab]').forEach((t) => {
    const on = t.dataset.tab === S.tab;
    t.setAttribute('aria-selected', String(on));
    $('#pane-' + t.dataset.tab).hidden = !on;
  });
  if (S.tab === 'out') renderOut();
  else if (S.tab === 'files') renderFiles();
  else renderRules();
}

function renderOut() {
  const pane = $('#pane-out'), figNo = figureNumbers();
  pane.replaceChildren();
  if (S.plan.length) {
    pane.append(el('h3', { class: 'sec', text: 'Plan' }),
      el('ul', { class: 'plan' }, S.plan.map((p) => el('li', { class: p.status }, el('span', { text: p.text })))));
  }
  const all = [...figNo.keys()];
  pane.append(el('h3', { class: 'sec', text: 'Şekiller' }));
  if (!all.length) { pane.append(el('p', { class: 'pane-note', text: 'Hesaplar grafik ürettiğinde burada toplanır.' })); return; }
  pane.append(el('div', { class: 'out-list' }, all.map((p) => el('button', { class: 'thumb', type: 'button', onclick: () => openLightbox(fileUrl(p)) },
    el('img', { src: fileUrl(p), alt: '', loading: 'lazy' }), el('span', { text: `Şekil ${figNo.get(p)} · ${p.split('/').pop()}` })))));
}

async function renderFiles() {
  const pane = $('#pane-files');
  pane.replaceChildren();
  if (S.preview) return renderPreview(pane);
  if (!S.files.length) { pane.append(el('h3', { class: 'sec', text: 'Çalışma alanı' }), el('p', { class: 'pane-note', text: 'Çalışma alanında henüz dosya yok. Yüklediğin ve Nodus’un ürettiği dosyalar burada görünür.' })); return; }
  const groups = new Map();
  for (const f of S.files) { const d = f.includes('/') ? f.slice(0, f.lastIndexOf('/')) : '.'; (groups.get(d) || groups.set(d, []).get(d)).push(f); }
  pane.append(el('h3', { class: 'sec', text: 'Çalışma alanı' }));
  for (const [dir, files] of groups) {
    if (dir !== '.') pane.append(el('div', { class: 'file-grp', text: dir + '/' }));
    for (const f of files) pane.append(el('button', { class: 'file-row', type: 'button', title: f, onclick: () => { S.preview = f; renderFiles(); } }, el('span', { text: f.split('/').pop() })));
  }
}

async function renderPreview(pane) {
  const p = S.preview, ext = (p.split('.').pop() || '').toLowerCase();
  pane.append(el('div', { class: 'pv-head' },
    el('button', { class: 'btn btn-sm', type: 'button', text: 'Geri', onclick: () => { S.preview = null; renderFiles(); } }),
    el('b', { text: p.split('/').pop(), title: p }),
    el('a', { class: 'btn btn-sm', href: fileUrl(p, true), download: p.split('/').pop(), text: 'İndir' })));
  const body = el('div', { class: 'pv-body' });
  pane.append(body);
  if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)) {
    const img = el('img', { src: fileUrl(p), alt: p }); img.addEventListener('click', () => openLightbox(fileUrl(p))); body.append(img);
  } else {
    try {
      const d = await api('/file/text?path=' + encodeURIComponent(p));
      const code = el('code', { class: 'language-' + ext }, d.text);
      body.append(el('pre', {}, code));
      if (window.hljs && hljs.getLanguage(ext)) hljs.highlightElement(code);
    } catch (e) { body.append(el('p', { class: 'pane-note', style: 'padding:14px', text: 'Bu dosya önizlenemiyor. İndirerek açabilirsin.' })); }
  }
}

function renderRules() {
  const pane = $('#pane-rules');
  pane.replaceChildren(el('h3', { class: 'sec', text: 'Kalıcı kurallar' }));
  if (!S.facts.length) pane.append(el('p', { class: 'pane-note', text: 'Nodus’un her görevde uyacağı kuralları buraya ekle. Örn: SI birim sistemi kullan.' }));
  S.facts.forEach((f, i) => pane.append(el('div', { class: 'rule-item' }, el('span', { text: f }),
    el('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Kuralı sil', onclick: async () => { try { S.facts = (await api('/facts/' + i, { method: 'DELETE' })).facts; renderRules(); } catch (e) { toast(e.message); } } }, delIcon()))));
  const input = el('input', { type: 'text', placeholder: 'Yeni kural', 'aria-label': 'Yeni kural', maxlength: '300' });
  const add = async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    try { S.facts = (await post('/facts', { text })).facts; renderRules(); } catch (err) { toast(err.message); }
  };
  pane.append(el('form', { class: 'rule-add', onsubmit: add }, input, el('button', { class: 'btn btn-ink', type: 'submit', text: 'Kaydet' })));
}

// ------------------------------------------------------------------ menuler / diyaloglar
function openLightbox(src) { $('#lightbox-img').src = src; $('#lightbox').showModal(); }

function toggleModelMenu(force) {
  const menu = $('#model-menu'), btn = $('#model-btn');
  const open = force === undefined ? menu.hidden : force;
  if (!open) { menu.hidden = true; btn.setAttribute('aria-expanded', 'false'); return; }
  menu.replaceChildren(...S.models.map((m) => el('button', { class: 'opt', type: 'button', role: 'option', 'aria-selected': String(m === S.model),
    onclick: () => { S.model = m; LS.set('model', m); toggleModelMenu(false); renderTitle(); } },
    el('b', { text: modelLabel(m) }), el('small', { text: modelProv(m) }))));
  const r = btn.getBoundingClientRect();
  menu.hidden = false;
  menu.style.top = r.bottom + 6 + 'px';
  menu.style.left = Math.max(8, Math.min(r.left, innerWidth - menu.offsetWidth - 8)) + 'px';
  btn.setAttribute('aria-expanded', 'true');
}

function renderSettingsIfOpen() { if ($('#settings').open) renderSettings(); }
function renderSettings() {
  const body = $('#settings-body'), pref = LS.get('theme', 'system');
  const seg = (items, current, on) => el('div', { class: 'seg' }, items.map(([v, t]) => el('button', { type: 'button', 'aria-pressed': String(v === current), text: t, onclick: () => on(v) })));
  const toggle = (id, label, on, set) => el('button', { class: 'tgl' + (id === 'auto' ? ' danger' : ''), type: 'button', 'aria-pressed': String(on), onclick: () => { set(!on); renderSettings(); renderComposer(); } }, el('i'), label);
  body.replaceChildren(
    el('section', { class: 'set-sec' }, el('h3', { text: 'Tema' }), el('p', { text: 'Sistem ayarını izler ya da elle seçilir.' }),
      seg([['system', 'Sistem'], ['light', 'Açık'], ['dark', 'Koyu']], pref, applyTheme)),
    el('section', { class: 'set-sec' }, el('h3', { text: 'Çalıştırma' }),
      el('p', { text: 'Kapalıyken her kod çalıştırma senden onay ister. İnternetten ya da belgeden içerik okunduktan sonra bu ayar ne olursa olsun onay istenir.' }),
      el('div', { class: 'row-btns' },
        toggle('verify', 'Ağır görevlerde çapraz doğrula', S.verify, (v) => { S.verify = v; LS.set('verify', v ? '1' : '0'); }),
        toggle('auto', 'Kodu onaysız çalıştır', S.autoExec, (v) => { S.autoExec = v; LS.set('auto', v ? '1' : '0'); }))),
    el('section', { class: 'set-sec' }, el('h3', { text: 'Bugünkü kullanım' }),
      S.usage.length ? el('table', { class: 'use-table' },
        el('thead', {}, el('tr', {}, ['Sağlayıcı', 'İstek', 'Token', '429', 'Kalan istek'].map((h) => el('th', { text: h })))),
        el('tbody', {}, S.usage.map((u) => el('tr', {}, [u.saglayici, u.istek, u.token, u['429'], u.kalan_istek].map((c) => el('td', { text: String(c) })))))) : el('p', { text: 'Anahtarı tanımlı sağlayıcı yok.' }),
      el('p', { style: 'margin-top:8px', text: 'Kalan kota, sağlayıcının yanıt başlıklarından okunur; ilk istekten sonra dolar.' })),
    el('section', { class: 'set-sec' }, el('h3', { text: 'Anahtarlar' }),
      el('p', { text: 'Yapay zeka sağlayıcı anahtarların bu bilgisayarda .env dosyasında durur. ' + KEY_PROVIDERS.map(([k, n]) => `${n}: ${S.keys[k] ? '✓ kayıtlı' : '— yok'}`).join(' · ') }),
      el('div', { class: 'row-btns' }, el('button', { class: 'btn', type: 'button', text: 'Anahtar ekle / değiştir', onclick: () => { $('#settings').close(); showSetup(); } }))),
    el('section', { class: 'set-sec' }, el('h3', { text: 'Sürüm' }),
      el('p', { text: `Nodus ${S.version || '—'}. Güncelleme denetimi GitHub'a bağlanır; NODUS_NO_UPDATE_CHECK=1 ile kapatılır.` }),
      el('div', { class: 'row-btns' }, el('button', { class: 'btn', type: 'button', text: 'Güncellemeleri denetle', onclick: manualUpdateCheck }))),
    el('section', { class: 'set-sec' }, el('h3', { text: 'Veriler' }), el('p', { text: 'Bu işlemler geri alınamaz.' }),
      el('div', { class: 'row-btns' },
        el('button', { class: 'btn btn-danger', type: 'button', text: 'Bu görevi sil', onclick: () => { $('#settings').close(); removeSession(S.sid, true); } }),
        el('button', { class: 'btn btn-danger', type: 'button', text: 'Tümünü sıfırla', onclick: resetAll }))));
}

async function resetAll() {
  if (!confirm('Tüm görevler, kalıcı kurallar ve notlar silinecek. Devam edilsin mi?')) return;
  try { await post('/reset'); $('#settings').close(); await newTask(true); toast('Tüm veriler sıfırlandı.'); } catch (e) { toast(e.message); }
}

// ------------------------------------------------------------------ oturumlar
async function refreshData() {
  try {
    const b = await api('/bootstrap');
    Object.assign(S, { sessions: b.sessions, sandbox: b.sandbox, providers: b.providers, usage: b.usage, models: b.models, facts: b.facts, files: b.files, audio: b.audio, version: b.version || S.version, keys: b.keys || {}, needsKeys: !!b.needs_keys });
    const resting = new Set(b.providers.filter((p) => p.dinlenen).map((p) => p.saglayici));
    if (S.rested) for (const n of resting) if (!S.rested.has(n)) toast(n + ' kotası doldu ya da sağlayıcı yanıt vermiyor; istekler otomatik olarak diğer sağlayıcılara yönlendiriliyor.');
    S.rested = resting;
    if (!S.models.includes(S.model)) S.model = 'auto';
    if (!S.run) S.plan = b.plan.length ? b.plan : S.plan;
    renderRail(); renderTitle(); renderDock(); renderComposer();
  } catch (e) { toast('Sunucuya ulaşılamadı: ' + e.message); }
}

async function newTask(force) {
  if (S.busy && !force) return toast('Görev çalışırken yeni görev açılamaz.');
  try {
    S.sid = (await post('/session')).id;
    Object.assign(S, { msgs: [], pending: null, plan: [], preview: null, run: null, busy: false });
    setRail(false); renderAll(); refreshData();
    $('#prompt').focus();
  } catch (e) { toast(e.message); }
}

async function openSession(id) {
  if (S.busy) return toast('Görev çalışırken görev değiştirilemez.');
  if (id === S.sid) return setRail(false);
  try {
    const d = await api('/session/' + id);
    Object.assign(S, { sid: id, msgs: d.messages, pending: d.pending, plan: [], preview: null });
    setRail(false); renderAll(); refreshData();
  } catch (e) { toast(e.message); }
}

async function removeSession(id, skipConfirm) {
  if (S.busy) return toast('Görev çalışırken silinemez.');
  if (!skipConfirm && !confirm('Bu görev silinsin mi?')) return;
  try {
    await api('/session/' + id, { method: 'DELETE' });
    if (id === S.sid) await newTask(); else refreshData();
  } catch (e) { toast(e.message); }
}

// ------------------------------------------------------------------ ilk kurulum: anahtar ekleme
const KEY_PROVIDERS = [['gemini', 'Gemini'], ['groq', 'Groq'], ['openrouter', 'OpenRouter'], ['cerebras', 'Cerebras'], ['mistral', 'Mistral']];
const setup = { busy: false, error: '', text: '', vals: {} };
// Sağlayıcıların anahtar önekleri: kullanıcı hangi sağlayıcının anahtarı olduğunu bilmeden yapıştırabilsin
const KEY_HINTS = [[/^AIza[\w-]{30,}$/, 'gemini'], [/^gsk_\w{20,}$/, 'groq'], [/^sk-or-[\w-]{20,}$/, 'openrouter'], [/^csk-\w{20,}$/, 'cerebras'], [/^[A-Za-z0-9]{32}$/, 'mistral']];
const detectProvider = (k) => { const hit = KEY_HINTS.find(([re]) => re.test(k)); return hit ? hit[1] : null; };
const providerName = (k) => (KEY_PROVIDERS.find(([id]) => id === k) || [, k])[1];
// Gemini dışındaki sağlayıcılar: her biri için "anahtar sayfasını aç" bağlantısı ve tek cümlelik yönerge
const PROVIDER_INFO = {
  groq: { url: 'https://console.groq.com/keys', hint: 'Çok hızlı cevap verir; sesli komut kullanmak istiyorsan bu gerekli. Giriş yap, “Create API Key” de.' },
  openrouter: { url: 'https://openrouter.ai/keys', hint: 'Bir sürü ücretsiz modelden oluşan yedek havuz. Giriş yap, “Create Key” de.' },
  cerebras: { url: 'https://cloud.cerebras.ai', hint: 'Çok hızlı cevap verir. Giriş yaptıktan sonra “API Keys” bölümünden yeni anahtar oluştur.' },
  mistral: { url: 'https://console.mistral.ai/api-keys', hint: 'Ek yedek havuz. Giriş yap, “Create new key” de.' },
};

function paintSetup() {
  const body = $('#setup-body');
  const inputs = {};
  const card = (k) => {
    const info = PROVIDER_INFO[k], name = providerName(k);
    inputs[k] = el('input', { type: 'password', autocomplete: 'off', spellcheck: 'false', 'aria-label': name + ' anahtarı',
      placeholder: S.keys[k] ? 'kayıtlı; değiştirmek için yenisini yapıştır' : 'anahtarı buraya yapıştır', disabled: setup.busy,
      value: setup.vals[k] || '', oninput: (e) => { setup.vals[k] = e.target.value; } });   // hata sonrasi yeniden cizimde yazilan silinmesin
    return el('div', { class: 'key-card' },
      el('div', { class: 'key-card-head' }, el('b', { text: name }), S.keys[k] ? el('span', { class: 'key-ok', text: '✓ kayıtlı' }) : null),
      el('p', { class: 'key-card-hint', text: info.hint }),
      el('div', { class: 'key-main' },
        el('a', { class: 'btn btn-sm', href: info.url, target: '_blank', rel: 'noopener noreferrer', text: 'Anahtar sayfasını aç ↗' }), inputs[k]));
  };
  const submit = async (e) => {
    e.preventDefault();
    const payload = {};
    for (const [k] of KEY_PROVIDERS) if (inputs[k] && inputs[k].value.trim()) payload[k] = inputs[k].value.trim();
    const pasted = inputs.main.value.trim();
    if (pasted) {
      const prov = detectProvider(pasted);
      if (!prov) { setup.error = 'Bu anahtarı tanıyamadım. Gemini anahtarları “AIza” ile başlar; kopyalarken baştan ya da sondan karakter kaçmış olabilir. Başka bir sağlayıcınınsa anahtarı aşağıdaki kartlardan ona ait olana yapıştır.'; return paintSetup(); }
      payload[prov] = pasted;
    }
    if (!Object.keys(payload).length) { setup.error = 'Önce anahtarı yapıştır.'; return paintSetup(); }
    setup.busy = true; setup.error = ''; setup.text = 'Anahtar doğrulanıyor…'; paintSetup();
    let boot0;
    try {
      boot0 = (await api('/ping')).boot;
      const r = await post('/setup/keys', payload);
      if (r.unverified && r.unverified.length) toast(r.unverified.join(', ') + ' anahtarı doğrulanamadı (internet?); yine de kaydedildi.');
    } catch (err) { setup.busy = false; setup.error = err.message; return paintSetup(); }
    setup.text = 'Kaydedildi. Nodus yeniden başlıyor…'; paintSetup();
    const t0 = Date.now();
    for (;;) {
      await sleep(1000);
      try { const p = await api('/ping'); if (p.boot && p.boot !== boot0) return location.reload(); } catch { /* yeniden basliyor */ }
      if (Date.now() - t0 > 90000) { setup.busy = false; setup.error = "Yeniden başlatma uzun sürdü. Nodus'u kapatıp yeniden aç."; return paintSetup(); }
    }
  };
  const found = el('small', { class: 'key-detect', 'aria-live': 'polite' });
  const detect = (v) => {
    v = v.trim();
    const prov = detectProvider(v);
    found.className = 'key-detect' + (prov ? ' ok' : '');
    found.textContent = !v ? '' : prov ? `✓ ${providerName(prov)} anahtarı gibi görünüyor` : 'Bu henüz tam bir anahtara benzemiyor; baştan sona kopyaladığından emin ol.';
  };
  inputs.main = el('input', { type: 'text', autocomplete: 'off', spellcheck: 'false', 'aria-label': 'Anahtar', disabled: setup.busy,
    placeholder: S.keys.gemini ? 'kayıtlı; değiştirmek için yeni anahtarı yapıştır' : 'AIza… ile başlayan anahtarı buraya yapıştır', value: setup.vals.main || '',
    oninput: (e) => { setup.vals.main = e.target.value; detect(e.target.value); } });
  detect(inputs.main.value);
  const pasteBtn = el('button', { class: 'btn', type: 'button', disabled: setup.busy, text: 'Panodan yapıştır', onclick: async () => {
    try {
      const t = (await navigator.clipboard.readText()).trim();
      inputs.main.value = t; setup.vals.main = t; detect(t);
    } catch { setup.error = 'Panoya erişemedim; anahtarı kutuya Ctrl+V ile yapıştır.'; paintSetup(); }
  } });
  const first = S.needsKeys;   // hiç anahtar yoksa: ilk kurulum, sade bir karşılama metni göster
  $('#setup-h').textContent = first ? 'Nodus’a hoş geldin' : 'Anahtar ekle / değiştir';
  body.replaceChildren(
    first
      ? el('div', { class: 'key-welcome' },
          el('p', {}, el('b', { text: 'Başlamadan önce tek bir şey gerekiyor.' }), ' Nodus’un düşünebilmesi için internetteki bir yapay zekâ servisini kullanması lazım. O servis de bir “anahtar” ister.'),
          el('p', { text: 'Anahtar, uzun harf ve rakamlardan oluşan bir şifre gibidir; servise kayıt olunca sana verilir. Ücretsizdir, kredi kartı istemez ve yalnızca bu bilgisayarda saklanır. İstediğin zaman Ayarlar → Anahtar ekle / değiştir’den yenisini girebilirsin.' }),
          el('p', {}, el('b', { text: 'Aşağıdaki 3 adımı izle; yaklaşık 1 dakika sürer.' })))
      : el('p', { class: 'key-intro' }, 'Nodus yapay zekayı Google’ın ', el('b', { text: 'ücretsiz' }), ' Gemini hizmetiyle çalıştırır. Bunun için kendi hesabından bir “anahtar” (uzun bir şifre) almak gerekir. ',
          el('b', { text: 'Kredi kartı istemez, yaklaşık 1 dakika sürer.' }), ' Anahtar yalnızca bu bilgisayarda saklanır.'),
    el('form', { class: 'key-form', onsubmit: submit },
      el('ol', { class: 'key-steps' },
        el('li', {}, 'Google hesabınla giriş yap (Gmail adresin yeterli). ', el('a', { class: 'btn btn-sm', href: 'https://aistudio.google.com/apikey', target: '_blank', rel: 'noopener noreferrer', text: 'Anahtar sayfasını aç ↗' })),
        el('li', { text: '“Create API key” (Anahtar oluştur) düğmesine bas; çıkan uzun metni kopyala (yanındaki kopyala simgesi işini görür).' }),
        el('li', {}, 'Buraya yapıştır:', el('div', { class: 'key-main' }, inputs.main, pasteBtn), found)),
      el('section', { class: 'key-more' },
        el('h3', { text: 'Daha fazla ücretsiz kota (isteğe bağlı)' }),
        el('p', { text: 'Gemini tek başına yeterli. Ama her ücretsiz servisin günlük bir sınırı var: ne kadar çok servis eklersen sınır o kadar geniş olur ve biri dolunca Nodus kendiliğinden diğerine geçer. Hepsinde yöntem aynı: “Anahtar sayfasını aç”, giriş yap ya da kayıt ol, yeni anahtar oluştur, kopyala, buraya yapıştır.' }),
        el('div', { class: 'key-cards' }, ['groq', 'openrouter', 'cerebras', 'mistral'].map(card))),
      ...(setup.error ? [el('p', { class: 'upd-err', role: 'alert', text: setup.error })] : []),
      ...(setup.busy ? [el('div', { class: 'status-line' }, el('i', { class: 'spin' }), setup.text)] : []),
      el('div', { class: 'row-btns' },
        el('button', { class: 'btn btn-ink', type: 'submit', disabled: setup.busy, text: 'Kaydet ve başlat' }),
        el('button', { class: 'btn', type: 'button', disabled: setup.busy, text: first ? 'Şimdi değil' : 'Vazgeç', onclick: () => $('#setup').close() }))));
}

function showSetup() { setup.busy = false; setup.error = ''; paintSetup(); if (!$('#setup').open) $('#setup').showModal(); }

// ------------------------------------------------------------------ guncelleme
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const upd = { busy: false, text: '', error: '' };

async function checkUpdate(force) {
  try { return await api('/update/check' + (force ? '?force=1' : '')); } catch { return null; }
}

function paintUpdate() {
  const info = S.update, l = info.latest, body = $('#update-body');
  const notes = el('div', { class: 'prose upd-notes' });
  notes.innerHTML = mdToHtml(l.notes || 'Bu sürüm için güncelleme notu yok.');
  enhance(notes, true);
  body.replaceChildren(
    el('p', { class: 'upd-line' }, el('b', { text: 'Nodus ' + l.version }), ` yayınlandı. Şu an ${info.current} sürümünü kullanıyorsun.`),
    el('h3', { class: 'upd-h', text: 'Güncelleme notları' }), notes,
    ...(upd.error ? [el('p', { class: 'upd-err', role: 'alert', text: upd.error })] : []),   // replaceChildren(null) "null" yazar
    upd.busy
      ? el('div', { class: 'status-line' }, el('i', { class: 'spin' }), upd.text)
      : el('p', { class: 'upd-ask', text: 'Şimdi güncellemek ister misin? Anahtarların, görevlerin ve notların korunur; Nodus kısa süre yeniden başlar.' }),
    el('div', { class: 'row-btns' },
      el('button', { class: 'btn btn-ink', type: 'button', disabled: upd.busy, text: upd.error ? 'Yeniden dene' : 'Şimdi güncelle', onclick: runUpdate }),
      el('button', { class: 'btn', type: 'button', disabled: upd.busy, text: 'Sonra', onclick: () => $('#update').close() })));
}

function showUpdate(info) {
  S.update = info; upd.error = ''; upd.busy = false;
  paintUpdate();
  if (!$('#update').open) $('#update').showModal();
}

async function runUpdate() {
  const info = S.update;
  upd.busy = true; upd.error = ''; upd.text = 'Güncelleme başlatılıyor…'; paintUpdate();
  try { await post('/update'); } catch (e) { upd.busy = false; upd.error = e.message; return paintUpdate(); }
  for (;;) {
    await sleep(700);
    let s;
    try { s = await api('/update/status'); } catch { break; }   // sunucu yeniden basladi
    if (s.state === 'error') { upd.busy = false; upd.error = s.message || 'Güncelleme başarısız oldu.'; return paintUpdate(); }
    upd.text = s.step || upd.text; paintUpdate();
    if (s.state === 'done') { if (s.message) toast(s.message); upd.text = 'Yeniden başlatılıyor…'; paintUpdate(); break; }
  }
  const t0 = Date.now();
  for (;;) {   // yeni surum yanit verene kadar bekle, sonra sayfayi yenile
    await sleep(1000);
    try { const p = await api('/ping'); if (p.version && p.version !== info.current) return location.reload(); } catch { /* yeniden basliyor */ }
    if (Date.now() - t0 > 120000) { upd.busy = false; upd.error = "Yeniden başlatma beklenenden uzun sürdü. Nodus'u kapatıp yeniden aç."; return paintUpdate(); }
  }
}

async function manualUpdateCheck() {
  const d = await checkUpdate(true);
  if (!d || d.error) return toast("GitHub'a ulaşılamadı; internet bağlantını kontrol et.");
  if (d.disabled) return toast('Güncelleme denetimi kapalı (NODUS_NO_UPDATE_CHECK).');
  if (d.available) { $('#settings').close(); return showUpdate(d); }
  toast(`Nodus güncel (${d.current}).`);
}

async function checkUpdateOnOpen() {
  await sleep(1200);
  const d = await checkUpdate(false);
  if (d && d.available && !S.busy) showUpdate(d);
}

// ------------------------------------------------------------------ ses kaydi
let rec = null;
async function toggleMic() {
  const btn = $('#mic');
  if (rec) { rec.stop(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const chunks = [];
    rec = new MediaRecorder(stream);
    rec.ondataavailable = (e) => chunks.push(e.data);
    rec.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      btn.dataset.rec = 'false'; rec = null;
      const blob = new Blob(chunks, { type: chunks[0] ? chunks[0].type : 'audio/webm' });
      toast('Ses metne çevriliyor…');
      try {
        const r = await fetch('/api/transcribe', { method: 'POST', headers: { 'X-Nodus': '1', 'Content-Type': blob.type }, body: blob });
        const d = await r.json();
        if (d.ok) { const t = $('#prompt'); t.value = (t.value + ' ' + d.text).trim(); autosize(); renderComposer(); t.focus(); } else toast(d.text);
      } catch (e) { toast('Ses servisine ulaşılamadı.'); }
    };
    rec.start(); btn.dataset.rec = 'true';
  } catch { toast('Mikrofon izni verilmedi.'); }
}

// ------------------------------------------------------------------ baslatma
function renderAll() { renderRail(); renderTitle(); renderSheet(); renderGate(); renderComposer(); renderDock(); }

function bind() {
  const prompt = $('#prompt');
  prompt.addEventListener('input', () => { autosize(); renderComposer(); });
  prompt.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('#composer').requestSubmit(); }
  });
  $('#composer').addEventListener('submit', (e) => {
    e.preventDefault();
    if (S.busy) return stopRun();
    if (!$('#send').disabled) sendText(prompt.value);
  });
  $('#attach').addEventListener('click', () => $('#file-input').click());
  $('#file-input').addEventListener('change', (e) => { addFiles(e.target.files); e.target.value = ''; });
  $('#mic').addEventListener('click', toggleMic);
  $('#opt-verify').addEventListener('click', () => { S.verify = !S.verify; LS.set('verify', S.verify ? '1' : '0'); renderComposer(); });
  $('#opt-auto').addEventListener('click', () => {
    S.autoExec = !S.autoExec; LS.set('auto', S.autoExec ? '1' : '0'); renderComposer();
    if (S.autoExec) toast('Python kodu ve kabuk komutları onay istenmeden çalışacak (bu seçim hatırlanır). Dosya silme yine onay ister.');
  });
  prompt.addEventListener('paste', (e) => { const fs = [...(e.clipboardData ? e.clipboardData.files : [])]; if (fs.length) { e.preventDefault(); addFiles(fs); } });

  const stage = $('#stage');
  let depth = 0;
  stage.addEventListener('dragenter', (e) => { if (e.dataTransfer && [...e.dataTransfer.types].includes('Files')) { depth++; stage.dataset.drag = 'true'; } });
  stage.addEventListener('dragover', (e) => e.preventDefault());
  stage.addEventListener('dragleave', () => { if (--depth <= 0) { depth = 0; stage.dataset.drag = 'false'; } });
  stage.addEventListener('drop', (e) => { e.preventDefault(); depth = 0; stage.dataset.drag = 'false'; addFiles(e.dataTransfer.files); });

  $('#new-task').addEventListener('click', () => newTask());
  let searchTimer = 0;
  $('#session-search').addEventListener('input', (e) => {
    S.search = e.target.value; S.hits = null; renderRail();
    clearTimeout(searchTimer);
    const q = S.search.trim();
    if (q.length < 2) return;
    searchTimer = setTimeout(async () => {
      try { const d = await api('/search?q=' + encodeURIComponent(q)); if (S.search.trim() === q) { S.hits = new Set(d.ids); renderRail(); } } catch { /* baslik aramasi yeter */ }
    }, 250);
  });
  $('#open-settings').addEventListener('click', () => { renderSettings(); $('#settings').showModal(); });
  $('#model-btn').addEventListener('click', () => toggleModelMenu());
  $('#rail-toggle').addEventListener('click', () => setRail(true));
  $('#dock-toggle').addEventListener('click', () => setDock(!dockOpen()));
  $('#scrim').addEventListener('click', () => { setRail(false); if (innerWidth <= 1180) setDock(false); });
  $$('.tabs [role=tab]').forEach((t) => t.addEventListener('click', () => { S.tab = t.dataset.tab; LS.set('tab', S.tab); renderDock(); }));
  $('#setup').addEventListener('cancel', (e) => { if (setup.busy) e.preventDefault(); });
  $('#update').addEventListener('cancel', (e) => { if (upd.busy) e.preventDefault(); });
  $('#lightbox').addEventListener('click', (e) => { if (e.target.id === 'lightbox') e.currentTarget.close(); });
  $('#settings').addEventListener('click', (e) => { if (e.target.id === 'settings') e.currentTarget.close(); });

  document.addEventListener('click', (e) => { if (!e.target.closest('#model-menu, #model-btn')) toggleModelMenu(false); });
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); newTask(); }
    if (e.key === 'Escape') { toggleModelMenu(false); setRail(false); if (innerWidth <= 1180) setDock(false); }
  });
}

// Tek sekme: Nodus simgesine her tiklama yeni sekme acar; ikinci sekme baska sekmenin acik oldugunu fark edip sorar.
let tabChannel = null, tabIsDup = false;
function otherTabOpen() {
  if (!('BroadcastChannel' in window)) return Promise.resolve(false);
  tabChannel = new BroadcastChannel('nodus-tab');
  tabChannel.addEventListener('message', (e) => { if (e.data === 'hello' && !tabIsDup) tabChannel.postMessage('taken'); });
  return new Promise((resolve) => {
    const t = setTimeout(() => resolve(false), 400);
    tabChannel.addEventListener('message', (e) => { if (e.data === 'taken') { clearTimeout(t); resolve(true); } });
    tabChannel.postMessage('hello');
  });
}
function askDuplicateTab() {
  tabIsDup = true;
  return new Promise((resolve) => {
    const box = el('div', { class: 'dup-tab', role: 'alertdialog', 'aria-label': 'Nodus başka sekmede açık' },
      el('div', { class: 'dup-card' },
        el('h2', { text: 'Nodus zaten başka bir sekmede açık' }),
        el('p', { text: 'Aynı anda tek sekmede kullanmak en iyisi. Diğer sekmeye geçebilir ya da burayı kullanabilirsin.' }),
        el('div', { class: 'dup-actions' },
          el('button', { class: 'btn', text: 'Bu sekmeyi kapat', onclick: () => { window.close(); toast('Sekme kapanmadı; tarayıcıdan kapat (⌘W / Ctrl+W).'); } }),
          el('button', { class: 'btn btn-ink', text: 'Burada kullan', onclick: () => { tabIsDup = false; box.remove(); resolve(); } }))));
    document.body.append(box);
  });
}

async function boot() {
  if (await otherTabOpen()) await askDuplicateTab();
  const saved = LS.get('dock', null);
  setDock(saved === null ? innerWidth > 1180 : saved === '1' && innerWidth > 1180);
  bind();
  try {
    await newTask(true);
    await refreshData();
    if (S.needsKeys) showSetup(); else checkUpdateOnOpen();
  } catch (e) { toast('Sunucuya ulaşılamadı.'); }
}
boot();
})();
