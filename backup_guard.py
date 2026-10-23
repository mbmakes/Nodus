# -*- coding: utf-8 -*-
import os
import re
import shutil
import subprocess
import sys

VAULT_DIR = "core_vault"
os.makedirs(VAULT_DIR, exist_ok=True)

_SECRET_RE = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE)

def scrubbed_env() -> dict:
    """Alt sureclere API anahtarlarini gecirmeyen ortam degiskenleri."""
    env = {k: v for k, v in os.environ.items() if not _SECRET_RE.search(k)}
    env["MPLBACKEND"] = "Agg"
    env["PYTHONIOENCODING"] = "utf-8"
    return env

class BackupGuard:
    @staticmethod
    def get_backup_path(file_path: str) -> str:
        return file_path + ".bak"

    @staticmethod
    def get_golden_path(file_path: str) -> str:
        base_name = os.path.basename(file_path)
        name, ext = os.path.splitext(base_name)
        return os.path.join(VAULT_DIR, f"{name}_golden{ext}")

    @classmethod
    def create_snapshot(cls, file_path: str) -> bool:
        """Belirtilen dosyanin sicak yedegini ve altin kopyasini olusturur."""
        if not os.path.exists(file_path):
            return False
        
        # 1. Sicak yedek
        shutil.copy2(file_path, cls.get_backup_path(file_path))
        
        # 2. Altin kasa (yoksa olustur)
        golden = cls.get_golden_path(file_path)
        if not os.path.exists(golden):
            shutil.copy2(file_path, golden)
        return True

    @classmethod
    def rollback(cls, file_path: str) -> bool:
        """Hata durumunda dosyayi once sicak yedege, o da yoksa altin kasaya dondurur."""
        bak = cls.get_backup_path(file_path)
        golden = cls.get_golden_path(file_path)

        if os.path.exists(bak):
            shutil.copy2(bak, file_path)
            print(f"[GUARD] {file_path} sicak yedege donduruldu.")
            return True
        elif os.path.exists(golden):
            shutil.copy2(golden, file_path)
            print(f"[GUARD] {file_path} altin kasaya donduruldu.")
            return True
        return False

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
