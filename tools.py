# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import sympy as sp
from typing import Dict, Any, List
from path_guard import PathGuard

guard = PathGuard()

class NodusTools:
    """Nodus platformunun guvenli arac seti:
    - Guvenli Dosya Okuma/Yazma/Listeleme
    - Python Kodu Calistirma (Subprocess Sandbox)
    - Sembolik Matematik Motoru (SymPy)
    """

    # --- DOSYA YONETIMI ---
    @staticmethod
    def write_file(filename: str, content: str) -> Dict[str, Any]:
        """allowed_workspace icine guvenli dosya yazar."""
        try:
            full_path = guard.get_safe_path(filename)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"success": True, "message": f"'{filename}' basariyla kaydedildi.", "path": full_path}
        except Exception as e:
            return {"success": False, "error": f"Dosya yazma hatasi: {str(e)}"}

    @staticmethod
    def read_file(filename: str) -> Dict[str, Any]:
        """allowed_workspace icinden guvenli dosya okur."""
        try:
            full_path = guard.get_safe_path(filename)
            if not os.path.exists(full_path):
                return {"success": False, "error": f"'{filename}' bulunamadi."}
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"success": True, "content": content}
        except Exception as e:
            return {"success": False, "error": f"Dosya okuma hatasi: {str(e)}"}

    @staticmethod
    def list_files() -> List[str]:
        """Calisma alanindaki tum dosyalari listeler."""
        try:
            workspace = guard.allowed_dir
            if not os.path.exists(workspace):
                return []
            return [f for f in os.listdir(workspace) if os.path.isfile(os.path.join(workspace, f))]
        except Exception:
            return []

    # --- KOD CALISTIRMA VE HATA AYIKLAMA ---
    @staticmethod
    def execute_python_code(code: str, timeout: int = 15) -> Dict[str, Any]:
        """Python kodunu allowed_workspace dizininde bagimsiz bir alt surec olarak calistirir."""
        temp_file = guard.get_safe_path("_temp_exec.py")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(code)

            result = subprocess.run(
                [sys.executable, temp_file],
                cwd=guard.allowed_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            return {
                "success": result.returncode == 0,
                "stdout": stdout,
                "stderr": stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Calistirma zaman asimina ugradi ({timeout} saniye). Sonsuz dongu olabilir."}
        except Exception as e:
            return {"success": False, "error": f"Yurutme hatasi: {str(e)}"}
        finally:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    # --- ANALITIK VE SEMBOLIK MATEMATIK MOTORU ---
    @staticmethod
    def solve_math(expression_str: str, var_str: str = "x", operation: str = "solve") -> Dict[str, Any]:
        """SymPy ile analitik islem yapar.
        operation: 'solve' (kok bulma), 'diff' (turev), 'integrate' (integral), 'simplify' (sadelestirme)
        """
        try:
            var = sp.symbols(var_str)
            expr = sp.sympify(expression_str)

            if operation == "solve":
                result = sp.solve(expr, var)
            elif operation == "diff":
                result = sp.diff(expr, var)
            elif operation == "integrate":
                result = sp.integrate(expr, var)
            elif operation == "simplify":
                result = sp.simplify(expr)
            else:
                return {"success": False, "error": f"Desteklenmeyen islem turu: {operation}"}

            return {
                "success": True,
                "result": str(result),
                "latex": sp.latex(result)
            }
        except Exception as e:
            return {"success": False, "error": f"Sembolik matematik hatasi: {str(e)}"}