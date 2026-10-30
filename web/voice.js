/* Nodus sesli mod. Konuşma tanıma ve seslendirme tarayıcıdan (Web Speech API); beyin ve araçlar /api/chat'te.
   Ortadaki küre canvas'a çizilir: dinlerken mikrofon seviyesine, konuşurken seslendirme vuruşlarına tepki verir. */
(() => {
'use strict';

// ------------------------------------------------------------------ yardimcilar
const $ = (s) => document.querySelector(s);
const el = (tag, props = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else n.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) n.append(c.nodeType ? c : document.createTextNode(c));
  return n;
};
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const synth = window.speechSynthesis;
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

const LABEL = { idle: 'HAZIR', listening: 'DİNLİYORUM', thinking: 'DÜŞÜNÜYORUM', speaking: 'KONUŞUYORUM', approval: 'ONAY BEKLİYORUM' };
const HUE = { idle: 192, listening: 208, thinking: 38, speaking: 162, approval: 8 };
const TOOL_LABEL = { eng_calc: 'Mühendislik hesabı', execute_code: 'Kod çalıştır', execute_python_code: 'Kod çalıştır', run_shell: 'Komut çalıştır', open_app: 'Uygulama aç',
  save_user_file: 'Dosya yaz', write_file: 'Dosya yaz', read_file: 'Dosya oku', list_files: 'Dosyaları listele', web_search: 'Web araması', fetch_url: 'Sayfa oku',
  browse_url: 'Tarayıcıda aç', read_document: 'Belge oku', export_report: 'Rapor üret', solve_math: 'Sembolik çözüm', delete_file: 'Dosya sil' };

const S = {
  sid: null, mode: null, state: 'idle', muted: false, busy: false, speaking: false, pending: null, heard: '',
  recog: null, level: 0, target: 0, hue: 192, pulse: 0, analyser: null, freq: null, micOk: false, voice: null, steps: [], srFailed: false,
  spokeAt: 0, lastSpoken: '', rate: 0.16, spin: 0, engine: '', ttsDown: false, ttsFails: 0, edgeVoices: ['tr-TR-EmelNeural', 'tr-TR-AhmetNeural'], ctx: null, outAnalyser: null, outFreq: null, audio: null, stopAudio: null, playing: false,
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
  const r = await fetch('/api' + path, { method: 'POST', body: isJson ? JSON.stringify(body) : body,
    headers: { 'X-Nodus': '1', ...(isJson ? { 'Content-Type': 'application/json' } : {}) } });
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

// ------------------------------------------------------------------ durum ve panel
function setState(st) {
  S.state = st;
  document.body.dataset.state = st;
  $('#state-label').textContent = LABEL[st];
}
function setCaption(who, text) { $(who === 'you' ? '#cap-you' : '#cap-bot').textContent = text || ''; }

function addLog(role, text, images) {
  const log = $('#log');
  log.append(el('div', { class: role, text: text.length > 320 ? text.slice(0, 320) + '…' : text },
    (images || []).slice(0, 2).map((p) => el('img', { src: '/api/file?path=' + encodeURIComponent(p), alt: p }))));
  while (log.children.length > 12) log.firstChild.remove();
  log.scrollTop = log.scrollHeight;
}

function paintSteps() {
  const ol = $('#steps');
  ol.replaceChildren(...(S.steps.length ? S.steps.slice(-9).map((s) => el('li', { class: s.tool ? (s.done ? '' : 'run') : 'note' },
    el('span', { text: s.tool ? (TOOL_LABEL[s.tool] || s.tool) : s.note }), s.tool && s.done ? el('span', { text: s.ms < 1000 ? '<1 sn' : Math.round(s.ms / 1000) + ' sn' }) : null))
    : [el('li', { class: 'empty', text: 'Henüz iş yok' })]));
}
function closeStep() { const l = S.steps[S.steps.length - 1]; if (l && l.tool && !l.done) { l.done = true; l.ms = Date.now() - l.t0; } }

function paintSys(boot) {
  syncVoiceUI();
  const rows = [['MOD', S.mode === 'auto' ? 'ONAYSIZ' : S.mode === 'ask' ? 'ONAYLI' : '—'], ['OTURUM', (S.sid || '—').slice(-4)],
    ['SÜRÜM', boot ? boot.version : '—'], ['KONUŞMA TANIMA', SR ? (S.srFailed ? 'ÇALIŞMIYOR' : 'HAZIR') : 'YOK'],
    ['SESLENDİRME', S.engine && !S.ttsDown ? (S.engine === 'eleven' ? 'ELEVENLABS' : 'MICROSOFT SİNİR AĞI') : synth ? 'TARAYICI' : 'YOK']];
  $('#sys').replaceChildren(...rows.flatMap(([k, v]) => [el('dt', { text: k }), el('dd', { text: v })]));
  $('#prov').replaceChildren(...((boot && boot.providers) || []).map((p) => el('li', { title: p.model_sayisi + ' model' }, el('i', { class: 'dot' + (p.dinlenen ? ' rest' : '') }), p.saglayici)));
}
function paintChips() {
  $('#chip-mode').textContent = 'MOD ' + (S.mode === 'auto' ? '· ONAYSIZ' : S.mode === 'ask' ? '· ONAYLI' : '—');
  $('#chip-mic').textContent = 'MİKROFON ' + (S.muted ? '· KAPALI' : S.micOk ? '· AÇIK' : '· YOK');
  $('#btn-mic').textContent = S.muted ? 'Mikrofon: kapalı' : 'Mikrofon: açık';
  $('#btn-mic').setAttribute('aria-pressed', String(S.muted));
  document.body.dataset.mode = S.mode || 'none';
}

// ------------------------------------------------------------------ seslendirme
function speechClean(t) {
  return String(t || '').replace(/```[\s\S]*?```/g, ' ').replace(/^\s*\|.*\|\s*$/gm, ' ').replace(/\$\$[\s\S]*?\$\$/g, ' ').replace(/\$([^$\n]+)\$/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/https?:\/\/\S+/g, ' bağlantı ').replace(/_/g, ' ').replace(/[*`#>~]/g, '')
    .replace(/^\s*[-•]\s+/gm, '').replace(/\s+/g, ' ').trim();
}
function splitSentences(t, max = 600) {
  const out = [];
  for (const s of (t.match(/[^.!?…]+[.!?…]*\s*/g) || [t])) {
    const last = out[out.length - 1];
    if (last && (last + s).length < 160) out[out.length - 1] = last + s; else out.push(s.trim());
  }
  let total = 0;
  return out.filter((s) => (total += s.length) <= max || total - s.length === 0);   // çok uzun cevabın tamamını okumaz; ekranda durur
}
// Türkçe sesler kaliteye göre sıralanır: Edge'in "Natural" (sinir ağı) sesleri ücretsizdir ve en doğalıdır; sonra Google/diğer çevrimiçi, en sonda eski yerel sesler
const VOICE_KEY = 'nodus.voice';
const voiceScore = (v) => (/natural/i.test(v.name) ? 10 : 0) + (/online/i.test(v.name) ? 5 : 0) + (/google/i.test(v.name) ? 3 : 0) + (v.localService ? 0 : 1);
const trVoices = () => ((synth && synth.getVoices()) || []).filter((v) => /^tr/i.test(v.lang)).sort((a, b) => voiceScore(b) - voiceScore(a));
const EDGE_KEY = 'nodus.edgevoice', EDGE_LABEL = { 'tr-TR-EmelNeural': 'Emel (kadın) ★', 'tr-TR-AhmetNeural': 'Ahmet (erkek) ★' };
const lsGet = (k) => { try { return localStorage.getItem(k) || ''; } catch { return ''; } };
const edgeVoice = () => (S.edgeVoices.includes(lsGet(EDGE_KEY)) ? lsGet(EDGE_KEY) : S.edgeVoices[0]);
const serverVoice = () => S.engine && !S.ttsDown && S.ctx;   // sunucu sesi (ElevenLabs ya da Microsoft sinir ağı) kullanılıyor mu

// Ses menüsü: Microsoft sinir ağı sesinde Emel/Ahmet, tarayıcı sesinde cihazdaki Türkçe sesler, ElevenLabs'te menü yok
function syncVoiceUI() {
  const wrap = $('#voice-wrap'), sel = $('#voice-sel');
  if (!wrap || !sel) return;
  if (serverVoice() && S.engine === 'edge') {
    sel.replaceChildren(...S.edgeVoices.map((v) => el('option', { value: v, text: EDGE_LABEL[v] || v })));
    sel.value = edgeVoice(); wrap.hidden = false;
  } else if (serverVoice()) {
    wrap.hidden = true;
  } else {
    const list = trVoices();
    sel.replaceChildren(...list.map((v) => el('option', { value: v.name, text: v.name.replace(/^Microsoft /, '').replace(/ - Turkish.*$/, '') + (/natural/i.test(v.name) ? ' ★' : '') })));
    sel.value = S.voice ? S.voice.name : ''; wrap.hidden = !list.length;
  }
}
function pickVoice() {
  const list = trVoices();
  S.voice = list.find((v) => v.name === lsGet(VOICE_KEY)) || list[0] || null;
  syncVoiceUI();
}
if (synth) { pickVoice(); synth.onvoiceschanged = pickVoice; }

function speak(text, after) {
  const clean = speechClean(text);
  S.speaking = true; S.lastSpoken = clean; stopListening(); setState('speaking');
  setCaption('bot', clean.length > 260 ? clean.slice(0, 260) + '…' : clean);
  const done = () => { S.speaking = false; S.spokeAt = Date.now(); if (after) after(); else { setState('idle'); startListening(); } };
  if (!clean) return setTimeout(done, 400);
  const parts = splitSentences(clean);
  if (serverVoice()) return speakServer(parts, (rest) => speakBrowser(rest, done), done);
  speakBrowser(parts, done);
}

// Ses dosyasını çözer ve baştaki/sondaki sessizliği ölçer (mp3'lerin başında ve sonunda doğal bir boşluk olur; art arda çalınca kelime aralarında "bekleme" gibi duyulur).
async function decodeTrim(blob) {
  const buf = await S.ctx.decodeAudioData(await blob.arrayBuffer());
  const d = buf.getChannelData(0), rate = buf.sampleRate, thr = 0.012;
  let a = 0, b = d.length - 1;
  while (a < b && Math.abs(d[a]) < thr) a++;
  while (b > a && Math.abs(d[b]) < thr) b--;
  const off = Math.max(0, a / rate - 0.03), end = Math.min(buf.duration, b / rate + 0.09);   // cümle sonunda kısa bir nefes payı kalır
  return { buf, off, dur: Math.max(0.05, end - off) };
}

// Sunucu sesi (ElevenLabs ya da Microsoft sinir ağı): bütün parçalar AYNI ANDA istenir (üretim gecikmesi çalmayı bölmesin),
// çözülüp kırpılır ve Web Audio ile aralıksız art arda zamanlanır. Hata olursa kalan kısım tarayıcı sesiyle okunur;
// art arda iki hatada sunucu sesi bu oturum için bırakılır.
async function speakServer(parts, fallback, done) {
  const voice = S.engine === 'edge' ? edgeVoice() : undefined;
  const get = (t) => fetch('/api/tts', { method: 'POST', headers: { 'X-Nodus': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ text: t, voice }) })
    .then(async (r) => {
      if (!r.ok) { const d = await r.json().catch(() => ({})); const e = new Error(d.error || r.statusText); e.quota = !!d.quota; throw e; }
      return decodeTrim(await r.blob());
    });
  const jobs = parts.map((t) => { const p = get(t); p.catch(() => {}); return p; });   // hata sırası gelince aşağıda yakalanır
  const srcs = [];
  let when = 0, k = 0, last = Promise.resolve();
  S.stopAudio = () => { srcs.forEach((s) => { try { s.stop(); } catch { /* çoktan bitmiş */ } }); S.playing = false; S.stopAudio = null; };
  try {
    if (S.ctx.state === 'suspended') await S.ctx.resume();
    for (; k < jobs.length; k++) {
      const clip = await jobs[k];
      if (!S.speaking) return;
      const src = S.ctx.createBufferSource();
      src.buffer = clip.buf; src.connect(S.outAnalyser || S.ctx.destination);
      const t0 = Math.max(S.ctx.currentTime + 0.04, when);   // önceki parça bittiği anda başlar; geç kalındıysa hemen
      src.start(t0, clip.off, clip.dur); when = t0 + clip.dur;
      srcs.push(src); S.playing = true; S.ttsFails = 0;
      last = new Promise((r) => { src.onended = r; });
    }
    await last;
    if (!S.speaking) return;
    S.playing = false; S.stopAudio = null; done();
  } catch (e) {
    if (!S.speaking) return;
    await last;   // zaten zamanlanmış parçalar bitsin; yarım cümle kesilmesin
    if (!S.speaking) return;
    S.playing = false; S.stopAudio = null;
    if (e.quota) { S.ttsDown = true; setCaption('you', 'ElevenLabs kotası doldu ya da anahtar geçersiz; tarayıcı sesine geçtim.'); }
    else if (++S.ttsFails >= 2) { S.ttsDown = true; setCaption('you', 'Sunucu sesi alınamıyor (internet?); tarayıcı sesine geçtim.'); }
    if (S.ttsDown) paintSys(S.boot);
    fallback(parts.slice(k));
  }
}

function speakBrowser(parts, done) {
  if (!synth || !parts.length) return setTimeout(done, 400);
  synth.cancel();
  let i = 0;
  const next = () => {
    if (!S.speaking) return;
    if (i >= parts.length) return done();
    const text = parts[i++], u = new SpeechSynthesisUtterance(text);
    u.lang = 'tr-TR'; if (S.voice) u.voice = S.voice; u.rate = 1.03;
    let fired = false;
    const go = () => { if (fired) return; fired = true; clearTimeout(guard); next(); };
    const guard = setTimeout(go, Math.max(2500, text.length * 120));   // bazı tarayıcılarda onend hiç gelmez: takılı kalma
    u.onboundary = () => { S.pulse = 1; };
    u.onstart = () => { S.pulse = 1; };
    u.onend = go; u.onerror = go;
    synth.speak(u);
  };
  next();
}
function interruptSpeech() { S.speaking = false; if (synth) synth.cancel(); if (S.stopAudio) S.stopAudio(); }

// ------------------------------------------------------------------ konuşma tanıma
function startListening() {
  if (!SR || S.muted || S.busy || S.speaking || S.recog || !S.sid || S.srFailed) return;
  const r = new SR();
  r.lang = 'tr-TR'; r.interimResults = true; r.continuous = false; r.maxAlternatives = 1;
  S.heard = '';
  r.onstart = () => { if (!S.pending) setState('listening'); };
  r.onresult = (e) => {
    let text = '';
    for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
    S.heard = text.trim(); setCaption('you', S.heard);
  };
  r.onerror = (e) => {
    if (['not-allowed', 'service-not-allowed'].includes(e.error)) { S.muted = true; S.micOk = false; setCaption('bot', 'Mikrofon izni verilmedi. Adres çubuğundan izin verip sayfayı yenile; yazarak devam edebilirsin.'); }
    else if (e.error === 'network') { S.srFailed = true; setCaption('bot', 'Konuşma tanıma servisine ulaşılamadı (internet?). Şimdilik yazarak devam edebilirsin.'); paintSys(S.boot); }
    paintChips();
  };
  r.onend = () => {
    S.recog = null;
    const text = S.heard; S.heard = '';
    if (text) handleUtterance(text, true);
    else if (!S.muted && !S.busy && !S.speaking && !S.srFailed) setTimeout(startListening, 350);
    else if (!S.busy && !S.speaking && !S.pending) setState('idle');
  };
  try { r.start(); S.recog = r; } catch { S.recog = null; }
}
function stopListening() { const r = S.recog; S.recog = null; S.heard = ''; if (r) { r.onend = null; try { r.abort(); } catch { /* zaten durmus */ } } }

async function initMic() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    const src = S.ctx.createMediaStreamSource(stream);
    S.analyser = S.ctx.createAnalyser(); S.analyser.fftSize = 256; S.analyser.smoothingTimeConstant = 0.7;
    src.connect(S.analyser); S.freq = new Uint8Array(S.analyser.frequencyBinCount); S.micOk = true;
  } catch { S.micOk = false; }
  paintChips();
}

// ------------------------------------------------------------------ konusma akisi
function setMode(m, announce) {
  S.mode = m; paintChips(); paintSys(S.boot);
  if (announce) speak(m === 'auto' ? 'Tamam, bundan sonra onay sormadan çalışacağım.' : 'Tamam, kritik işlemlerden önce sana soracağım.');
}

// fromVoice: konuşma tanımadan geldi (yazılan metin değil). Karar mantığı voice-intent.js'te (saf ve testli).
function handleUtterance(raw, fromVoice) {
  const text = raw.trim(), I = window.nodusIntent;
  // Yankı koruması: Nodus'un sesinin hemen ardından gelen ya da az önce söylediğimiz cümleyi geri okuyan tanımalar kullanıcı sözü sayılmaz
  if (fromVoice && (Date.now() - S.spokeAt < 1500 || I.isEcho(text, S.lastSpoken))) {
    setCaption('you', ''); return setTimeout(startListening, 300);
  }
  setCaption('you', text);
  const m = I.mode(text);
  if (m) return setMode(m, true);
  if (S.pending) {
    const a = I.approval(text);   // yalnızca kısa ve net ifadeler onay sayılır; "yapma" gibi olumsuz kelime her zaman ret
    if (a === true) return decide(true);
    if (a === false) return decide(false);
    return speak('Anlayamadım. Yapayım mı? Evet ya da hayır de.', () => { setState('approval'); startListening(); });
  }
  send(text);
}

function startRun() { S.busy = true; S.steps = []; paintSteps(); setState('thinking'); }

async function send(text) {
  if (!text || S.busy) return;
  addLog('me', text); startRun();
  const fd = new FormData();
  fd.append('sid', S.sid); fd.append('text', text); fd.append('model', 'auto'); fd.append('verify', '0'); fd.append('voice', '1');
  fd.append('auto_exec', S.mode === 'auto' ? '1' : '0'); fd.append('full_auto', S.mode === 'auto' ? '1' : '0');
  try { await stream('/chat', fd, false); } catch (e) { fail(e.message); }
  if (S.busy) fail('Bağlantı beklenmedik şekilde kesildi.');
}

async function decide(approve) {
  if (!S.pending) return;
  S.pending = null; $('#gate').hidden = true; startRun();
  try { await stream('/decision', { sid: S.sid, approve, model: 'auto', auto_exec: false, full_auto: S.mode === 'auto', verify: false }, true); } catch (e) { fail(e.message); }
  if (S.busy) fail('Bağlantı beklenmedik şekilde kesildi.');
}

function fail(msg) { S.busy = false; closeStep(); addLog('bot', 'Hata: ' + msg); speak('Bir sorun oldu. ' + msg); }

function onEvent(ev) {
  switch (ev.type) {
    case 'step': {
      closeStep();
      const m = ev.text.match(/Adım (\d+)\/\d+: `([^`]+)`/);
      S.steps.push(m ? { tool: m[2], t0: Date.now() } : { note: ev.text.replace(/[`*]/g, '').trim().slice(0, 60) });
      paintSteps(); break;
    }
    case 'status': if (ev.label) setCaption('you', ev.label); break;
    case 'error': fail(ev.message || 'Beklenmeyen bir hata.'); break;
    case 'final': onFinal(ev); break;
  }
}

function onFinal(ev) {
  closeStep(); paintSteps(); S.busy = false;
  const m = ev.message || {};
  if (m.content) addLog('bot', speechClean(m.content) || m.content, m.images);
  if (ev.pending) return askApproval(ev.pending);
  const lines = speechClean(m.content).split(/(?<=[.!?])\s+/);
  speak(speechClean(ev.spoken) || lines.slice(-3).join(' ') || 'Tamamlandı.');
  api('/bootstrap').then((b) => { S.boot = b; paintSys(b); }).catch(() => {});
}

function askApproval(p) {
  S.pending = p;
  $('#gate-why').textContent = p.reason || 'Kritik bir işlem yapılmak isteniyor.';
  $('#gate-detail').textContent = (p.detail || JSON.stringify(p.params || {}, null, 2)).slice(0, 1200);
  $('#gate').hidden = false;
  speak(`Onayına ihtiyacım var. ${p.reason || ''} Yapayım mı?`, () => { setState('approval'); startListening(); });
}

// ------------------------------------------------------------------ baslat
async function begin(mode) {
  $('#start').hidden = true;
  try { S.sid = (await post('/session')).id; } catch (e) { return setCaption('bot', 'Sunucuya bağlanılamadı: ' + e.message); }
  setMode(mode, false); setState('idle');
  try {   // tek ses bağlamı: mikrofon girişi ve ElevenLabs çıkışı aynı analizörlerle küreyi sürer
    S.ctx = new (window.AudioContext || window.webkitAudioContext)();
    S.outAnalyser = S.ctx.createAnalyser(); S.outAnalyser.fftSize = 256; S.outAnalyser.connect(S.ctx.destination);
    S.outFreq = new Uint8Array(S.outAnalyser.frequencyBinCount);
  } catch { S.ctx = null; S.outAnalyser = null; }
  initMic();   // beklenmez: izin penceresi cevaplanana kadar getUserMedia askıda kalır ve sesli mod sessiz kalırdı
  await Promise.race([S.bootPromise, new Promise((r) => setTimeout(r, 2500))]);   // geç kalırsa panel sonradan dolar
  paintSys(S.boot); paintChips();
  const hello = mode === 'auto' ? 'Tamam, onay sormadan çalışacağım. Seni dinliyorum.' : 'Tamam, kritik işlemlerden önce sana soracağım. Seni dinliyorum.';
  speak(hello);
}

function orbPressed() {
  if (!S.sid) return;
  if (S.speaking) { interruptSpeech(); setState('idle'); return startListening(); }
  if (S.busy) return;
  if (S.recog) { stopListening(); return setState('idle'); }
  S.muted = false; paintChips(); startListening();
}

function bind() {
  $('#pick-auto').addEventListener('click', () => begin('auto'));
  $('#pick-ask').addEventListener('click', () => begin('ask'));
  if (!SR) $('#warn-sr').hidden = false;
  $('#eleven-save').addEventListener('click', async () => {
    const key = $('#eleven-key').value.trim(), msg = $('#eleven-msg');
    if (!key) { msg.textContent = 'Önce anahtarı yapıştır.'; return; }
    msg.textContent = 'Kaydediliyor…';
    try {
      const r = await post('/setup/eleven', { key });
      S.engine = 'eleven'; S.ttsDown = false; S.ttsFails = 0; $('#eleven-key').value = ''; syncVoiceUI();
      msg.textContent = r.verified ? '✓ Kaydedildi; doğal ses kullanılacak.' : '✓ Kaydedildi (doğrulanamadı: internet ya da kısıtlı izin olabilir).';
    } catch (e) { msg.textContent = e.message; }
  });
  // bootstrap yavaş olabilir (model listeleri): sayfa açılırken arka planda başlar, karşılama onu en fazla 2,5 sn bekler
  S.bootPromise = api('/bootstrap').then((b) => {
    S.boot = b; paintSys(b);
    if (b.edge_voices && b.edge_voices.length) S.edgeVoices = b.edge_voices;
    if (b.tts) S.engine = b.tts;
    if (b.eleven) $('#eleven-msg').textContent = '✓ ElevenLabs anahtarı kayıtlı; doğal ses kullanılacak.';
    syncVoiceUI();
    return b;
  }).catch(() => null);
  $('#gate-yes').addEventListener('click', () => decide(true));
  $('#gate-no').addEventListener('click', () => decide(false));
  $('#text-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const i = $('#text-in'), t = i.value.trim();
    if (!t || !S.sid) return;
    i.value = ''; interruptSpeech(); stopListening(); handleUtterance(t, false);
  });
  $('#btn-mic').addEventListener('click', () => {
    S.muted = !S.muted; paintChips();
    if (S.muted) { stopListening(); if (!S.busy && !S.speaking) setState('idle'); } else startListening();
  });
  $('#btn-stop').addEventListener('click', async () => {
    interruptSpeech(); stopListening();
    if (S.busy) { try { await post('/stop', { sid: S.sid }); } catch { /* is zaten bitmis */ } }
    else { setState('idle'); startListening(); }
  });
  $('#btn-mode').addEventListener('click', () => setMode(S.mode === 'auto' ? 'ask' : 'auto', true));
  $('#voice-sel').addEventListener('change', (e) => {
    try { localStorage.setItem(S.engine === 'edge' && serverVoice() ? EDGE_KEY : VOICE_KEY, e.target.value); } catch { /* gizli pencere: yalnız bu oturumda geçerli */ }
    pickVoice(); interruptSpeech(); stopListening();
    speak('Merhaba, ben Nodus. Sesim böyle.', () => { setState('idle'); startListening(); });
  });
  $('#orb').addEventListener('click', orbPressed);
  document.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && !/INPUT|TEXTAREA|BUTTON/.test(document.activeElement.tagName) && $('#start').hidden) { e.preventDefault(); orbPressed(); }
  });
  setInterval(() => { $('#clock').textContent = new Date().toLocaleTimeString('tr-TR'); }, 1000);
}

// ------------------------------------------------------------------ cizim
const cv = $('#orb'), ctx = cv.getContext('2d');
let W = 0, H = 0, dpr = 1;
function resize() {
  dpr = Math.min(window.devicePixelRatio || 1, 2); W = innerWidth; H = innerHeight;
  cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
addEventListener('resize', resize); resize();

const hsl = (h, s, l, a = 1) => `hsla(${h}, ${s}%, ${l}%, ${a})`;
const TAU = Math.PI * 2;
function arcs(cx, cy, r, rot, n, fill, lw, col) {   // n eşit yay, her biri aralığın 'fill' oranı kadar
  ctx.lineWidth = lw; ctx.strokeStyle = col; ctx.lineCap = 'butt';
  const step = TAU / n;
  for (let i = 0; i < n; i++) { ctx.beginPath(); ctx.arc(cx, cy, r, rot + i * step, rot + i * step + step * fill); ctx.stroke(); }
}
function ticks(cx, cy, r, len, n, rot, col, lw = 1) {
  ctx.lineWidth = lw; ctx.strokeStyle = col; ctx.beginPath();
  for (let i = 0; i < n; i++) {
    const a = rot + (i / n) * TAU, l = i % 5 === 0 ? len * 1.9 : len;
    ctx.moveTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r); ctx.lineTo(cx + Math.cos(a) * (r + l), cy + Math.sin(a) * (r + l));
  }
  ctx.stroke();
}

function levelNow(t) {
  if (S.state === 'listening' && S.analyser) {
    S.analyser.getByteFrequencyData(S.freq);
    let sum = 0; for (let i = 2; i < 42; i++) sum += S.freq[i];
    return Math.min(1, (sum / 40 / 255) * 1.9);
  }
  if (S.state === 'speaking' && S.playing && S.outAnalyser) {   // ElevenLabs çalıyor: gerçek ses seviyesi
    S.outAnalyser.getByteFrequencyData(S.outFreq);
    let sum = 0; for (let i = 2; i < 42; i++) sum += S.outFreq[i];
    return Math.min(1, 0.12 + (sum / 40 / 255) * 2.2);
  }
  if (S.state === 'speaking') return 0.28 + 0.5 * S.pulse + 0.14 * Math.sin(t / 90) * Math.sin(t / 237);
  if (S.state === 'thinking') return 0.22 + 0.08 * Math.sin(t / 260);
  if (S.state === 'approval') return 0.18 + 0.12 * (0.5 + 0.5 * Math.sin(t / 220));
  return 0.06 + 0.03 * Math.sin(t / 900);
}

let last = 0;
function frame(t) {
  requestAnimationFrame(frame);
  const dt = Math.min(48, t - last || 16); last = t;
  const slow = reduceMotion ? 0.2 : 1, k = dt / 16;
  S.pulse *= Math.pow(0.9, k);
  S.target = levelNow(t); S.level += (S.target - S.level) * Math.min(1, 0.18 * k);
  S.hue += (HUE[S.state] - S.hue) * Math.min(1, 0.06 * k);
  const h = S.hue, L = S.level, fast = 1;
  document.documentElement.style.setProperty('--hue', h.toFixed(0));

  const cx = W / 2, cy = H * 0.42, R = Math.min(W, H * 0.9) * 0.14;
  ctx.clearRect(0, 0, W, H);
  ctx.globalCompositeOperation = 'lighter';

  // dış parıltı
  let g = ctx.createRadialGradient(cx, cy, R * 0.4, cx, cy, R * 3);
  g.addColorStop(0, hsl(h, 100, 55, 0.30 + L * 0.35)); g.addColorStop(1, hsl(h, 100, 50, 0));
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, R * 3, 0, TAU); ctx.fill();

  // dış halkalar
  // Dönüş hızı durumla yumuşakça değişir: normalde çok yavaş; konuşurken ve dinlerken ses seviyesine göre hızlanır, susunca yeniden yavaşlar.
  // Mutlak zaman yerine biriken açı kullanılır, böylece hız değişince halkalar sıçramaz.
  const want = { idle: 0.16, listening: 0.22 + L * 1.6, thinking: 0.55, speaking: 0.24 + L * 2.6, approval: 0.2 }[S.state] * slow;
  S.rate += (want - S.rate) * Math.min(1, 0.035 * k);
  S.spin += (dt / 1000) * S.rate;
  const spin = S.spin;
  ticks(cx, cy, R * 2.3, R * 0.05, 120, spin * 0.05, hsl(h, 90, 62, 0.35));
  arcs(cx, cy, R * 2.12, -spin * 0.35 * fast, 3, 0.62, 2, hsl(h, 100, 62, 0.55));
  arcs(cx, cy, R * 1.96, spin * 0.5 * fast, 48, 0.45, 1.5, hsl(h, 90, 65, 0.4));
  arcs(cx, cy, R * 1.8, -spin * 0.8 * fast, 6, 0.3, 4, hsl(h, 100, 60, 0.5 + L * 0.3));
  ctx.lineWidth = 1; ctx.strokeStyle = hsl(h, 80, 60, 0.25); ctx.beginPath(); ctx.arc(cx, cy, R * 1.66, 0, TAU); ctx.stroke();

  // ses çubukları (dinlerken gerçek spektrum, diğer durumlarda seviyeye bağlı dalga)
  const N = 112, base = R * 1.12;
  const spectrum = S.state === 'listening' && S.analyser ? S.freq : S.state === 'speaking' && S.playing && S.outAnalyser ? S.outFreq : null;   // levelNow bu karede doldurdu
  ctx.lineCap = 'round'; ctx.lineWidth = Math.max(2, R * 0.03);
  for (let i = 0; i < N; i++) {
    const a = (i / N) * TAU - Math.PI / 2;
    let v;
    if (spectrum) { const m = i < N / 2 ? i : N - 1 - i; v = spectrum[2 + Math.floor(m * 0.7)] / 255; }
    else v = L * (0.55 + 0.45 * Math.sin(i * 0.33 + spin * 4.8) * Math.sin(i * 0.12 - spin * 1.9));
    const len = R * (0.04 + Math.max(0, v) * 0.5);
    ctx.strokeStyle = hsl(h + v * 30, 100, 62 + v * 18, 0.35 + v * 0.55);
    ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * base, cy + Math.sin(a) * base); ctx.lineTo(cx + Math.cos(a) * (base + len), cy + Math.sin(a) * (base + len)); ctx.stroke();
  }

  // çekirdek: nefes alan küre + dönen plazma lekeleri
  const rr = R * (1 + L * 0.1);
  g = ctx.createRadialGradient(cx - rr * 0.3, cy - rr * 0.35, rr * 0.05, cx, cy, rr);
  g.addColorStop(0, hsl(h, 100, 88, 0.95)); g.addColorStop(0.45, hsl(h, 100, 55, 0.7)); g.addColorStop(1, hsl(h + 10, 100, 25, 0.35));
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, rr, 0, TAU); ctx.fill();
  for (let i = 0; i < 4; i++) {
    const a = spin * (0.7 + i * 0.35) * (i % 2 ? -1 : 1) * fast + i * 1.7, d = rr * (0.25 + 0.12 * Math.sin(t / 700 + i));
    const px = cx + Math.cos(a) * d, py = cy + Math.sin(a * 1.3) * d, pr = rr * (0.5 + L * 0.25);
    const pg = ctx.createRadialGradient(px, py, 0, px, py, pr);
    pg.addColorStop(0, hsl(h + i * 12, 100, 70, 0.35)); pg.addColorStop(1, hsl(h, 100, 50, 0));
    ctx.fillStyle = pg; ctx.beginPath(); ctx.arc(px, py, pr, 0, TAU); ctx.fill();
  }
  ctx.lineWidth = 1.5; ctx.strokeStyle = hsl(h, 100, 80, 0.55); ctx.beginPath(); ctx.arc(cx, cy, rr, 0, TAU); ctx.stroke();

  // düşünürken yörüngede dönen uydular
  if (S.state === 'thinking') for (let i = 0; i < 3; i++) {
    const a = spin * 2.4 + (i * TAU) / 3, rad = R * 1.5;
    ctx.fillStyle = hsl(h, 100, 70, 0.9); ctx.beginPath(); ctx.arc(cx + Math.cos(a) * rad, cy + Math.sin(a) * rad, 3.5, 0, TAU); ctx.fill();
  }
  ctx.globalCompositeOperation = 'source-over';
}

// ------------------------------------------------------------------ acilis
bind(); paintSys(null); paintChips(); requestAnimationFrame(frame);
})();
