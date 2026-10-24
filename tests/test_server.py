# -*- coding: utf-8 -*-
"""Web sunucusu (server.py) testleri: gercek uvicorn + sahte model. Disk kaydi gecici klasore yazilir."""
import importlib
import json
import os
import socket
import sys
import threading
import time

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
H = {"X-Nodus": "1"}


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    import uvicorn
    os.environ["NODUS_MEMORY_DIR"] = str(tmp_path_factory.mktemp("nodus_mem"))
    server = importlib.import_module("server")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    u = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=u.run, daemon=True).start()
    for _ in range(100):
        if u.started:
            break
        time.sleep(0.05)
    yield server, f"http://127.0.0.1:{port}"
    u.should_exit = True


def events(resp):
    return [json.loads(c[6:]) for c in resp.text.split("\n\n") if c.startswith("data: ")]


def fake_model(server, monkeypatch, script):
    """script: sirayla donecek model yanitlari."""
    it = iter(script)

    def call_model(model_name, prompt_content="", history=None, available_models=None, on_token=None):
        text = next(it)
        if on_token:
            on_token(text)
        return text
    monkeypatch.setattr(server.agent, "call_model", call_model)
    monkeypatch.setattr(server.agent, "select_best_model", lambda p, m=None: ("auto:fast", "test"))
    monkeypatch.setattr(server.agent, "verify_answer", lambda t, r: (None, ""))


def new_sid(base):
    return requests.post(base + "/api/session", headers=H).json()["id"]


def chat(base, sid, text):
    return requests.post(base + "/api/chat", headers=H, data={"sid": sid, "text": text, "model": "auto"})


def test_guard_blocks_foreign_host_origin_and_missing_header(srv):
    _, base = srv
    assert requests.get(base + "/api/ping", headers={"Host": "evil.example"}).status_code == 403
    assert requests.post(base + "/api/session").status_code == 403
    assert requests.post(base + "/api/session", headers={**H, "Origin": "http://evil.example"}).status_code == 403
    assert requests.post(base + "/api/session", headers=H).status_code == 200
    assert "default-src 'self'" in requests.get(base + "/").headers["content-security-policy"]


def test_chat_streams_and_persists(srv, monkeypatch):
    server, base = srv
    fake_model(server, monkeypatch, ["Merhaba, hazırım."])
    sid = new_sid(base)
    ev = events(chat(base, sid, "selam"))
    kinds = [e["type"] for e in ev]
    assert "start" in kinds and kinds[-1] == "final"
    assert ev[-1]["message"]["content"] == "Merhaba, hazırım." and ev[-1]["pending"] is None
    d = requests.get(base + f"/api/session/{sid}", headers=H).json()
    assert [m["role"] for m in d["messages"]] == ["user", "assistant"]
    assert any(s["id"] == sid for s in requests.get(base + "/api/bootstrap", headers=H).json()["sessions"])


def test_risky_action_waits_for_approval_and_can_be_rejected(srv, monkeypatch):
    server, base = srv
    action = 'Siliyorum.\nEYLEM_DETAYI:\n{"action": "delete_file", "params": {"filename": "yok_boyle_dosya.tmp"}}'
    fake_model(server, monkeypatch, [action])
    sid = new_sid(base)
    ev = events(chat(base, sid, "dosyayı sil"))
    assert ev[-1]["type"] == "final" and ev[-1]["pending"]["action"] == "delete_file"
    # onay beklerken yeni gorev kabul edilmez; bekleyen durum sayfa yenilenince de gelir
    assert chat(base, sid, "baska").status_code == 409
    assert requests.get(base + f"/api/session/{sid}", headers=H).json()["pending"]["action"] == "delete_file"
    r = requests.post(base + "/api/decision", headers=H, json={"sid": sid, "approve": False, "model": "auto"})
    last = events(r)[-1]
    assert last["message"]["content"] == "İşlem reddedildi." and last["pending"] is None
    assert requests.post(base + "/api/decision", headers=H, json={"sid": sid, "approve": True}).status_code == 409


def test_approved_action_resumes_task(srv, monkeypatch):
    server, base = srv
    action = 'EYLEM_DETAYI:\n{"action": "delete_file", "params": {"filename": "yok_boyle_dosya.tmp"}}'
    fake_model(server, monkeypatch, [action, "Dosya yoktu, iş tamam."])
    sid = new_sid(base)
    events(chat(base, sid, "sil"))
    r = requests.post(base + "/api/decision", headers=H, json={"sid": sid, "approve": True, "model": "auto"})
    last = events(r)[-1]
    assert last["type"] == "final" and "iş tamam" in last["message"]["content"] and last["pending"] is None


def test_file_endpoints_are_confined(srv):
    _, base = srv
    for p in ("../../.env", "C:/Windows/win.ini", "..\\..\\.env", "/etc/passwd"):
        assert requests.get(base + "/api/file", params={"path": p}, headers=H).status_code == 404, p
        assert requests.get(base + "/api/file/text", params={"path": p}, headers=H).status_code == 404, p
    assert requests.get(base + "/api/session/..%5C..%5Cx", headers=H).status_code in (400, 404)


def test_stop_cancels_running_task(srv, monkeypatch):
    server, base = srv
    started = threading.Event()
    calls = []

    def slow_model(model_name, prompt_content="", history=None, available_models=None, on_token=None):
        calls.append(1)
        started.set()
        for _ in range(100):   # akis suruyor; durdurma token geri cagrisinda yakalanir
            time.sleep(0.05)
            on_token("yaziyorum")
        return "bitti"
    monkeypatch.setattr(server.agent, "call_model", slow_model)
    monkeypatch.setattr(server.agent, "select_best_model", lambda p, m=None: ("auto:fast", "test"))
    sid = new_sid(base)
    out = {}
    t = threading.Thread(target=lambda: out.update(ev=events(chat(base, sid, "uzun is"))))
    t.start()
    assert started.wait(5)
    assert requests.post(base + "/api/stop", headers=H, json={"sid": sid}).status_code == 200
    t.join(10)
    assert not t.is_alive() and len(calls) == 1
    last = out["ev"][-1]
    assert last["type"] == "final" and "durduruldu" in last["message"]["content"]
    assert requests.post(base + "/api/stop", headers=H, json={"sid": sid}).status_code == 409   # artik calisan yok


def test_steps_are_saved_with_the_session(srv, monkeypatch):
    server, base = srv
    action = 'EYLEM_DETAYI:\n{"action": "list_files", "params": {}}'
    fake_model(server, monkeypatch, [action, "Dosyalar listelendi."])
    sid = new_sid(base)
    last = events(chat(base, sid, "dosyalari goster"))[-1]
    assert [s["tool"] for s in last["message"]["steps"]] == ["list_files"]
    d = requests.get(base + f"/api/session/{sid}", headers=H).json()
    saved = d["messages"][-1]["steps"]
    assert saved[0]["tool"] == "list_files" and "ms" in saved[0] and not any(k.startswith("_") for k in saved[0])


def test_stop_kills_running_code(srv, monkeypatch):
    server, base = srv
    action = 'EYLEM_DETAYI:\n{"action": "execute_code", "params": {"code": "import time\ntime.sleep(60)"}}'
    fake_model(server, monkeypatch, [action])
    sid = new_sid(base)
    out = {}

    def run():
        r = requests.post(base + "/api/chat", headers=H, data={"sid": sid, "text": "uzun kod", "model": "auto", "auto_exec": "1"})
        out["ev"] = events(r)
    t = threading.Thread(target=run)
    t.start()
    for _ in range(100):   # alt surec ayaga kalkana kadar bekle
        if server.tools_mod.ACTIVE_PROCS:
            break
        time.sleep(0.05)
    assert server.tools_mod.ACTIVE_PROCS
    t0 = time.time()
    assert requests.post(base + "/api/stop", headers=H, json={"sid": sid}).status_code == 200
    t.join(15)
    assert not t.is_alive() and time.time() - t0 < 12   # 60 sn'lik uyku beklenmedi
    assert "durduruldu" in out["ev"][-1]["message"]["content"] and not server.tools_mod.ACTIVE_PROCS


def test_search_and_export(srv, monkeypatch):
    server, base = srv
    fake_model(server, monkeypatch, ["Rapor icin benzersizkelime54 iceren cevap."])
    sid = new_sid(base)
    events(chat(base, sid, "arama deneme gorevi"))
    assert sid in requests.get(base + "/api/search", params={"q": "BENZERSIZKELIME54"}, headers=H).json()["ids"]
    assert requests.get(base + "/api/search", params={"q": "x"}, headers=H).json()["ids"] == []   # cok kisa sorgu
    r = requests.post(base + "/api/export", headers=H, json={"sid": sid, "format": "docx"})
    assert r.status_code == 200
    f = requests.get(base + "/api/file", params={"path": r.json()["path"], "download": "1"}, headers=H)
    assert f.status_code == 200 and f.content[:2] == b"PK"   # docx = zip
    assert requests.post(base + "/api/export", headers=H, json={"sid": sid, "format": "exe"}).status_code == 400


def test_failed_verification_triggers_one_recalculation(srv, monkeypatch):
    server, base = srv
    first = "Ilk hesap sonucu: basinc kaybi 28.5 kPa bulundu, bu cevap yeterince uzun olsun diye aciklama ile uzatildi ve ayrintilandi."
    fake_model(server, monkeypatch, [first, "Duzeltilmis sonuc: 110.9 kPa."])
    verdicts = iter([(False, "28.5 kPa yanlis, dogrusu ~111 kPa"), (True, "")])
    monkeypatch.setattr(server.agent, "verify_answer", lambda t, r: next(verdicts))
    monkeypatch.setattr(server.agent, "assess_complexity", lambda t: (True, ""))
    sid = new_sid(base)
    r = requests.post(base + "/api/chat", headers=H, data={"sid": sid, "text": "boru kaybi", "model": "auto", "verify": "1"})
    last = events(r)[-1]["message"]["content"]
    assert "110.9 kPa" in last and "yeniden yapıldı" in last and "uyarısı" not in last and "28.5" not in last.split("yeniden yapıldı")[1]


def test_browser_candidates_per_platform(srv):
    server, _ = srv
    mac = server.browser_candidates("darwin", {})
    assert "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" in mac
    assert "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" in mac
    assert all("/Contents/MacOS/" in p for p in mac)
    win = server.browser_candidates("win32", {"ProgramFiles": "C:/P", "LOCALAPPDATA": "C:/L"})
    assert any(p.endswith("msedge.exe") for p in win) and any(p.endswith("chrome.exe") for p in win)
    assert server.browser_candidates("win32", {}) == []          # ortam degiskeni yoksa yol uretme
    assert server.browser_candidates("linux", {}) == []          # Linux: PATH'te aranir


def test_unix_launchers_use_lf_line_endings():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("run_nodus.sh", "run_nodus.command"):
        data = open(os.path.join(root, name), "rb").read()
        assert data.startswith(b"#!/usr/bin/env bash\n") and b"\r" not in data, name   # CRLF macOS'ta "bad interpreter" verir
