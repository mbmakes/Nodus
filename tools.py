# -*- coding: utf-8 -*-
import os
import re
import sys
import subprocess
import sympy as sp

class NodusTools:
    def __init__(self, workspace_dir="allowed_workspace"):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.workspace_dir = os.path.join(self.base_dir, workspace_dir)
        os.makedirs(self.workspace_dir, exist_ok=True)

    def _resolve_safe_path(self, filename: str) -> str:
        safe_name = os.path.basename(filename)
        return os.path.join(self.workspace_dir, safe_name)

    def write_file(self, filename: str, content: str) -> dict:
        """Calisma alanina sifirdan dosya yazar."""
        target_path = self._resolve_safe_path(filename)
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"success": True, "message": f"{filename} basariyla kaydedildi."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def read_file(self, filename: str) -> dict:
        """Calisma alanindaki dosyanin icerigini okur."""
        target_path = self._resolve_safe_path(filename)
        if not os.path.exists(target_path):
            return {"success": False, "error": f"{filename} bulunamadi."}
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"success": True, "content": content}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_files(self) -> list:
        """Calisma alanindaki dosyalari listeler."""
        if not os.path.exists(self.workspace_dir):
            return []
        return [f for f in os.listdir(self.workspace_dir) if os.path.isfile(os.path.join(self.workspace_dir, f))]

    def apply_patch(self, filename: str, search_block: str, replace_block: str) -> dict:
        """
        Claude Code tarzi hedefli duzenleme.
        Dosyanin tamamini yeniden yazmak yerine sadece belirtilen kod blogunu degistirir.
        """
        target_path = self._resolve_safe_path(filename)
        if not os.path.exists(target_path):
            return {"success": False, "error": f"Hedef dosya bulunamadi: {filename}"}

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                file_content = f.read()

            s_block = str(search_block).strip()
            r_block = str(replace_block).strip()

            if s_block not in file_content:
                # Satir sonu uyumsuzluklarina karsi esnek arama
                normalized_file = file_content.replace("\r\n", "\n")
                normalized_search = s_block.replace("\r\n", "\n")
                if normalized_search in normalized_file:
                    file_content = normalized_file
                    s_block = normalized_search

            if s_block not in file_content:
                return {
                    "success": False, 
                    "error": f"Degistirilecek kod blogu bulunamadi:\n{s_block}"
                }

            updated_content = file_content.replace(s_block, r_block, 1)

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(updated_content)

            return {"success": True, "message": f"{filename} cerrahi yontemle (patch) guncellendi."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search_codebase(self, query: str) -> dict:
        """Calisma alanindaki tum dosyalarda metin / fonksiyon arar."""
        results = {}
        files = self.list_files()
        for f in files:
            full_p = os.path.join(self.workspace_dir, f)
            try:
                with open(full_p, "r", encoding="utf-8", errors="ignore") as file_obj:
                    for line_num, line in enumerate(file_obj, start=1):
                        if str(query).lower() in line.lower():
                            if f not in results:
                                results[f] = []
                            results[f].append(f"Satir {line_num}: {line.strip()}")
            except Exception:
                pass
        return {"success": True, "matches": results if results else "Eslesme bulunamadi."}

    def execute_python_code(self, code: str) -> dict:
        """Calisma alaninda Python kodu calistirir."""
        temp_file = os.path.join(self.workspace_dir, "_temp_exec.py")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(code)

            result = subprocess.run(
                [sys.executable, temp_file],
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                timeout=30
            )

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stderr": "Calistirma zaman asimina ugradi (Timeout - 30s)."}
        except Exception as e:
            return {"success": False, "stderr": str(e)}

    def solve_math(self, expression: str, variable: str = "x", task: str = "solve") -> dict:
        """SymPy ile sembolik matematik cozer."""
        try:
            var = sp.Symbol(variable)
            expr = sp.sympify(expression)

            if task == "solve":
                sol = sp.solve(expr, var)
            elif task == "diff":
                sol = sp.diff(expr, var)
            elif task == "integrate":
                sol = sp.integrate(expr, var)
            else:
                return {"success": False, "error": f"Gecersiz islem: {task}"}

            return {"success": True, "result": str(sol)}
        except Exception as e:
            return {"success": False, "error": str(e)}