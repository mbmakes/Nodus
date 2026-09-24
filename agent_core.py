# -*- coding: utf-8 -*-
import os
import re
import json
import base64
import requests
from tools import NodusTools
from memory_manager import NodusMemory

class NodusAgent:
    def __init__(self, api_key: str, gemini_api_key: str = None):
        self.api_key = api_key
        raw_gemini = gemini_api_key or os.getenv("GEMINI_API_KEY") or ""
        self.gemini_api_key = raw_gemini.strip().strip('"').strip("'")
        
        self.tools = NodusTools()
        self.memory = NodusMemory()
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"

    def _build_system_prompt(self) -> str:
        facts = self.memory.get_facts()
        facts_block = "\n".join([f"- {f}" for f in facts]) if facts else "- Henuz ozel kural tanimlanmadi."

        return f"""Sen Nodus adli otonom bir muhendislik ve karar destek ajanisin.
Gorevin: Muhendislik hesaplamalari yapmak, teknik dokuman hazirlamak, Python scriptleri olusturmak, analiz ve veri gorsellestirme yapmaktir.

KULLANICININ BELIRLEDIGI DEGISTIRILEMEZ KURALLAR (PINNED FACTS):
{facts_block}

KULLANABILECEGIN ARACLAR:
1. write_file: Calisma alanina dosya yazar. Parametreler: {{"filename": "ad.uzanti", "content": "icerik"}}
2. read_file: Calisma alanindaki dosyayi okur. Parametreler: {{"filename": "ad.uzanti"}}
3. list_files: Calisma alanindaki dosyalari listeler. Parametreler: {{}}
4. execute_code: Calisma alaninda Python kodu calistirir. Parametreler: {{"code": "python_kodu"}}
5. solve_math: SymPy ile sembolik matematik cozer. Parametreler: {{"expression": "ifade", "variable": "degisken", "task": "solve/diff/integrate"}}
6. apply_patch: Dosyanin tamamini silmeden yalnizca belirli kod blogunu degistirir. Parametreler: {{"filename": "ad.py", "search_block": "aranan_orijinal_kod", "replace_block": "yeni_kod"}}
7. search_codebase: Calisma alanindaki dosyalarda fonksiyon veya kelime arar. Parametreler: {{"query": "aranan_kelime"}}

KURALLAR:
- ASLA <tool_call> veya benzeri XML/HTML etiketleri kullanma!
- Kullanici bir dosya yazmani, kod calistirmani, duzenlemeni (patch) veya denklem cozmeni istediginde tek basina duz metin yazma; eylemini planla.
- Grafik cizerken Matplotlib kullan. Arayuzsuz calistigin icin ASLA plt.show() kullanma. Grafikleri her zaman calisma alanina plt.savefig('grafik_adi.png', bbox_inches='tight') seklinde kaydet ve ardindan plt.close() cagir.
- Eger bir eylem (tool) calistiracaksan cevabinin EN SONUNA kesinlikle su formatta JSON ekle:

EYLEM_DETAYI:
{{
  "action": "arac_adi",
  "params": {{"parametre_adi": "deger"}}
}}
"""

    def _get_candidate_gemini_models(self) -> list:
        priority_models = [
            "gemini-3.6-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-2.5-flash"
        ]
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.gemini_api_key}"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                models = res.json().get("models", [])
                valid = [
                    m["name"].replace("models/", "") for m in models
                    if "generateContent" in m.get("supportedGenerationMethods", [])
                    and "gemini" in m.get("name", "").lower()
                    and "embedding" not in m.get("name", "").lower()
                ]
                for m in valid:
                    if m not in priority_models:
                        priority_models.append(m)
        except Exception:
            pass
        return priority_models

    def transcribe_engineering_image(self, image_bytes: bytes, mime_type: str = "image/png") -> tuple:
        """Gorseli Gemini Vision ile analiz eder. Dondurur: (Basari: bool, Mesaj/Dokum: str)"""
        if not self.gemini_api_key:
            return False, "GEMINI_API_KEY tanimli degil. Lutfen .env dosyasina ekleyin."

        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        prompt = (
            "Sen muhendislik ve teknik cizimleri hatasiz sayisallastiran uzman bir teknik algilayicisin (Perception Layer).\n"
            "Gorevin: Bu gorseldeki teknik cizimi, semayi, soruyu ve tablolari analiz etmek ve eksiksiz bir teknik ozet cikarmaktir.\n"
            "Lutfen su bilgileri net bir sekilde cikar:\n"
            "1. Soru metni ve istenen tum maddeler (a, b, c vb.).\n"
            "2. Geometri, dugum noktalari (A, B, C...), mesafeler/olculer ve mesnet turleri (sabit pim, kayar mesnet, ankastre vb.).\n"
            "3. Uygulanan tum yukler (degerleri, yonleri, acilari ve hangi dugume uygulandiklari).\n"
            "NOT: Cozum veya hesaplama yapma. Yalnizca gordugun tum verileri eksiksiz bir teknik dokum olarak listele."
        )

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data
                        }
                    }
                ]
            }]
        }

        candidates = self._get_candidate_gemini_models()
        last_error = ""

        for model_slug in candidates:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_slug}:generateContent?key={self.gemini_api_key}"
            try:
                resp = requests.post(url, json=payload, timeout=35)
                if resp.status_code == 200:
                    data = resp.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    return True, text
                last_error = f"Model {model_slug} (Kod {resp.status_code})"
                continue
            except Exception as e:
                last_error = f"Model {model_slug} hatasi: {str(e)}"
                continue

        return False, f"Gemini Vision modellerinden yanit alinamadi. Son durum: {last_error}"

    def assess_complexity(self, prompt_text: str) -> tuple:
        """Girdinin teknik agirligini ve karmasikligini puanlar."""
        score = 0
        reasons = []
        text_lower = str(prompt_text).lower()

        if "teknik dokumu (perception)" in text_lower or "inline_data" in text_lower:
            score += 4
            reasons.append("Teknik Cizim/Diyagram")

        heavy_engineering = [
            "kafes", "truss", "mesnet", "statik", "mukavemet", "gerilme", "stress", 
            "sehim", "burulma", "atalet", "moment", "serbest cisim", "kesit metodu", "dugum metodu",
            "akiskan", "navier-stokes", "bernoulli", "reynolds", "sinir tabaka",
            "termodinamik", "entropi", "entalpi", "carnot", "rankine",
            "diferansiyel", "laplace", "fourier", "matris", "ozdeger", "eigen", 
            "sonlu eleman", "ansys", "fluent", "simulasyon"
        ]
        matched_eng = [kw for kw in heavy_engineering if kw in text_lower]
        if matched_eng:
            eng_weight = min(len(matched_eng) * 2, 4)
            score += eng_weight
            reasons.append(f"Muhendislik Kavramlari ({', '.join(matched_eng[:2])})")

        math_patterns = [r"\b\d+\.?\d*\s*(?:kn|n|kpa|mpa|gpa|mm|m/s|rad/s)\b", r"[\^_\{\}\\]", r"[=<>]=?"]
        math_matches = sum(len(re.findall(p, text_lower)) for p in math_patterns)
        if math_matches >= 3:
            score += 2
            reasons.append("Birim/Sayisal Yogunluk")

        reasoning_prompts = ["adim adim", "ayrintili", "ispatla", "analiz et", "cozumunu yap", "hesapla"]
        if any(rp in text_lower for rp in reasoning_prompts):
            score += 1
            reasons.append("Adim Adim Hesaplama")

        is_heavy = score >= 3
        return is_heavy, score, reasons

    def select_best_model(self, prompt_text: str, available_models: list) -> tuple:
        """Gorevin zorluk seviyesine gore en kararlı modeli dinamik olarak secer."""
        if not available_models:
            return "meta-llama/llama-3.3-70b-instruct:free", "Model listesi bos, varsayilan atandi."

        is_heavy, score, reasons = self.assess_complexity(prompt_text)

        tier1_heavy = [
            "llama-3.3-70b",
            "deepseek-r1",
            "qwen-2.5-72b"
        ]

        tier2_fast = [
            "llama-3.1-8b",
            "qwen",
            "mistral"
        ]

        banned = ["mini", "1b", "3b", "lite", "nex", "small", "guard", "moderation", "nemotron", "lightning"]
        selected = None

        if is_heavy:
            for heavy_slug in tier1_heavy:
                for m in available_models:
                    m_low = m.lower()
                    if heavy_slug in m_low and not any(b in m_low for b in banned):
                        selected = m
                        break
                if selected:
                    break
            report = f"Agir Problem (Skor {score}/10: {', '.join(reasons)}) -> Yuksek Muhakeme Modeli"
        else:
            for fast_slug in tier2_fast:
                for m in available_models:
                    m_low = m.lower()
                    if fast_slug in m_low and not any(b in m_low for b in banned):
                        selected = m
                        break
                if selected:
                    break
            report = f"Standart Gorev (Skor {score}/10) -> Hizli Model"

        if not selected:
            clean_pool = [m for m in available_models if not any(b in m.lower() for b in banned)]
            selected = clean_pool[0] if clean_pool else available_models[0]

        return selected, report

    def call_model(self, model_name: str, prompt_content: str, history: list, available_models: list = None) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "Nodus Platform"
        }

        messages = [{"role": "system", "content": self._build_system_prompt()}]
        messages.extend(history)

        pool = available_models or []
        banned = ["mini", "1b", "3b", "guard", "moderation", "nex", "nemotron", "lightning"]
        text_candidates = [m for m in pool if not any(w in m.lower() for w in banned)]
        
        models_to_try = [model_name]
        for m in text_candidates:
            if m != model_name and len(models_to_try) < 2:
                models_to_try.append(m)

        last_error = "Bilinmeyen hata olustu."
        for target_model in models_to_try:
            payload = {
                "model": target_model,
                "messages": messages,
                "temperature": 0.1
            }
            try:
                response = requests.post(self.api_url, headers=headers, json=payload, timeout=(10, 35))
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"]
                last_error = f"Model {target_model} yanit vermedi (Kod {response.status_code})"
                continue
            except requests.exceptions.Timeout:
                last_error = f"Model {target_model} zaman asimina ugradi (Timeout)"
                continue
            except Exception as e:
                last_error = f"Baglanti hatasi ({target_model}): {str(e)}"
                continue

        return f"⚠️ Modellerden yanit alinamadi. Son durum: {last_error}"

    def parse_action(self, response_text: str):
        """Model ciktisindan eylemi yakalar (JSON ve XML/<tool_call> hibrit destekli)."""
        try:
            # 1. Standart EYLEM_DETAYI blogu kontrolu
            if "EYLEM_DETAYI:" in response_text:
                json_part = response_text.split("EYLEM_DETAYI:")[1].strip()
                if json_part.startswith("```"):
                    json_part = re.sub(r"^```[a-zA-Z]*\n", "", json_part)
                    json_part = re.sub(r"\n```$", "", json_part)
                return json.loads(json_part.strip())

            # 2. Genel JSON nesnesi yakalama
            match = re.search(r'\{[\s\r\n]*"action"[\s\r\n]*:[\s\S]*?\}', response_text)
            if match:
                raw_json = match.group(0).strip()
                return json.loads(raw_json)

            # 3. Modelin XML <tool_call> uretmesi durumu (Qwen/Hermes modelleri)
            xml_match = re.search(r'<tool_call>(.*?)</tool_call>', response_text, re.DOTALL)
            if xml_match:
                inner = xml_match.group(1).strip()
                if inner.startswith("{") and inner.endswith("}"):
                    data = json.loads(inner)
                    return {"action": data.get("name"), "params": data.get("arguments", {})}
                
                parts = inner.split(None, 1)
                action_name = parts[0].strip() if parts else ""
                pairs = re.findall(r'<arg_key>(.*?)</arg_key>\s*<arg_value>(.*?)</arg_value>', inner, re.DOTALL)
                params = {k.strip(): v.strip() for k, v in pairs}
                return {"action": action_name, "params": params}

        except Exception as e:
            print(f"Action parse hatasi: {e}")
        return None

    def execute_approved_action(self, action_info: dict) -> dict:
        """Kullanicinin onayladigi veya guvenli gorulen eylemi yurutur."""
        action = action_info.get("action")
        params = action_info.get("params", {})

        if action == "write_file":
            return self.tools.write_file(params.get("filename"), params.get("content"))
        elif action == "read_file":
            return self.tools.read_file(params.get("filename"))
        elif action == "list_files":
            return {"files": self.tools.list_files()}
        elif action == "execute_code":
            return self.tools.execute_python_code(params.get("code"))
        elif action == "solve_math":
            return self.tools.solve_math(
                params.get("expression"),
                params.get("variable", "x"),
                params.get("task", "solve")
            )
        elif action == "apply_patch":
            return self.tools.apply_patch(
                params.get("filename"),
                params.get("search_block"),
                params.get("replace_block")
            )
        elif action == "search_codebase":
            return self.tools.search_codebase(params.get("query"))
        else:
            return {"error": f"Bilinmeyen eylem turu: {action}"}