# -*- coding: utf-8 -*-
"""tools.browse_url tarafindan AYRI SUREC olarak calistirilir:  browse_worker.py <url> <text|screenshot> <png_yolu>
Her ag istegi (yonlendirmeler ve alt kaynaklar dahil) ozel/yerel adreslere karsi denetlenir."""
import sys
import socket
import ipaddress
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright


def is_public(url: str) -> bool:
    u = urlparse(url)
    if u.scheme in ("data", "blob", "about"):
        return True
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    try:
        for info in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80)):
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
            if ip.version == 6 and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            if not ip.is_global:
                return False
    except Exception:
        return False
    return True


def main():
    url, mode, shot = sys.argv[1:4]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800}, accept_downloads=False, service_workers="block",
            user_agent="NodusBot/1.0 (yerel arastirma asistani)",
        )
        page = ctx.new_page()
        page.route("**/*", lambda route: route.continue_() if is_public(route.request.url) else route.abort())
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)   # JS ile gelen icerik icin kisa bekleme
        if mode == "screenshot":
            page.screenshot(path=shot)
        else:
            print("Baslik:", page.title())
            print()
            print(page.inner_text("body")[:30000])
        browser.close()


if __name__ == "__main__":
    main()
