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


def test_busy_flag_is_set_before_the_job_thread_starts(srv, monkeypatch):
    server, base = srv
    from starlette.responses import JSONResponse
    sid, seen = new_sid(base), []
    monkeypatch.setattr(server, "sse", lambda job: (seen.append(server.STATE[sid].busy), JSONResponse({"ok": True}))[1])
    assert chat(base, sid, "selam").status_code == 200
    assert seen == [True]                                                # is parcacigi baslamadan once bayrak kalkmis olmali
    assert chat(base, sid, "ikinci").status_code == 409                  # ayni sohbette ikinci gorev araya giremez
    server.STATE[sid].busy = False
    assert chat(base, sid, "").status_code == 400 and not server.STATE[sid].busy   # reddedilen istek bayragi birakmaz


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
    assert [s["tool"] for s in last["message"]["steps"] if "tool" in s] == ["list_files"]
    assert any("Model yanıtı ve araçlar:" in s.get("note", "") for s in last["message"]["steps"])   # sure notu arayuzde gorunur
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
    for name in ("run_nodus.sh", "run_nodus.command", "install.sh"):
        data = open(os.path.join(root, name), "rb").read()
        assert data.startswith(b"#!/usr/bin/env bash\n") and b"\r" not in data, name   # CRLF macOS'ta "bad interpreter" verir


# ---------------------------------------------------------------- guncelleme
def _fake_release(version="1.1-beta"):
    return {"current": "1.0-beta", "available": True, "latest": {
        "tag": "v" + version, "version": version, "name": "Nodus v" + version, "notes": "## Yenilikler\n- bir sey",
        "url": "https://example.test/r", "published": "2026-10-24T00:00:00Z", "zipball": "https://api.github.com/zip"}}


def _reset_update(server):
    server.UPDATE.update(state="idle", step="", message="", version="")
    server._update_cache.update(t=0.0, info=None)


def test_ping_reports_version_and_update_check_hides_download_url(srv, monkeypatch):
    server, base = srv
    _reset_update(server)
    assert requests.get(base + "/api/ping").json()["version"] == server.__version__
    monkeypatch.setattr(server.updater, "check", lambda current: _fake_release())
    d = requests.get(base + "/api/update/check?force=1", headers=H).json()
    assert d["available"] and d["latest"]["version"] == "1.1-beta" and "zipball" not in d["latest"] and d["mode"] in ("zip", "git")
    monkeypatch.setenv("NODUS_NO_UPDATE_CHECK", "1")
    assert requests.get(base + "/api/update/check", headers=H).json()["disabled"]
    assert requests.post(base + "/api/update", headers=H).status_code == 403


def test_update_check_survives_network_failure(srv, monkeypatch):
    server, base = srv
    _reset_update(server)

    def boom(current):
        raise ConnectionError("internet yok")
    monkeypatch.setattr(server.updater, "check", boom)
    d = requests.get(base + "/api/update/check?force=1", headers=H).json()
    assert d["available"] is False and d["error"] == "ConnectionError"


def test_update_applies_files_keeps_data_and_restarts(srv, monkeypatch, tmp_path):
    import zipfile
    server, base = srv
    _reset_update(server)
    target = tmp_path / "install"
    target.mkdir()
    (target / "server.py").write_text("eski")
    (target / ".env").write_text("GEMINI_API_KEY=gizli")
    zpath = tmp_path / "rel.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("o-Nodus-abc/version.py", '__version__ = "1.1-beta"\n')
        z.writestr("o-Nodus-abc/server.py", "yeni")
        z.writestr("o-Nodus-abc/.env", "EZMEMELI")
    restarted = []
    monkeypatch.setattr(server, "UPDATE_TARGET", str(target))
    monkeypatch.setattr(server.updater, "check", lambda current: _fake_release())
    monkeypatch.setattr(server.updater, "download_zip", lambda url, dest: open(dest, "wb").write(zpath.read_bytes()))
    monkeypatch.setattr(server.updater, "install_requirements", lambda t: (True, ""))
    monkeypatch.setattr(server, "schedule_restart", lambda: restarted.append(1))
    assert requests.post(base + "/api/update", headers=H).status_code == 200
    for _ in range(100):
        st = requests.get(base + "/api/update/status", headers=H).json()
        if st["state"] != "running":
            break
        time.sleep(0.1)
    assert st["state"] == "done" and st["version"] == "1.1-beta" and restarted == [1]
    assert (target / "server.py").read_text() == "yeni" and (target / ".env").read_text() == "GEMINI_API_KEY=gizli"
    assert chat(base, new_sid(base), "merhaba").status_code == 409      # guncelleme bitti, yeniden baslamayi bekliyor
    _reset_update(server)


def test_update_refused_when_task_running_or_already_current_or_failing(srv, monkeypatch, tmp_path):
    server, base = srv
    _reset_update(server)
    monkeypatch.setattr(server, "UPDATE_TARGET", str(tmp_path))
    monkeypatch.setattr(server.updater, "check", lambda current: _fake_release())
    sid = new_sid(base)
    server.STATE[sid].busy = True
    try:
        assert requests.post(base + "/api/update", headers=H).status_code == 409      # gorev calisirken guncelleme yok
    finally:
        server.STATE[sid].busy = False
    cur = _fake_release(); cur["available"] = False
    monkeypatch.setattr(server.updater, "check", lambda current: cur)
    assert requests.post(base + "/api/update", headers=H).status_code == 409          # zaten guncel
    monkeypatch.setattr(server.updater, "check", lambda current: _fake_release())

    def fail(url, dest):
        raise server.updater.UpdateError("Izin verilmeyen indirme adresi.")
    monkeypatch.setattr(server.updater, "download_zip", fail)
    assert requests.post(base + "/api/update", headers=H).status_code == 200
    for _ in range(100):
        st = requests.get(base + "/api/update/status", headers=H).json()
        if st["state"] != "running":
            break
        time.sleep(0.1)
    assert st["state"] == "error" and "Izin verilmeyen" in st["message"]
    _reset_update(server)


# ---------------------------------------------------------------- ilk kurulum: anahtar ekleme
KEY = "AIzaSyTESTKEY_0123456789abcdef"


def test_bootstrap_reports_missing_keys_and_ping_has_boot_id(srv, monkeypatch):
    server, base = srv
    for e in server.KEY_ENV.values():
        monkeypatch.delenv(e, raising=False)
    b = requests.get(base + "/api/bootstrap", headers=H).json()
    assert b["needs_keys"] is True and b["keys"] == dict.fromkeys(["gemini", "groq", "openrouter", "cerebras", "mistral"], False)
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    b = requests.get(base + "/api/bootstrap", headers=H).json()
    assert b["needs_keys"] is False and b["keys"]["gemini"] is True and KEY not in str(b)        # anahtar asla geri donmez
    assert requests.get(base + "/api/ping").json()["boot"] == server.BOOT_ID


def test_setup_keys_writes_env_keeps_other_lines_and_restarts(srv, monkeypatch, tmp_path):
    server, base = srv
    env = tmp_path / ".env"
    env.write_text("FOO=bar\nGEMINI_API_KEY=eski\n# GROQ_API_KEY=yorum\n")
    restarted = []
    monkeypatch.setattr(server, "ENV_PATH", str(env))
    monkeypatch.setattr(server, "validate_key", lambda prov, key: True if prov == "gemini" else None)
    monkeypatch.setattr(server, "schedule_restart", lambda: restarted.append(1))
    for e in server.KEY_ENV.values():
        monkeypatch.setenv(e, "x")                                     # test sonunda eski ortam geri yuklensin
    r = requests.post(base + "/api/setup/keys", headers=H, json={"gemini": " " + KEY + " ", "groq": "gsk_" + "a" * 20})
    assert r.status_code == 200 and r.json() == {"ok": True, "unverified": ["Groq"]} and restarted == [1]
    lines = env.read_text().splitlines()
    assert "FOO=bar" in lines and f"GEMINI_API_KEY={KEY}" in lines and "# GROQ_API_KEY=yorum" in lines and "GROQ_API_KEY=gsk_" + "a" * 20 in lines
    assert "GEMINI_API_KEY=eski" not in lines and KEY not in r.text
    if os.name != "nt":
        assert oct(os.stat(env).st_mode & 0o777) == "0o600"


def test_setup_keys_rejects_bad_input_without_writing(srv, monkeypatch, tmp_path):
    server, base = srv
    env = tmp_path / ".env"
    monkeypatch.setattr(server, "ENV_PATH", str(env))
    monkeypatch.setattr(server, "schedule_restart", lambda: (_ for _ in ()).throw(AssertionError("yeniden baslamamali")))
    post = lambda body: requests.post(base + "/api/setup/keys", headers=H, json=body)
    assert post({}).status_code == 400                                              # bos
    assert post({"gemini": "kisa"}).status_code == 400                              # cok kisa
    assert post({"gemini": "bosluk iceren anahtar 1234567890"}).status_code == 400  # bosluk
    assert post({"gemini": "AIza\nINJECT=1_0123456789abcdef"}).status_code == 400   # satir enjeksiyonu
    monkeypatch.setattr(server, "validate_key", lambda prov, key: False)
    r = post({"gemini": KEY})
    assert r.status_code == 400 and "reddedildi" in r.json()["error"] and KEY not in r.text
    assert not env.exists()                                                          # hicbir durumda yazilmadi
    sid = new_sid(base)
    server.STATE[sid].busy = True
    try:
        assert post({"gemini": KEY}).status_code == 409                              # gorev calisirken yeniden baslatma yok
    finally:
        server.STATE[sid].busy = False


def test_server_starts_when_stdout_cannot_encode_turkish(tmp_path):
    """Turkce olmayan Windows'ta (cp1252) yonlendirilmis cikti 'ı' harfini kodlayamaz; sunucu yine de acilmali."""
    import subprocess
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "NODUS_PORT": str(port), "NODUS_NO_WINDOW": "1",
           "NODUS_NO_UPDATE_CHECK": "1", "NODUS_MEMORY_DIR": str(tmp_path / "mem")}
    env.pop("PYTHONUTF8", None)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = subprocess.Popen([sys.executable, "server.py"], cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        ok = False
        for _ in range(100):
            if p.poll() is not None:
                break
            try:
                ok = requests.get(f"http://127.0.0.1:{port}/api/ping", timeout=1).json().get("app") == "nodus"
            except Exception:
                ok = False
            if ok:
                break
            time.sleep(0.2)
        err = b"" if p.poll() is None else p.stderr.read()
        assert ok, err.decode("utf-8", "replace")[-600:]
    finally:
        p.terminate()
        try:
            p.wait(5)
        except Exception:
            p.kill()


def test_install_script_picks_highest_version_not_first_in_list(tmp_path):
    """GitHub release listesi surum sirasinda degildir (v1.1.1 en basta, v1.2 ikinci geldi); betik en buyugunu secmeli."""
    import shutil, subprocess
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash yok")
    tags = ["v1.1.1-beta", "v1.2-beta", "v1.1-beta", "v1.0-beta-macos", "v1.0-beta", "v1.10-beta", "v1.9", "notaversion"]
    f = tmp_path / "rel.json"
    f.write_text(json.dumps([{"tag_name": t, "draft": False} for t in tags]))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def pick(tag_list):
        f.write_text(json.dumps([{"tag_name": t} for t in tag_list]))
        env = {**os.environ, "NODUS_RELEASES_JSON_FILE": str(f), "NODUS_DRY_RUN": "1", "NODUS_HOME": str(tmp_path / "nope")}
        r = subprocess.run([bash, "install.sh"], cwd=root, env=env, capture_output=True, text=True, timeout=60)
        return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]
    assert pick(tags) == "REF=v1.10-beta"                                        # 1.10 > 1.9 (sayisal siralama)
    assert pick(["v1.1.1-beta", "v1.2-beta", "v1.1-beta"]) == "REF=v1.2-beta"
    assert pick(["v1.2-beta", "v1.2"]) == "REF=v1.2"                             # kararli, on-surumden buyuk
    assert pick(["v1.0-beta-macos", "v1.0-beta"]) == "REF=v1.0-beta"             # platforma ozel etiket atlanir


def test_system_prompt_tells_model_os_and_shell_access():
    from agent_core import NodusAgent
    p = NodusAgent()._build_system_prompt()
    assert "SISTEM ERISIMI" in p and "run_shell" in p and os.path.expanduser("~") in p
    assert "Mustafa Bacaksiz" in p and "mustafa.bcksz" in p and "mbmakes" in p


def test_window_opens_only_after_server_is_ready(monkeypatch):
    import server
    calls, state = [], {"n": 0}

    def fake_running(port):
        state["n"] += 1
        return state["n"] >= 3   # ilk iki yoklamada sunucu hazir degil

    monkeypatch.setattr(server, "_nodus_running", fake_running)
    monkeypatch.setattr(server, "open_window", lambda url: calls.append((url, state["n"])))
    server._open_when_ready("http://127.0.0.1:1", 1, timeout=10)
    assert calls == [("http://127.0.0.1:1", 3)]


def test_shrink_image_reduces_big_screenshots_and_keeps_small_ones():
    import io
    from PIL import Image
    from agent_core import shrink_image
    big = Image.effect_noise((3200, 2000), 40).convert("RGB")   # Retina ekran goruntusu boyutu, sikismaz gurultu
    buf = io.BytesIO(); big.save(buf, "PNG")
    data, mime = shrink_image(buf.getvalue(), "image/png")
    assert mime == "image/jpeg" and len(data) < len(buf.getvalue()) / 3
    assert max(Image.open(io.BytesIO(data)).size) == 2000
    tiny = io.BytesIO(); Image.new("RGB", (200, 100), "white").save(tiny, "PNG")
    assert shrink_image(tiny.getvalue(), "image/png") == (tiny.getvalue(), "image/png")
    assert shrink_image(b"bozuk", "image/png") == (b"bozuk", "image/png")


def test_vision_order_prefers_fast_flash_models():
    from agent_core import vision_order
    ranked = ["gemini-3-pro-preview", "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-2.5-flash"]
    assert vision_order(ranked) == ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3-pro-preview", "gemini-2.5-pro"]


def test_chat_steps_record_timings_in_ui(monkeypatch):
    """Sureler Terminal'e degil adim kaydina yazilir (kullanici Terminal'i gormuyor)."""
    import server
    events = []
    st = server.Status(lambda kind, **kw: events.append((kind, kw)))
    st.write("Görsel çözümleme: 4.2 sn (0.31 MB yüklendi, gemini-flash)")
    st.write("Çapraz doğrulama: 6.1 sn")
    notes = [x["note"] for x in st.saved_steps() if "note" in x]
    assert any("Görsel çözümleme: 4.2 sn" in n for n in notes) and any("Çapraz doğrulama" in n for n in notes)


def test_image_prompt_is_generic_and_images_do_not_force_heavy_model():
    import inspect
    from agent_core import NodusAgent
    src = inspect.getsource(NodusAgent.transcribe_engineering_image)
    assert "ekran goruntusuyse" in src and "arama veya uydurma" in src   # teknik cizim varsayimi yok
    heavy, score, reasons = NodusAgent().assess_complexity("Nodus ekran goruntusu\n--- [YUKLENEN GORSELIN ICERIGI (PERCEPTION)] ---\nbir sohbet penceresi")
    assert not heavy and score == 0 and "Teknik Cizim" not in reasons


def test_claim_without_tool_is_challenged_once(srv, monkeypatch):
    server, base = srv
    action = 'EYLEM_DETAYI:\n{"action": "list_files", "params": {}}'
    # 1) arac cagirmadan "ekledim" -> yonlendirilir; 2) arac calisir; 3) nihai cevap
    fake_model(server, monkeypatch, ["Uygulamayı Dock'a ekledim.", action, "Dosyaları listeledim, Dock'a ekleyemedim."])
    sid = new_sid(base)
    last = events(chat(base, sid, "dock'a ekle"))[-1]
    content = last["message"]["content"]
    assert "Dock'a ekledim." not in content and "ekleyemedim" in content
    assert any("hiçbir araç çalışmadı" in s.get("note", "") for s in last["message"]["steps"])


def test_claim_after_tool_is_accepted_without_extra_model_call(srv, monkeypatch):
    server, base = srv
    action = 'EYLEM_DETAYI:\n{"action": "list_files", "params": {}}'
    fake_model(server, monkeypatch, [action, "Dosyaları listeledim ve not ekledim."])   # 3. cagri olursa StopIteration -> test duser
    sid = new_sid(base)
    last = events(chat(base, sid, "listele"))[-1]
    assert "not ekledim" in last["message"]["content"]
    assert not any("hiçbir araç çalışmadı" in s.get("note", "") for s in last["message"]["steps"])
