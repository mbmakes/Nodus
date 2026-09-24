import os
import json
import requests
from dotenv import load_dotenv
from path_guard import safe_write_file, WORKSPACE_DIR

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    raise ValueError("Hata: .env dosyasinda OPENROUTER_API_KEY tanimli degil.")

# OpenRouter uzerinde kullanilacak roller ve modeller
MODELS = {

    "router": "openrouter/free",
    "gemini": "openrouter/free",
    "coder": "openrouter/free"
}


def call_openrouter(prompt: str, model: str) -> str:
    """OpenRouter API uzerinden belirlenen modele istek atar."""
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/engineering-agent",
                "X-Title": "Engineering Agent"
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=45
        )
        data = response.json()
        
        if "error" in data:
            return f"API Hatasi: {data['error'].get('message', 'Bilinmeyen hata')}"
            
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Baglanti Hatasi: {e}"

def decide_route(user_prompt: str) -> str:
    """
    Kullanici girdisini analiz ederek hangi uzmana gidecegine karar verir:
    - Kodlama / API / Makro -> 'coder'
    - Diger her sey -> 'gemini'
    """
    code_keywords = ["makro", "solidworks", "ansys", "python kodu", "script", "api", "algoritma"]
    
    if any(keyword in user_prompt.lower() for keyword in code_keywords):
        return "coder"
    return "gemini"

def run_agent(task_prompt: str, output_filename: str = "ajan_raporu.txt"):
    """Gorevi yonlendirir, calistirir ve guvenli sekilde kaydeder."""
    print(f"\n[Gorev]: {task_prompt}")
    
    # 1. Yonlendirme Karari
    target_role = decide_route(task_prompt)
    selected_model = MODELS[target_role]
    print(f"[Router]: Gorev '{target_role}' uzmanina ({selected_model}) aktarildi.")
    
    # 2. Modeli Calistirma
    response_content = call_openrouter(task_prompt, selected_model)
    
    # Eger ucretli Claude modelinde bakiye hatasi verirse ucretsiz modele gecis yap (fallback)
    if "API Hatasi" in response_content and target_role == "coder":
        print("[Router]: Uzman model yanit vermedi, yedek modele (Gemini) aktariliyor...")
        selected_model = MODELS["gemini"]
        response_content = call_openrouter(task_prompt, selected_model)

    print("\n--- MODEL CIKTISI ---")
    print(response_content[:400] + ("...\n[Devami dosyaya yazildi]" if len(response_content) > 400 else ""))

    # 3. Path Guard ile Guvenli Kayit
    target_file = f"./allowed_workspace/{output_filename}"
    kayit_mesaji = safe_write_file(target_file, response_content)
    print(f"\n[Guvenlik Katmani]: {kayit_mesaji}")

if __name__ == "__main__":
    print(f"Engineering Agent Devrede. Izinli Dizin: {WORKSPACE_DIR}")
    
    # Test gorevi
    ornek_soru = "Basit bir mil burulma gerilmesini hesaplayan ornek bir Python fonksiyonu yaz."
    run_agent(ornek_soru, "mil_hesap_ornegi.py")