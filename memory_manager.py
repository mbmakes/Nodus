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
        tmp = path + ".tmp"  # atomik yazim: yarim kalan yazma hafizayi bozmaz
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

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

class NodusNotes:
    """Kalici uzun sureli not hafizasi (SQLite FTS5 ile tam metin arama; FTS5 yoksa LIKE).
    Sohbet gecmisinden bagimsizdir: 'remember' ile eklenir, 'recall' ile aranir."""
    MAX_NOTES = 2000

    def __init__(self, path: str = None):
        import sqlite3
        self._sqlite3 = sqlite3
        self.path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory", "notes.db")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with self._conn() as c:
            try:
                c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS notes USING fts5(text, tags, created UNINDEXED)")
                self.fts = True
            except sqlite3.OperationalError:
                c.execute("CREATE TABLE IF NOT EXISTS notes(text, tags, created)")
                self.fts = False

    def _conn(self):
        from contextlib import closing
        return closing(self._sqlite3.connect(self.path))

    def add(self, text: str, tags: str = "") -> bool:
        import time
        text = str(text).strip()[:2000]
        if not text:
            return False
        with self._conn() as c:
            c.execute("INSERT INTO notes(text, tags, created) VALUES (?,?,?)",
                      (text, str(tags).strip()[:200], time.strftime("%Y-%m-%d %H:%M")))
            c.execute("DELETE FROM notes WHERE rowid <= (SELECT MAX(rowid) FROM notes) - ?", (self.MAX_NOTES,))
            c.commit()
        return True

    def search(self, query: str, limit: int = 5) -> list:
        import re
        tokens = list(dict.fromkeys(re.findall(r"\w{2,}", str(query).lower())))[:12]
        if not tokens:
            return []
        with self._conn() as c:
            if self.fts:
                match = " OR ".join('"%s"' % t.replace('"', "") for t in tokens)
                rows = c.execute("SELECT text, tags, created FROM notes WHERE notes MATCH ? ORDER BY rank LIMIT ?",
                                 (match, limit)).fetchall()
            else:
                cond = " OR ".join("lower(text || ' ' || tags) LIKE ?" for _ in tokens)
                rows = c.execute(f"SELECT text, tags, created FROM notes WHERE {cond} ORDER BY rowid DESC LIMIT ?",
                                 [f"%{t}%" for t in tokens] + [limit]).fetchall()
        return [{"text": t, "tags": g, "created": d} for t, g, d in rows]

    def clear(self):
        with self._conn() as c:
            c.execute("DELETE FROM notes")
            c.commit()


class NodusSessions:
    """Birden fazla sohbeti diske kaydeder ve geri yukler (memory/sessions/<kimlik>.json).
    Gorseller ve buyuk ekler kaydedilmez; yalnizca rol/icerik metni saklanir."""
    ID_RE = r"[0-9]{8}-[0-9]{6}-[0-9a-f]{4}"
    MAX_MESSAGES = 300

    def __init__(self, directory: str = None):
        self.dir = directory or os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory", "sessions")
        os.makedirs(self.dir, exist_ok=True)

    @staticmethod
    def new_id() -> str:
        import time, uuid
        return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]

    def _path(self, sid: str) -> str:
        import re
        if not re.fullmatch(self.ID_RE, str(sid)):
            raise ValueError("Gecersiz sohbet kimligi.")
        return os.path.join(self.dir, f"{sid}.json")

    def save(self, sid: str, messages: list):
        clean = [{"role": m.get("role", "user"), "content": str(m.get("content", ""))[:20000],
                  **({"images": [x for x in m["images"] if isinstance(x, str)][:20]} if m.get("images") else {}),
                  **({"steps": [x for x in m["steps"] if isinstance(x, dict)][:40]} if m.get("steps") else {})}
                 for m in messages if m.get("content")][-self.MAX_MESSAGES:]
        if not clean:
            return
        first = next((m["content"] for m in clean if m["role"] == "user"), "Yeni sohbet")
        data = {"title": " ".join(first.split())[:50] or "Yeni sohbet", "messages": clean}
        path = self._path(sid)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(path + ".tmp", path)

    def list(self) -> list:
        out = []
        for name in os.listdir(self.dir):
            sid = name[:-5]
            if not name.endswith(".json"):
                continue
            try:
                path = self._path(sid)
                with open(path, "r", encoding="utf-8") as f:
                    title = json.load(f).get("title", sid)
                out.append({"id": sid, "title": title, "mtime": os.path.getmtime(path)})
            except Exception:
                continue
        return sorted(out, key=lambda x: x["mtime"], reverse=True)

    def search(self, query: str, limit: int = 30) -> list:
        """Sohbet iceriklerinde (baslik + mesaj metni) arar; eslesen sohbet kimliklerini, yeniden eskiye dondurur."""
        q = str(query or "").strip().lower()
        if len(q) < 2:
            return []
        out = []
        for item in self.list():
            if any(q in str(m.get("content", "")).lower() for m in self.load(item["id"])):
                out.append(item["id"])
                if len(out) >= limit:
                    break
        return out

    def load(self, sid: str) -> list:
        try:
            with open(self._path(sid), "r", encoding="utf-8") as f:
                return json.load(f).get("messages", [])
        except Exception:
            return []

    def delete(self, sid: str):
        try:
            os.remove(self._path(sid))
        except Exception:
            pass
