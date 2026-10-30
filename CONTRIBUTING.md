# Contributing / Katkı

**English** · [Türkçe aşağıda](#türkçe)

Thanks for looking at Nodus. Bug reports, ideas and pull requests are all welcome.

## Reporting a bug

Open an issue with the *Bug report* form. The three things that help most: your OS, the Nodus version (Settings → Version) and what you did right before it broke. For anything that touches security, please read [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Running it from source

```bash
git clone https://github.com/mbmakes/Nodus.git
cd Nodus
python -m pip install -r requirements.txt     # Python 3.12 or 3.13
python -m pytest tests -q -p no:cacheprovider # should be all green
python server.py                               # http://127.0.0.1:8765
```

You need at least one free provider key to talk to a model (see the README), but the whole test suite runs with a fake model and does not need any.

## Pull requests

- Keep a change focused; one fix or one feature per pull request.
- Add or update a test. Calculations in `engcalc.py` should be checked against a hand calculation (see `tests/test_engcalc.py`).
- Run the full test suite before you push. CI runs it on Windows, macOS and Linux.
- Match the surrounding code style. Source comments are in Turkish, the README is bilingual; either language is fine in a PR description.
- Two files must keep their line endings: `*.sh` and `*.command` use LF, `*.bat` and `*.ps1` use CRLF (`.gitattributes` enforces it). PowerShell scripts must stay ASCII-only.

---

## Türkçe

Nodus'a baktığın için teşekkürler. Hata bildirimi, fikir ve pull request'lerin hepsi memnuniyetle karşılanır.

**Hata bildirimi:** *Bug report* formuyla issue aç. En çok işe yarayan üç bilgi: işletim sistemin, Nodus sürümü (Ayarlar → Sürüm) ve bozulmadan hemen önce ne yaptığın. Güvenlikle ilgili bir şeyse herkese açık issue yerine [SECURITY.md](SECURITY.md) dosyasını oku.

**Kaynaktan çalıştırma:** yukarıdaki komutlar aynı. Bir modelle konuşmak için en az bir ücretsiz sağlayıcı anahtarı gerekir (README'ye bak); ama test paketi sahte modelle çalışır, anahtar istemez.

**Pull request kuralları:** değişiklik odaklı olsun (bir düzeltme ya da bir özellik); test ekle ya da güncelle (`engcalc.py` hesapları elle hesapla doğrulanmalı); göndermeden önce tüm testleri çalıştır; çevredeki kod stiline uy. `*.sh`/`*.command` dosyaları LF, `*.bat`/`*.ps1` dosyaları CRLF kalmalı, PowerShell betikleri yalnızca ASCII olmalı.
