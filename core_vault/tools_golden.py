# -*- coding: utf-8 -*-
import os
import re
import sys
import json
import subprocess
import mss
import requests
from googlesearch import search
from backup_guard import BackupGuard

# ==========================================
# 1. DOSYA VE DIZIN ISLEMLERI
# ==========================================

def read_file(filepath: str) -> str:
    """Belirtilen dosyanin icerigini okur."""
    try:
        if not os.path.exists(filepath):
            return f"Hata: '{filepath}' dosyasi bulunamadi."
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        return f"Dosya okuma hatasi: {str(e)}"

def write_file(filepath: str, content: str) -> str:
    """Belirtilen dosyayi olusturur veya uzerine yazar."""
    try:
        if os.path.dirname(filepath):
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"'{filepath}' basariyla yazildi."
    except Exception as e:
        return f"Dosya yazma hatasi: {str(e)}"

def apply_patch(filepath: str, target_snippet: str, replacement_snippet: str) -> str:
    """Belirli bir dosyadaki hedef kod blogunu yenisiyle degistirir."""
    try:
        if not os.path.exists(filepath):
            return f"Hata: '{filepath}' bulunamadi."

        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        if target_snippet not in content:
            return f"Hata: Hedef blok '{filepath}' icinde bulunamadi."

        new_content = content.replace(target_snippet, replacement_snippet, 1)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"'{filepath}' basariyla yamalandi."
    except Exception as e:
        return f"Yama uygulama hatasi: {str(e)}"

def search_codebase(pattern: str, target_dir: str = ".") -> str:
    """Proje dizininde arama yapar."""
    ignored_dirs = {".git", "core_vault", "__pycache__", ".venv", "venv"}
    results = []

    try:
        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            for file in files:
                if file.endswith((".py", ".json", ".md", ".txt", ".html")):
                    path = os.path.join(root, file)
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            for idx, line in enumerate(f, 1):
                                if re.search(pattern, line, re.IGNORECASE):
                                    results.append(f"{path}:{idx} -> {line.strip()}")
                    except Exception:
                        continue

        if not results:
            return f"'{pattern}' icin eslesme bulunamadi."
        return "\n".join(results[:25])
    except Exception as e:
        return f"Arama hatasi: {str(e)}"

# ==========================================
# 2. CALISTIRMA MOTORU
# ==========================================

def execute_python_code(code: str, timeout: int = 15) -> str:
    """Verilen Python kodunu alt surecte calistirir."""
    try:
        res = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if res.returncode == 0:
            return f"Basarili Cikti:\n{res.stdout.strip() if res.stdout else 'Kod hatasiz calisti.'}"
        else:
            return f"Calisma Hatasi:\n{res.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return f"Hata: Kod {timeout} saniyelik zaman asimina ugradi."
    except Exception as e:
        return f"Calistirma hatasi: {str(e)}"

# ==========================================
# 3. GOOGLE ARAMA VE EKRAN ALGILAMA
# ==========================================

def web_search(query: str, max_results: int = 5) -> str:
    """Google uzerinden arama yapar."""
    try:
        results = search(query, num_results=max_results, advanced=True, lang="tr")
        output = []
        for r in results:
            output.append(f"Baslik: {r.title}\nOzet: {r.description}\nLink: {r.url}\n")
        
        if not output:
            return "Google aramasinda sonuc bulunamadi."
            
        return "\n---\n".join(output)
    except Exception as e:
        return f"Google arama hatasi: {str(e)}"

def capture_screen(output_path: str = "workspace/screen_capture.png") -> str:
    """Masaustunun anlik ekran goruntusunu kaydeder."""
    try:
        if os.path.dirname(output_path):
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with mss.mss() as sct:
            sct.shot(mon=-1, output=output_path)
        return f"Ekran goruntusu kaydedildi: {output_path}"
    except Exception as e:
        return f"Ekran yakalama hatasi: {str(e)}"

# ==========================================
# 4. MUHENDISLIK HESAPLAMA VE OTONOM GELISIM
# ==========================================

def solve_symbolic_math(equation_str: str, variable_str: str = "x") -> str:
    """SymPy ile sembolik denklem cozer."""
    try:
        import sympy as sp
        var = sp.Symbol(variable_str)
        expr = sp.sympify(equation_str)
        solution = sp.solve(expr, var)
        return f"Denklem: {expr} = 0\nCozum kumesi: {solution}"
    except ImportError:
        return "SymPy yuklu degil. 'pip install sympy' calistirin."
    except Exception as e:
        return f"Sembolik cozum hatasi: {str(e)}"

def self_improve(task_description: str) -> str:
    """tools.py dosyasini guvenli sekilde gelistirir."""
    ollama_api = "http://localhost:11434/api/generate"
    model_name = "minicpm-v"
    test_script = "test_candidate.py"
    current_tools = read_file("tools.py")

    prompt = (
        "Sen otonom bir makine muhendisligi yazilim gelistiricisisin.\n\n"
        "Mevcut tools.py icerigi:\n"
        + current_tools + "\n\n"
        "GOREV:\n"
        + task_description + "\n\n"
        "Lutfen su 3 parcayi eksiksiz uret:\n"
        "1. tools.py icine eklenecek Python fonksiyonu.\n"
        "2. TOOL_REGISTRY icine eklenecek sozluk satiri.\n"
        "3. Bu araci test eden izole test_candidate.py kodu (basariliysa sys.exit(0) cagirmali).\n\n"
        "Cevabini SADECE su etiketler arasinda ver:\n"
        "<FUNCTION>\n# Fonksiyon kodu\n</FUNCTION>\n"
        "<REGISTRY_ENTRY>\n# Registry satiri\n</REGISTRY_ENTRY>\n"
        "<TEST>\n# Test kodu\n</TEST>"
    )

    try:
        res = requests.post(
            ollama_api,
            json={"model": model_name, "prompt": prompt, "stream": False},
            timeout=120
        )
        response_text = res.json().get("response", "")
    except Exception as e:
        return f"Model erisim hatasi: {str(e)}"

    func_match = re.search(r"<FUNCTION>(.*?)</FUNCTION>", response_text, re.DOTALL)
    reg_match = re.search(r"<REGISTRY_ENTRY>(.*?)</REGISTRY_ENTRY>", response_text, re.DOTALL)
    test_match = re.search(r"<TEST>(.*?)</TEST>", response_text, re.DOTALL)

    if not (func_match and reg_match and test_match):
        return "Model beklenen formatta kod uretemedi. Islem iptal edildi."

    func_code = func_match.group(1).strip()
    reg_entry = reg_match.group(1).strip()
    test_code = test_match.group(1).strip()

    write_file(test_script, test_code)

    target_marker = "# 5. ARAC CAGRI DAGITICISI (DISPATCHER)"
    patched_func = f"{func_code}\n\n{target_marker}"
    apply_patch("tools.py", target_marker, patched_func)

    reg_marker = "TOOL_REGISTRY = {"
    patched_reg = f"{reg_marker}\n    {reg_entry}"
    apply_patch("tools.py", reg_marker, patched_reg)

    success = BackupGuard.run_candidate_test(test_script)

    if os.path.exists(test_script):
        os.remove(test_script)

    if success:
        return f"Gorev basariyla tamamlandi ve sisteme eklendi: {task_description}"
    else:
        return f"Test basarisiz oldu. Sistem guvenli yedege donduruldu: {task_description}"

# ==========================================
# 5. ARAC CAGRI DAGITICISI (DISPATCHER)
# ==========================================

TOOL_REGISTRY = {
    "read_file": read_file,
    "write_file": write_file,
    "apply_patch": apply_patch,
    "search_codebase": search_codebase,
    "execute_python_code": execute_python_code,
    "web_search": web_search,
    "capture_screen": capture_screen,
    "solve_symbolic_math": solve_symbolic_math,
    "self_improve": self_improve
}

def call_tool(name: str, **kwargs) -> str:
    """Ajanin metin tabanli arac cagrilari icin kopru."""
    if name not in TOOL_REGISTRY:
        return f"Hata: Tanimlanmamis arac '{name}'."
    try:
        return TOOL_REGISTRY[name](**kwargs)
    except Exception as e:
        return f"Arac calistirma hatasi ({name}): {str(e)}"

# ==========================================
# 6. GERIYE DÖNÜK UYUMLULUK (AGENT_CORE KÖPRÜSÜ)
# ==========================================

class NodusTools:
    """agent_core.py tarafindan dogrudan cagirilan arac sinifi."""
    read_file = staticmethod(read_file)
    write_file = staticmethod(write_file)
    apply_patch = staticmethod(apply_patch)
    search_codebase = staticmethod(search_codebase)
    execute_python_code = staticmethod(execute_python_code)
    web_search = staticmethod(web_search)
    capture_screen = staticmethod(capture_screen)
    solve_symbolic_math = staticmethod(solve_symbolic_math)
    self_improve = staticmethod(self_improve)
    call_tool = staticmethod(call_tool)
    registry = TOOL_REGISTRY