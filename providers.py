# -*- coding: utf-8 -*-
"""Cok saglayicili model yonlendirici.

OpenAI uyumlu uc noktalari olan saglayicilari (anahtari tanimli olanlari) birlestirir, modelleri CANLI
kesfeder, gorev turune gore siralar; 429/404/5xx durumunda siradaki modele/saglayiciya gecer ve basarisiz
modeli bir sure dinlendirir. Sabit model adi yoktur: model adlari hizla eskidigi icin her sey listelenen
modellerden puanlanarak secilir."""
import os
import re
import json
import time
import threading
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HEALTH_FILE = os.path.join(BASE_DIR, "memory", "provider_health.json")
USAGE_FILE = os.path.join(BASE_DIR, "memory", "usage.json")
GOOD_FILE = os.path.join(BASE_DIR, "memory", "provider_ok.json")

PROVIDERS = {
    "gemini": {"base": "https://generativelanguage.googleapis.com/v1beta/openai", "env": "GEMINI_API_KEY"},
    "groq": {"base": "https://api.groq.com/openai/v1", "env": "GROQ_API_KEY"},
    "cerebras": {"base": "https://api.cerebras.ai/v1", "env": "CEREBRAS_API_KEY"},
    "mistral": {"base": "https://api.mistral.ai/v1", "env": "MISTRAL_API_KEY"},
    "openrouter": {"base": "https://openrouter.ai/api/v1", "env": "OPENROUTER_API_KEY", "free_only": True,
                   "headers": {"HTTP-Referer": "https://github.com/mbmakes/Nodus", "X-Title": "Nodus"}},
    "ollama": {"base": "http://localhost:11434/v1", "env": None, "local": True},
}
# Gorev turune gore saglayici egilimi (hizli yorumlayicilar kisa isleri, Gemini agir isleri sever).
PROVIDER_BONUS = {
    "fast": {"groq": 2.0, "cerebras": 2.0, "gemini": 1.0, "mistral": 0.5, "openrouter": 0.0, "ollama": -3.0},
    "heavy": {"gemini": 1.5, "groq": 0.5, "cerebras": 0.5, "mistral": 0.5, "openrouter": 0.0, "ollama": -3.0},
}

# Sohbet disi / istenmeyen modeller
_SKIP_RE = re.compile(r"embed|tts|image|audio|live|transcribe|robotics|computer-use|whisper|ocr|imagen|veo|translate|"
                      r"nano-banana|omni|native|rerank|safeguard|customtools|deep-research|orpheus|allam", re.IGNORECASE)
# 'mini', '1b' gibi kucuk modelleri eler; "gemini" gibi kelimelerin ICINDE eslesmez.
_BANNED_RE = re.compile(r"(^|[/\-_:.])(mini|1b|3b|guard|moderation|nemotron|lightning)($|[/\-_:.])", re.IGNORECASE)


def is_banned_model(name: str) -> bool:
    return bool(_BANNED_RE.search(name or ""))


def tool_call_text(name, args) -> str:
    """Modelin YEREL arac cagrisini (gpt-oss gibi) bu uygulamanin EYLEM_DETAYI metin protokolune cevirir."""
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except ValueError:
            args = {}
    name = str(name or "").split(".")[-1].strip()
    return "EYLEM_DETAYI:" + chr(10) + json.dumps({"action": name, "params": args if isinstance(args, dict) else {}},
                                                 ensure_ascii=False)


def _version(low: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", low)
    return float(m.group(1)) if m else 0.0


def _size_b(low: str) -> float:
    sizes = [float(x) for x in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)b(?![a-z])", low)]
    return max(sizes, default=0.0)


def score_model(model_id: str, kind: str = "fast") -> float:
    """Model adindan kaba kalite/hiz puani (yuksek = daha uygun)."""
    low = model_id.lower()
    size, ver = _size_b(low), min(_version(low), 10)
    pts = 0.0
    if kind == "heavy":
        pts += min(size, 200) / 15 + ver * 0.3
        if re.search(r"pro|r1|reason|think|large|405b|gpt-oss|opus|sonnet", low):
            pts += 3
        if "flash" in low:
            pts += 2
    else:
        pts += ver * 0.1 - min(size, 200) / 60
        if re.search(r"lite|instant|small|8b|20b|scout|haiku", low):
            pts += 4
        elif "flash" in low:
            pts += 2
    if re.search(r"preview|exp|beta", low):
        pts -= 1.5
    if "gemma" in low and kind == "heavy":   # API'de kararsiz (500 / zaman asimi)
        pts -= 2
    if "latest" in low:
        pts += 0.5
    return pts


def rank_models(ids: list, kind: str = "fast") -> list:
    ok = [i for i in ids if not _SKIP_RE.search(i) and not is_banned_model(i)]
    return sorted(ok, key=lambda i: score_model(i, kind), reverse=True)


class Router:
    def __init__(self):
        self._lock = threading.RLock()
        self._models = {}      # saglayici -> (zaman, [idler])
        self._cool = {}        # (saglayici, model|None) -> bitis zamani
        self._fails = {}       # (saglayici, model) -> ardisik hata
        self.limits = {}       # saglayici -> son gorulen kota basliklari
        self._usage = {}       # tarih -> saglayici -> {req, tok, e429}
        self._good = {}        # "saglayici|model" -> son basari zamani (calisan modelleri one almak icin)
        self._usage_dirty = 0
        self._load_health()
        self._load_usage()
        self._load_good()

    # ---------------- yardimcilar ----------------
    def _key(self, prov: str) -> str:
        env = PROVIDERS[prov]["env"]
        return (os.getenv(env) or "").strip().strip('"').strip("'") if env else ""

    def _headers(self, prov: str) -> dict:
        h = dict(PROVIDERS[prov].get("headers", {}))
        key = self._key(prov)
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    def redact(self, text) -> str:
        text = str(text)
        for p in PROVIDERS:
            k = self._key(p)
            if k:
                text = text.replace(k, "***")
        return text

    def _load_health(self):
        try:
            with open(HEALTH_FILE, "r", encoding="utf-8") as f:
                now = time.time()
                for k, until in json.load(f).items():
                    prov, _, model = k.partition("|")
                    if until > now:
                        self._cool[(prov, model or None)] = until
        except Exception:
            pass

    def _save_health(self):
        try:  # yalnizca uzun sureli (>=1 saat) dinlendirmeler kalici (kaldirilmis model vb.)
            now = time.time()
            data = {f"{p}|{m or ''}": u for (p, m), u in self._cool.items() if u - now >= 3000}
            os.makedirs(os.path.dirname(HEALTH_FILE), exist_ok=True)
            with open(HEALTH_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass

    def _load_usage(self):
        try:
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                self._usage = json.load(f)
        except Exception:
            self._usage = {}

    def _load_good(self):
        try:
            with open(GOOD_FILE, "r", encoding="utf-8") as f:
                self._good = {k: v for k, v in json.load(f).items() if time.time() - v < 86400}
        except Exception:
            self._good = {}

    def _mark_ok(self, prov: str, model: str):
        with self._lock:
            self._good[f"{prov}|{model}"] = time.time()
            try:
                os.makedirs(os.path.dirname(GOOD_FILE), exist_ok=True)
                with open(GOOD_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._good, f)
            except Exception:
                pass

    def _good_bonus(self, prov: str, model: str) -> float:
        """Yakin zamanda basarili cevap veren model puan kazanir (1 saatte 4'ten 0'a lineer duser)."""
        age = time.time() - self._good.get(f"{prov}|{model}", 0)
        return max(0.0, 4.0 * (1 - age / 3600)) if age < 3600 else 0.0

    def _record(self, prov: str, resp=None, tokens: int = 0, e429: bool = False):
        """Gunluk istek/token sayaci ve (varsa) saglayicinin bildirdigi kalan kota."""
        day = time.strftime("%Y-%m-%d")
        with self._lock:
            d = self._usage.setdefault(day, {}).setdefault(prov, {"req": 0, "tok": 0, "e429": 0})
            d["req"] += 1
            d["tok"] += int(tokens or 0)
            d["e429"] += 1 if e429 else 0
            if resp is not None:
                h = {str(k).lower(): v for k, v in (getattr(resp, "headers", None) or {}).items()}
                lim = {k.replace("x-ratelimit-", ""): v for k, v in h.items() if k.startswith("x-ratelimit-")}
                if lim:
                    lim["_t"] = time.time()
                    self.limits[prov] = lim
            self._usage_dirty += 1
            if self._usage_dirty >= 5:
                self._save_usage()

    def _save_usage(self):
        try:
            for old in sorted(self._usage)[:-7]:   # son 7 gun
                self._usage.pop(old, None)
            os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
            with open(USAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._usage, f)
            self._usage_dirty = 0
        except Exception:
            pass

    def usage_today(self) -> list:
        """[{'saglayici','istek','token','429','kalan_istek','kalan_token'}]"""
        day = self._usage.get(time.strftime("%Y-%m-%d"), {})
        out = []
        for prov in self.available():
            d, lim = day.get(prov, {"req": 0, "tok": 0, "e429": 0}), self.limits.get(prov, {})
            out.append({"saglayici": prov, "istek": d["req"], "token": d["tok"], "429": d["e429"],
                        "kalan_istek": lim.get("remaining-requests", "-"), "kalan_token": lim.get("remaining-tokens", "-")})
        return out

    def _low_quota(self, prov: str, need_tokens: int) -> bool:
        """Saglayicinin son bildirdigi (taze) kalan dakikalik token'i bu istege yetmiyorsa True."""
        lim = self.limits.get(prov) or {}
        if time.time() - lim.get("_t", 0) > 55:      # dakikalik pencere; eski bilgi gecersiz
            return False
        try:
            return int(float(lim.get("remaining-tokens", "inf"))) < need_tokens
        except ValueError:
            return False

    def _cooling(self, prov: str, model=None) -> bool:
        now = time.time()
        return self._cool.get((prov, None), 0) > now or (model is not None and self._cool.get((prov, model), 0) > now)

    def _penalize(self, prov: str, model, seconds: float):
        with self._lock:
            self._cool[(prov, model)] = time.time() + seconds
            if seconds >= 3000:
                self._save_health()

    # ---------------- kesif ----------------
    def available(self) -> list:
        """Anahtari tanimli (veya yerel) saglayicilar."""
        # Yerel Ollama yalniz NODUS_OLLAMA=1 ile acilir: aksi halde arayuzde hep "ollama" noktasi gorunuyordu
        return [p for p, c in PROVIDERS.items() if (c.get("local") and os.getenv("NODUS_OLLAMA")) or self._key(p)]

    def models(self, prov: str) -> list:
        with self._lock:
            cached = self._models.get(prov)
            if cached and time.time() - cached[0] < (600 if cached[1] else 60):
                return cached[1]
        cfg, ids = PROVIDERS[prov], []
        try:
            r = requests.get(cfg["base"] + "/models", headers=self._headers(prov), timeout=1.5 if cfg.get("local") else 8)
            if r.status_code == 200:
                ids = [m["id"].replace("models/", "") for m in r.json().get("data", []) if m.get("id")]
                if cfg.get("free_only"):
                    ids = [i for i in ids if i.endswith(":free")]
            elif r.status_code in (401, 403):
                self._penalize(prov, None, 3600)
        except Exception:
            pass
        with self._lock:
            self._models[prov] = (time.time(), ids)
        return ids

    def candidates(self, kind: str = "fast", preferred: str = None, avoid: tuple = None) -> list:
        scored = []
        for prov in self.available():
            if self._cooling(prov):
                continue
            bonus = PROVIDER_BONUS.get(kind, PROVIDER_BONUS["fast"]).get(prov, 0)
            for mid in rank_models(self.models(prov), kind):
                if not self._cooling(prov, mid):
                    scored.append((score_model(mid, kind) + bonus + self._good_bonus(prov, mid), prov, mid))
        ordered = [(p, m) for _, p, m in sorted(scored, key=lambda x: x[0], reverse=True)]
        if avoid:  # capraz dogrulama: once farkli saglayici, sonra farkli model
            ordered.sort(key=lambda c: (c[0] == avoid[0], c == tuple(avoid)))

        pref = self.parse_preferred(preferred)
        if pref and not self._cooling(*pref) and pref[0] in self.available():
            ordered = [pref] + [c for c in ordered if c != pref]
        return ordered

    @staticmethod
    def parse_preferred(preferred):
        """'gemini::model' -> ('gemini','model');  'x/y:free' -> openrouter;  'auto[:tur]' -> None."""
        if not preferred or str(preferred).startswith("auto"):
            return None
        if "::" in preferred:
            prov, _, model = preferred.partition("::")
            return (prov, model) if prov in PROVIDERS else None
        return ("openrouter", preferred) if "/" in preferred else None

    @staticmethod
    def kind_of(preferred, default: str = "fast") -> str:
        m = re.match(r"auto:(fast|heavy)", str(preferred or ""))
        return m.group(1) if m else default

    # ---------------- sohbet ----------------
    def chat(self, messages: list, kind: str = "fast", preferred: str = None, max_attempts: int = 8,
             timeout=None, temperature: float = 0.2, deadline: float = 140,
             stream_cb=None, avoid: tuple = None):
        """(metin, (saglayici, model), hatalar). Basarisizsa metin None.
        stream_cb(o_ana_kadar_metin) verilirse yanit akarak gelir; yedeklemede metin bastan baslar."""
        timeout = timeout or ((8, 75) if kind == "heavy" else (8, 30))   # dusunen agir modeller ilk token'a 30 sn'den gec gelebilir
        errors, tried, start, prov_fails = [], 0, time.time(), {}
        need = int(sum(len(str(m.get("content", ""))) for m in messages) / 3) + 600   # kaba token tahmini
        for prov, model in self.candidates(kind, preferred, avoid):
            if tried >= max_attempts or time.time() - start > deadline:
                break
            if prov_fails.get(prov, 0) >= 3:   # bir saglayici uc kez dustuyse kalan modellerini atla, siradakine gec
                continue
            if self._low_quota(prov, need):    # bosuna 429 yememek icin kotasi yetmeyen saglayiciyi bu istek icin atla
                errors.append(f"{prov}: kalan token yetersiz, atlandi")
                continue
            tried += 1
            cfg = PROVIDERS[prov]
            try:
                payload = {"model": model, "messages": messages, "temperature": temperature}
                if stream_cb:
                    payload["stream"] = True
                r = requests.post(cfg["base"] + "/chat/completions", headers=self._headers(prov),
                                  json=payload, timeout=timeout, stream=bool(stream_cb))
            except Exception as e:  # zaman asimi: yavas modeli bir sure atla
                self._penalize(prov, model, 900 if isinstance(e, requests.Timeout) else 60)   # tek yavas cevap modeli bir saat susturmasin
                errors.append(f"{prov}/{model}: {type(e).__name__}")
                prov_fails[prov] = prov_fails.get(prov, 0) + 1
                continue

            if r.status_code == 200:
                tokens = 0
                try:
                    if stream_cb:
                        text = self._read_stream(r, stream_cb)
                    else:
                        data = r.json()
                        msg = data["choices"][0]["message"]
                        text = msg.get("content") or ""
                        if not text.strip() and msg.get("tool_calls"):   # yerel arac cagrisi -> metin protokolu
                            fn = msg["tool_calls"][0].get("function") or {}
                            text = tool_call_text(fn.get("name"), fn.get("arguments"))
                        tokens = (data.get("usage") or {}).get("total_tokens", 0)
                except Exception as e:  # akis ortasinda kopma / bozuk govde
                    text = ""
                    if stream_cb:
                        stream_cb("")
                    errors.append(f"{prov}/{model}: {type(e).__name__}")
                self._record(prov, r, tokens)
                if text.strip():
                    self._fails.pop((prov, model), None)
                    self._mark_ok(prov, model)
                    return text, (prov, model), errors
                self._penalize(prov, model, 30)
                errors.append(f"{prov}/{model}: bos yanit")
                prov_fails[prov] = prov_fails.get(prov, 0) + 1
                continue

            body = self.redact(r.text[:160]).replace("\n", " ")
            code = r.status_code
            self._record(prov, r, 0, e429=(code == 429))
            if code == 400 and "tool_use_failed" in (r.text or ""):
                recovered = self._recover_failed_tool_call(r)
                if recovered:
                    self._mark_ok(prov, model)
                    if stream_cb:
                        stream_cb(recovered)
                    return recovered, (prov, model), errors
            n = self._fails.get((prov, model), 0) + 1
            self._fails[(prov, model)] = n
            if code == 429 and re.search(r"limit:\s*0\b|quotaValue\W+0\b", r.text or "", re.IGNORECASE):
                self._penalize(prov, model, 21600)   # ucretsiz kotasi yok (or. Gemini pro): saatlerce deneme
            elif code == 429:
                try:
                    wait = float(r.headers.get("retry-after", ""))
                except ValueError:
                    wait = min(20 * 2 ** (n - 1), 600)
                self._penalize(prov, model, max(wait, 5))
            elif code in (401, 403):
                self._penalize(prov, None, 3600)
            elif code in (404, 410):
                self._penalize(prov, model, 86400)
            elif code == 400:  # istek kaynakli olabilir (baglam cok uzun vb.); yalnizca model sorunuysa uzun bekle
                self._penalize(prov, model, 3600 if re.search(r"model.{0,40}(not found|does not exist|decommission|deprecat|not supported|unavailable)", r.text or "", re.IGNORECASE) else 60)
            else:   # 5xx: ardisik hatalarda bekleme saate cikar ve kalici olur
                self._penalize(prov, model, 60 if n < 3 else 3600)
            errors.append(f"{prov}/{model}: HTTP {code} {body}")
            prov_fails[prov] = prov_fails.get(prov, 0) + 1
        return None, None, errors

    @staticmethod
    def _read_stream(r, cb) -> str:
        """OpenAI uyumlu SSE akisini okur; her parcada cb(birikmis_metin) cagirir.
        Metin yoksa ama yerel arac cagrisi geldiyse onu EYLEM_DETAYI metnine cevirir."""
        r.encoding = "utf-8"
        parts, calls = [], {}
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"]
            except Exception:
                continue
            for tc in delta.get("tool_calls") or []:
                d = calls.setdefault(tc.get("index", 0), {"name": "", "args": ""})
                f = tc.get("function") or {}
                d["name"] += f.get("name") or ""
                d["args"] += f.get("arguments") or ""
            piece = delta.get("content") or ""
            if piece:
                parts.append(piece)
                cb("".join(parts))
        r.close()
        if not parts and calls:
            first = calls[min(calls)]
            text = tool_call_text(first["name"], first["args"])
            cb(text)
            return text
        return "".join(parts)

    @staticmethod
    def _recover_failed_tool_call(r):
        """Groq 400 tool_use_failed: modelin uretmeye calistigi cagri 'failed_generation' icindedir."""
        try:
            gen = r.json()["error"]["failed_generation"]
            obj = json.loads(gen) if isinstance(gen, str) else gen
            if isinstance(obj, list):
                obj = obj[0]
            name = obj.get("name") or (obj.get("function") or {}).get("name")
            args = obj.get("arguments", obj.get("parameters", (obj.get("function") or {}).get("arguments", {})))
            return tool_call_text(name, args) if name else None
        except Exception:
            return None

    def status(self) -> list:
        """Arayuz icin: [{'saglayici', 'model_sayisi', 'dinlenen'}]"""
        out = []
        for prov in self.available():
            ids = self.models(prov)
            out.append({
                "saglayici": prov,
                "model_sayisi": len(rank_models(ids)),
                "dinlenen": self._cooling(prov) or not ids,
            })
        return out


_router = Router()


def get_router() -> Router:
    return _router
