# -*- coding: utf-8 -*-
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class PathGuard:
    """Guvenli dosya calisma alani yoneticisi."""

    def __init__(self, allowed_dir: str = None):
        env_dir = os.getenv("WORKSPACE_DIR", "./allowed_workspace")
        target_dir = allowed_dir if allowed_dir else env_dir
        self.workspace_path = Path(target_dir).resolve()
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        self.allowed_dir = str(self.workspace_path)

    def get_safe_path(self, filename: str) -> str:
        """Hedef yolun guvenli calisma dizini icinde kaldigini dogrular."""
        clean_name = os.path.basename(filename)
        safe_target = (self.workspace_path / clean_name).resolve()

        if not safe_target.is_relative_to(self.workspace_path):
            raise PermissionError(f"Guvenlik ihlali: '{filename}' izin verilen dizin disinda.")

        return str(safe_target)