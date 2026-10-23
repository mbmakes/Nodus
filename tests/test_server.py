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
