# -*- coding: utf-8 -*-
import os
import json
from typing import List, Dict, Any

class NodusMemory:
    """Nodus Iki Katmanli Hibrit Hafiza Yoneticisi:
    1. Katman: Pinned Facts (Kalici Tercihler / Kurallar)
    2. Katman: Sliding Window (Kayan Pencere & Arka Plan Ozeti)
    """

    def __init__(self, memory_dir: str = "memory", max_recent_messages: int = 20):
        self.memory_dir = memory_dir
        self.max_recent = max_recent_messages
        self.facts_file = os.path.join(memory_dir, "facts.json")
        self.history_file = os.path.join(memory_dir, "history.json")
        self.summary_file = os.path.join(memory_dir, "summary.json")

        self._ensure_storage()

    def _ensure_storage(self):
        """Hafiza klasoru ve dosyalarini baslatir."""
        os.makedirs(self.memory_dir, exist_ok=True)
        if not os.path.exists(self.facts_file):
            self._save_json(self.facts_file, [])
        if not os.path.exists(self.history_file):
            self._save_json(self.history_file, [])
        if not os.path.exists(self.summary_file):
            self._save_json(self.summary_file, {"summary": ""})

    def _load_json(self, path: str, default: Any) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _save_json(self, path: str, data: Any):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # --- 1. KATMAN: KALICI GERCEKLER / KURALLAR (PINNED FACTS) ---
    def get_facts(self) -> List[str]:
        """Tum kalici kurallari getirir."""
        return self._load_json(self.facts_file, [])

    def add_fact(self, fact_text: str) -> bool:
        """Yeni bir kalici kural ekler (tekrarlari onler)."""
        facts = self.get_facts()
        fact_text = fact_text.strip()
        if fact_text and fact_text not in facts:
            facts.append(fact_text)
            self._save_json(self.facts_file, facts)
            return True
        return False

    def remove_fact(self, index: int) -> bool:
        """Belirtilen indeksteki kurali siler."""
        facts = self.get_facts()
        if 0 <= index < len(facts):
            facts.pop(index)
            self._save_json(self.facts_file, facts)
            return True
        return False

    # --- 2. KATMAN: DINAMIK SOHBET VE KAYAN PENCERE ---
    def get_summary(self) -> str:
        """Eski konusmalarin ozetini doner."""
        return self._load_json(self.summary_file, {"summary": ""}).get("summary", "")

    def set_summary(self, summary_text: str):
        """Sohbet ozetini gunceller."""
        self._save_json(self.summary_file, {"summary": summary_text})

    def get_recent_messages(self) -> List[Dict[str, Any]]:
        """Son aktif mesajlari doner."""
        return self._load_json(self.history_file, [])

    def save_chat_turn(self, user_content: Any, assistant_content: str):
        """Kullanici ve asistan mesajlarini temizleyip kaydeder."""
        history = self.get_recent_messages()

        if isinstance(user_content, list):
            text_part = next((item["text"] for item in user_content if item.get("type") == "text"), "")
            cleaned_user = f"[Gorsel Eklendi] {text_part}".strip()
        else:
            cleaned_user = str(user_content)

        history.append({"role": "user", "content": cleaned_user})
        history.append({"role": "assistant", "content": assistant_content})

        if len(history) > self.max_recent:
            history = history[-self.max_recent:]

        self._save_json(self.history_file, history)

    def assemble_system_context(self) -> str:
        """Modelin sistem promptuna eklenecek kalici baglami uretir."""
        context_parts = []

        facts = self.get_facts()
        if facts:
            facts_str = "\n".join([f"- {fact}" for fact in facts])
            context_parts.append(f"### KULLANICI KALICI KURALLARI VE TERCIHLERI:\n{facts_str}")

        summary = self.get_summary()
        if summary:
            context_parts.append(f"### GECMIS KONUSMALARIN ARKA PLAN OZETI:\n{summary}")

        return "\n\n".join(context_parts)

    def reset_history_only(self):
        """Sadece konusma akisini ve ozeti temizler; kalici kurallari korur."""
        self._save_json(self.history_file, [])
        self._save_json(self.summary_file, {"summary": ""})

    def reset_everything(self):
        """Tum hafizayi (kurallar dahil) sifirlar."""
        self._save_json(self.facts_file, [])
        self.reset_history_only()