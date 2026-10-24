# -*- coding: utf-8 -*-
"""Uygulama ici guncelleme: GitHub release'lerini denetler, yeni surumu indirip uygular (git ya da zip),
uygulanan dosyalari yedekler ve hata olursa geri alir. Kullanici verisine (.env, memory/, workspace/ ...) dokunmaz."""
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from urllib.parse import urlparse

import requests

REPO = "mbmakes/Nodus"
API_BASE = "https://api.github.com"
ALLOWED_HOSTS = {"api.github.com", "codeload.github.com"}
MAX_ZIP = 80 * 1024 * 1024
MAX_FILE = 50 * 1024 * 1024
MAX_FILES = 5000
KEEP_BACKUPS = 2
# Guncelleme bunlarin uzerine yazmaz (kullanici verisi ve yerel kurulum)
PROTECTED = (".env", "memory/", "workspace/", "allowed_workspace/", "custom_tools/", "core_vault/",
             ".venv/", ".nodus_tools/", ".update_backup/", ".git/")
PLATFORM_TAG_WORDS = ("macos", "windows", "linux")   # eski, platforma ozel etiketler (v1.0-beta-macos) surum sayilmaz
HEADERS = {"User-Agent": "Nodus-updater", "Accept": "application/vnd.github+json"}


class UpdateError(Exception):
    """Kullaniciya gosterilebilecek, anlasilir guncelleme hatasi."""


# ------------------------------------------------------------------ surum karsilastirma
_VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+)*)(?:[-+.]?([0-9A-Za-z.\-]+))?$")


def parse_version(s):
    """'v1.2.0-beta.2' -> siralanabilir anahtar. Onek yoksa (kararli) onekli surumden buyuktur."""
    m = _VERSION_RE.match(str(s or "").strip())
    if not m:
        return None
    nums = tuple(int(x) for x in m.group(1).split("."))
    nums += (0,) * (4 - len(nums))
    pre = m.group(2)
    if not pre:
        return (nums, 1, ())
    toks = tuple((0, int(t), "") if t.isdigit() else (1, 0, t.lower()) for t in re.split(r"[.\-]", pre) if t)
    return (nums, 0, toks)


def is_newer(candidate, current) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    return a is not None and b is not None and a > b


def pick_release(releases: list):
    """GitHub release listesinden en yeni (on-surum dahil) gecerli surumu secer."""
    best, best_key = None, None
    for r in releases or []:
        tag = str(r.get("tag_name", ""))
        key = parse_version(tag)
        if r.get("draft") or key is None or any(w in tag.lower() for w in PLATFORM_TAG_WORDS):
            continue
        if best_key is None or key > best_key:
            best, best_key = r, key
    return best


# ------------------------------------------------------------------ denetleme / indirme
def _allowed(url: str) -> bool:
    u = urlparse(url)
    override = os.getenv("NODUS_UPDATE_API")   # yalnizca yerel test sunucusu icin
    if override and u.hostname == urlparse(override).hostname:
        return True
    return u.scheme == "https" and u.hostname in ALLOWED_HOSTS


def check(current: str, timeout: int = 10) -> dict:
    """{'current', 'available', 'latest': {...} | None}. Ag hatasinda istisna firlatir."""
    base = os.getenv("NODUS_UPDATE_API") or API_BASE
    r = requests.get(f"{base}/repos/{REPO}/releases", params={"per_page": 30}, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    rel = pick_release(r.json())
    info = {"current": current, "available": False, "latest": None}
    if rel:
        tag = str(rel["tag_name"])
        info["latest"] = {
            "tag": tag, "version": tag[1:] if tag[:1] in "vV" else tag, "name": rel.get("name") or tag,
            "notes": (rel.get("body") or "")[:20000], "url": rel.get("html_url"),
            "published": rel.get("published_at"), "zipball": rel.get("zipball_url"),
        }
        info["available"] = is_newer(tag, current)
    return info


def download_zip(url: str, dest: str, timeout: int = 60):
    """Yonlendirmeleri tek tek dogrulayarak (yalniz GitHub ana makineleri) boyut sinirli indirir."""
    for _ in range(4):
        if not _allowed(url):
            raise UpdateError("Izin verilmeyen indirme adresi.")
        r = requests.get(url, headers=HEADERS, stream=True, allow_redirects=False, timeout=timeout)
        if r.status_code in (301, 302, 303, 307, 308):
            url = r.headers.get("Location", "")
            r.close()
            continue
        r.raise_for_status()
        break
    else:
        raise UpdateError("Cok fazla yonlendirme.")
    size = 0
    with open(dest, "wb") as f:
        for chunk in r.iter_content(65536):
            size += len(chunk)
            if size > MAX_ZIP:
                raise UpdateError("Indirilen dosya beklenenden cok buyuk.")
            f.write(chunk)


# ------------------------------------------------------------------ uygulama
def _protected(rel: str) -> bool:
    return any(rel == p or (p.endswith("/") and rel.startswith(p)) for p in PROTECTED)


def apply_zip(zip_path: str, target: str) -> dict:
    """Arsivdeki dosyalari target'a yazar. Once hepsini dogrular, yazarken yedekler, hata olursa geri alir."""
    target = os.path.realpath(target)
    plan = []
    try:
        z = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise UpdateError("Indirilen dosya gecerli bir zip degil.")
    with z:
        infos = z.infolist()
        if len(infos) > MAX_FILES:
            raise UpdateError("Arsivde beklenenden cok dosya var.")
        for info in infos:
            if info.is_dir():
                continue
            parts = info.filename.replace("\\", "/").split("/")[1:]   # ilk bilesen: sahip-depo-sha klasoru
            if not parts or not parts[-1]:
                continue
            rel = "/".join(parts)
            if (rel.startswith("/") or ".." in parts or "" in parts or ":" in parts[0]
                    or (info.external_attr >> 16) & 0o170000 == 0o120000 or info.file_size > MAX_FILE):
                raise UpdateError(f"Guvensiz arsiv ogesi: {info.filename}")
            if _protected(rel):
                continue
            dest = os.path.realpath(os.path.join(target, *parts))
            if os.path.commonpath([dest, target]) != target:
                raise UpdateError(f"Guvensiz arsiv yolu: {info.filename}")
            plan.append((info, rel, dest))
        if not any(rel == "version.py" for _, rel, _ in plan):
            raise UpdateError("Arsiv Nodus'a benzemiyor (version.py yok); guncelleme iptal edildi.")

        backup = os.path.join(target, ".update_backup", time.strftime("%Y%m%d-%H%M%S"))
        backed, created = [], []
        try:
            for info, rel, dest in plan:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if os.path.isfile(dest):
                    b = os.path.join(backup, *rel.split("/"))
                    os.makedirs(os.path.dirname(b), exist_ok=True)
                    shutil.copy2(dest, b)
                    backed.append((dest, b))
                else:
                    created.append(dest)
                tmp = dest + ".nodus-new"
                with open(tmp, "wb") as f:
                    f.write(z.read(info))
                os.replace(tmp, dest)
                mode = (info.external_attr >> 16) & 0o777
                if os.name != "nt":
                    if rel.endswith((".sh", ".command")):
                        mode |= 0o755
                    if mode:
                        os.chmod(dest, mode | 0o600)
        except Exception:
            for dest, b in backed:
                shutil.copy2(b, dest)
            for dest in created:
                try:
                    os.remove(dest)
                except OSError:
                    pass
            for info, rel, dest in plan:
                try:
                    os.remove(dest + ".nodus-new")
                except OSError:
                    pass
            raise
    root = os.path.join(target, ".update_backup")
    for old in sorted(os.listdir(root) if os.path.isdir(root) else [])[:-KEEP_BACKUPS]:
        shutil.rmtree(os.path.join(root, old), ignore_errors=True)
    return {"files": len(plan), "backup": backup}


_TAG_RE = re.compile(r"^v?\d[\w.\-]*$")


def git_update(tag: str, target: str):
    """Git ile kurulu surumu etikete ilerletir (yalniz fast-forward). Yerel degisiklik varsa dokunmaz."""
    if not _TAG_RE.match(tag):
        raise UpdateError("Gecersiz surum etiketi.")

    def git(*args):
        return subprocess.run(["git", "-C", target, *args], capture_output=True, text=True, timeout=180)

    if git("status", "--porcelain", "--untracked-files=no").stdout.strip():
        raise UpdateError("Dosyalarda yerel degisiklik var; once commit et ya da `git stash` yap, sonra yeniden dene.")
    f = git("fetch", "--force", "origin", f"refs/tags/{tag}:refs/tags/{tag}")
    if f.returncode:
        raise UpdateError("Git surumu indiremedi: " + (f.stderr.strip().splitlines() or ["bilinmeyen hata"])[-1])
    m = git("merge", "--ff-only", f"refs/tags/{tag}^{{commit}}")
    if m.returncode:
        raise UpdateError("Gecmis dallanmis, otomatik ilerletilemedi. Elle: git fetch --tags && git reset --hard " + tag)


def install_mode(target: str) -> str:
    return "git" if os.path.isdir(os.path.join(target, ".git")) and shutil.which("git") else "zip"


def install_requirements(target: str):
    """(basarili_mi, son_satir). Kutuphane kurulumu basarisiz olsa da uygulama dosyalari yerinde kalir."""
    req = os.path.join(target, "requirements.txt")
    if not os.path.isfile(req):
        return True, ""
    try:
        p = subprocess.run([sys.executable, "-m", "pip", "install", "-r", req, "--quiet", "--disable-pip-version-check"],
                           capture_output=True, text=True, timeout=900, cwd=target)
    except subprocess.TimeoutExpired:
        return False, "pip zaman asimina ugradi"
    return p.returncode == 0, ((p.stderr or p.stdout).strip().splitlines() or [""])[-1]
