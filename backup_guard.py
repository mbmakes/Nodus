# -*- coding: utf-8 -*-
import os
import re
import subprocess
import sys

_SECRET_RE = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE)

def scrubbed_env() -> dict:
    """Alt sureclere API anahtarlarini gecirmeyen ortam degiskenleri."""
    env = {k: v for k, v in os.environ.items() if not _SECRET_RE.search(k)}
    env["MPLBACKEND"] = "Agg"
    env["PYTHONIOENCODING"] = "utf-8"
    return env

class BackupGuard:
    @staticmethod
    def verify_syntax(file_path: str) -> bool:
        """Dosyanin sentaks hatasi barindirip barindirmadigini test eder."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                compile(f.read(), file_path, "exec")
            return True
        except SyntaxError as e:
            print(f"[GUARD] Sentaks Hatasi ({file_path}): {e}")
            return False

    @classmethod
    def run_candidate_test(cls, test_script_path: str, target_file: str) -> bool:
        """Adayin sentaksini dogrular ve testini anahtarsiz ortamda calistirir.
        Geri alma islemini cagiran yapar; burada hicbir dosya ezilmez."""
        if not cls.verify_syntax(target_file):
            return False

        try:
            result = subprocess.run(
                [sys.executable, "-X", "utf8", test_script_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                env=scrubbed_env(),
                stdin=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                return True
            print(f"[GUARD] Test Basarisiz:\n{result.stderr}")
            return False
        except Exception as e:
            print(f"[GUARD] Test calistirma hatasi: {e}")
            return False
