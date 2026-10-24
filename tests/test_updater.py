# -*- coding: utf-8 -*-
"""updater.py: surum karsilastirma, zip uygulama (korumali klasorler, zip-slip, geri alma) ve git yolu. Hepsi gecici klasorlerde."""
import os
import subprocess
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import updater
from updater import UpdateError


def make_zip(path, files, top="mbmakes-Nodus-abc123"):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(f"{top}/{name}" if top else name, data)
    return str(path)


def test_version_ordering():
    n = updater.is_newer
    assert n("v1.1-beta", "1.0-beta") and n("1.0", "1.0-beta") and n("1.1-beta.2", "1.1-beta")
    assert n("1.1-rc", "1.1-beta") and n("1.10", "1.9") and n("2.0-alpha", "1.9")
    assert not n("1.0-beta", "1.0-beta") and not n("1.0-beta", "1.0") and not n("garbage", "1.0")
    assert updater.parse_version("nonsense!") is None


def test_pick_release_skips_drafts_and_platform_tags():
    rels = [{"tag_name": "v1.0-beta", "draft": False}, {"tag_name": "v1.0-beta-macos", "draft": False},
            {"tag_name": "v1.2-beta", "draft": True}, {"tag_name": "v1.1-beta", "draft": False}, {"tag_name": "notaversion"}]
    assert updater.pick_release(rels)["tag_name"] == "v1.1-beta"
    assert updater.pick_release([]) is None


def test_check_builds_info(monkeypatch):
    class R:
        def raise_for_status(self): pass
        def json(self): return [{"tag_name": "v1.1-beta", "name": "Nodus v1.1-beta", "body": "x" * 30000,
                                  "html_url": "u", "zipball_url": "z", "published_at": "t"}]
    monkeypatch.setattr(updater.requests, "get", lambda *a, **k: R())
    info = updater.check("1.0-beta")
    assert info["available"] and info["latest"]["version"] == "1.1-beta" and len(info["latest"]["notes"]) == 20000
    assert not updater.check("1.1-beta")["available"] and not updater.check("2.0")["available"]


def test_download_rejects_foreign_hosts(tmp_path):
    for url in ("http://evil.example/x.zip", "https://evil.example/x.zip", "http://api.github.com/x"):
        with pytest.raises(UpdateError):
            updater.download_zip(url, str(tmp_path / "x.zip"))


def test_apply_zip_updates_code_but_keeps_user_data(tmp_path):
    target = tmp_path / "install"
    (target / "memory").mkdir(parents=True)
    (target / "server.py").write_text("eski")
    (target / ".env").write_text("GEMINI_API_KEY=gizli")
    (target / "memory" / "kalici.json").write_text("benim verim")
    z = make_zip(tmp_path / "u.zip", {"version.py": "yeni", "server.py": "yeni sunucu", "web/app.js": "js",
                                       ".env": "ESKIYI_EZMEMELI", "memory/kalici.json": "EZMEMELI", "custom_tools/x.py": "EZMEMELI",
                                       "run_nodus.sh": "#!/bin/sh\n"})
    res = updater.apply_zip(z, str(target))
    assert (target / "server.py").read_text() == "yeni sunucu" and (target / "web" / "app.js").read_text() == "js"
    assert (target / ".env").read_text() == "GEMINI_API_KEY=gizli"
    assert (target / "memory" / "kalici.json").read_text() == "benim verim" and not (target / "custom_tools").exists()
    assert res["files"] == 4
    assert open(os.path.join(res["backup"], "server.py")).read() == "eski"
    assert not [p for p in target.rglob("*.nodus-new")]
    if os.name != "nt":
        assert os.access(target / "run_nodus.sh", os.X_OK)


def test_apply_zip_rejects_path_traversal(tmp_path):
    target = tmp_path / "install"
    target.mkdir()
    for bad in ("../evil.txt", "web/../../evil.txt", "/abs.txt", "C:/evil.txt"):
        z = make_zip(tmp_path / "bad.zip", {"version.py": "v", bad: "x"})
        with pytest.raises(UpdateError):
            updater.apply_zip(z, str(target))
    assert not (tmp_path / "evil.txt").exists() and not (target / "version.py").exists()   # dogrulama yazmadan once


def test_apply_zip_rejects_non_nodus_and_non_zip(tmp_path):
    target = tmp_path / "install"
    target.mkdir()
    with pytest.raises(UpdateError):
        updater.apply_zip(make_zip(tmp_path / "a.zip", {"readme.txt": "x"}), str(target))
    (tmp_path / "b.zip").write_text("zip degil")
    with pytest.raises(UpdateError):
        updater.apply_zip(str(tmp_path / "b.zip"), str(target))


def test_apply_zip_rolls_back_on_failure(tmp_path):
    target = tmp_path / "install"
    (target / "b.txt").mkdir(parents=True)          # b.txt yolu bir klasor: yazma ortada patlar
    (target / "a.py").write_text("eski a")
    z = make_zip(tmp_path / "u.zip", {"a.py": "yeni a", "b.txt": "x", "version.py": "v"})
    with pytest.raises(Exception):
        updater.apply_zip(z, str(target))
    assert (target / "a.py").read_text() == "eski a"       # geri alindi
    assert not (target / "version.py").exists() and not list(target.rglob("*.nodus-new"))


def _git(cwd, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout.strip()


def test_git_update_fast_forwards_to_tag_and_refuses_dirty_tree(tmp_path):
    origin, a, b = tmp_path / "origin.git", tmp_path / "a", tmp_path / "b"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", str(origin), str(a))
    (a / "version.py").write_text('__version__ = "1.0"\n')
    _git(a, "add", "."); _git(a, "commit", "-m", "v1"); _git(a, "push", "-u", "origin", "HEAD:main")
    _git(tmp_path, "clone", str(origin), str(b))
    (b / "version.py").write_text('__version__ = "1.1"\n')
    _git(b, "commit", "-am", "v1.1"); _git(b, "tag", "v1.1"); _git(b, "push", "origin", "HEAD:main", "--tags")
    (a / "version.py").write_text("elle degistirildi")                 # kirli agac
    with pytest.raises(UpdateError, match="yerel degisiklik"):
        updater.git_update("v1.1", str(a))
    _git(a, "checkout", "--", "version.py")
    updater.git_update("v1.1", str(a))
    assert (a / "version.py").read_text() == '__version__ = "1.1"\n'
    with pytest.raises(UpdateError):
        updater.git_update("--upload-pack=evil", str(a))               # secenek enjeksiyonu
    assert updater.install_mode(str(a)) == "git" and updater.install_mode(str(tmp_path)) == "zip"
