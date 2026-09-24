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
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.tools = NodusTools()
        self.memory = NodusMemory()
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_api_key}"

        self.fallback_pool = [
            "deepseek/deepseek-r1:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "meta-llama/llama-3.1-8b-instruct:free"
        ]

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

KURALLAR:
- Kullanici bir dosya yazmani, kod calistirmani veya denklem cozmeni istediginde tek basina duz metin yazma; eylemini planla.
- Grafik cizerken Matplotlib kullan. Arayuzsuz calistigin icin ASLA plt.show() kullanma. Grafikleri her zaman calisma alanina plt.savefig('grafik_adi.png', bbox_inches='tight') seklinde kaydet ve ardindan plt.close() cagir.
- Eger bir eylem (tool) calistiracaksan cevabinin EN SONUNA kesinlikle su formatta JSON ekle:

EYLEM_DETAYI:
{{
  "action": "arac_adi",
  "params": {{"parametre_adi": "deger"}}
}}
"""

    def transcribe_engineering_image(self, image_bytes: bytes, mime_type: str = "image/png") -> str:
        """Gorseli Gemini Vision ile analiz edip eksiksiz yapilandirilmis teknik metne donusturur."""
        if not self.gemini_api_key:
            return "HATA: GEMINI_API_KEY tanimli degil. Lutfen .env dosyasina ekleyin."

        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        prompt = (
            "Sen muhendislik ve teknik cizimleri hatasiz sayisallastiran uzman bir teknik algilayicisin (Perception Layer).\n"
            "Gorevin: Bu gorseldeki teknik cizimi, semayi, soruyu ve tablolari analiz etmek ve eksiksiz bir teknik ozet cikarmaktir.\n"
            "Lutfen su bilgileri net bir sekilde cikar:\n"
            "1. Soru metni ve istenen tum maddeler (a, b, c vb.).\n"
            "2. Geometri, dugum noktalari (A, B, C...), mesafeler/olculer ve mesnet turleri (sabit pim, kayar mesnet, ankastre vb.).\n"
            "3. Uygulanan tum yukler (degerleri, yonleri, acilari ve hangi dugume uygulandiklari).\n"
            "NOT: Hesaplama veya cozum yapma. Sadece gordugun teknik verileri eksiksiz ve yapilandirilmis bir liste halinde dök."
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

        try:
            resp = requests.post(self.gemini_url, json=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            return f"Gemini Vision Baglanti Hatasi (Kod {resp.status_code}): {resp.text}"
        except Exception as e:
            return f"Gemini Vision Hatasi: {str(e)}"

    def select_best_model(self, prompt_text: str, available_models: list) -> str:
        """Gorevin agirligina gore OpenRouter uzerindeki en guclu modeli secer."""
        if not available_models:
            return "meta-llama/llama-3.3-70b-instruct:free"

        prompt_lower = str(prompt_text).lower()
        heavy_engineering_triggers = [
            "kafes", "truss", "mesnet", "statik", "mukavemet", "akiskan", 
            "termodinamik", "diferansiyel", "gerilme", "stress", "tork", "sehim", 
            "atalet", "moment", "integral", "matris", "eigen", "simulasyon", "sonlu eleman"
        ]
        is_heavy_task = any(kw in prompt_lower for kw in heavy_engineering_triggers)

        if is_heavy_task:
            for heavy_slug in ["deepseek-r1", "llama-3.3-70b"]:
                for m in available_models:
                    if heavy_slug in m.lower():
                        return m

        for coder_slug in ["deepseek-r1", "llama-3.3-70b", "coder"]:
            for m in available_models:
                if coder_slug in m.lower() and not any(w in m.lower() for w in ["mini", "1b", "3b", "lite"]):
                    return m

        for general_slug in ["llama-3.3-70b", "instruct"]:
            for m in available_models:
                if general_slug in m.lower() and not any(w in m.lower() for w in ["mini", "1b", "3b"]):
                    return m

        return available_models[0]

    def call_model(self, model_name: str, prompt_content: str, history: list, available_models: list = None) -> str:
        """OpenRouter API cagirisi yapar."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "Nodus Platform"
        }

        messages = [{"role": "system", "content": self._build_system_prompt()}]
        messages.extend(history)

        pool = available_models or []
        text_candidates = [m for m in pool if not any(w in m.lower() for w in ["mini", "1b", "3b", "guard", "moderation"])]
        models_to_try = [model_name] + [m for m in text_candidates if m != model_name]

        if not models_to_try:
            models_to_try = [model_name]

        last_error = "Bilinmeyen hata olustu."

        for target_model in models_to_try:
            payload = {
                "model": target_model,
                "messages": messages,
                "temperature": 0.1
            }
            try:
                response = requests.post(self.api_url, headers=headers, json=payload, timeout=50)
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

        return f"⚠️ Secilen ve yedek modellerden yanit alinamadi. Son durum: {last_error}"

    def parse_action(self, response_text: str):
        """Model ciktisindan eylem detayini yakalar."""
        try:
            if "EYLEM_DETAYI:" in response_text:
                json_part = response_text.split("EYLEM_DETAYI:")[1].strip()
                if json_part.startswith("```"):
                    json_part = re.sub(r"^```[a-zA-Z]*\n", "", json_part)
                    json_part = re.sub(r"\n```$", "", json_part)
                return json.loads(json_part.strip())

            match = re.search(r'\{[\s\r\n]*"action"[\s\r\n]*:[\s\S]*\}', response_text)
            if match:
                raw_json = match.group(0).strip()
                if raw_json.endswith("```"):
                    raw_json = raw_json[:-3].strip()
                return json.loads(raw_json)
        except Exception as e:
            print(f"Action parse hatasi: {e}")
        return None

    def execute_approved_action(self, action_info: dict) -> dict:
        """Kullanicinin onayladigi eylemi yurutur."""
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
        else:
            return {"error": f"Bilinmeyen eylem turu: {action}"}