# Nodus

**Mühendislik hesaplarını, dosya ve araştırma işlerini kendi başına yürüten, yerel çalışan otonom yapay zeka ajanı.**
*An autonomous, locally-run AI agent for engineering calculations, file work and research.*

> **Sürüm: v1.0-beta.** Günlük kullanıma yakın ama henüz geniş çapta denenmedi. Bilinen sınırlar için [Sınırlar](#sınırlar-ve-beta-notları) bölümüne bak.

![Hesap föyü: adım kaydı, denklem ve tablo](docs/img/hesap-foyu.png)

## Nodus ne yapar?

Bir görevi Türkçe yazarsın; Nodus planlar, doğru aracı seçer, hesabı yapar ve sonucu birimleriyle, denklem ve tablolarla sunar. Kod çalıştırma, dosya silme gibi riskli her adımda **önce senden onay ister**.

Örnek görevler:

- *"Çapı 50 mm, uzunluğu 100 m olan pürüzsüz borudan 20 °C suyla 5 L/s akarken basınç kaybını hesapla."*
- *"Boyu 2 m, 40×40 mm çelik kare profilli ankastre kirişin ucuna 500 N yük gelirse sehimi ve gerilmeyi bul."*
- *"Doymuş su buharının 1–10 bar arasındaki entalpi ve entropi tablosunu ver."*
- Bir Excel/PDF/Word/CSV yükle: *"Bu verideki trendi analiz et."*
- Bir teknik çizim görseli yükle: *"Şekildeki kirişin maksimum sehimini hesapla."*

## Öne çıkanlar

| | |
|---|---|
| **Hazır, doğrulanmış hesaplar** | Boru basınç kaybı (Darcy-Weisbach + Colebrook-White), kiriş sehimi ve gerilmesi, doymuş buhar tablosu. Model formülü kafasından yazmaz; `eng_calc` aracı ile birim testli fonksiyonları çağırır. |
| **Çoklu model yönlendirici** | Gemini, Groq ve OpenRouter arasında görev türüne göre seçim yapar; kota dolunca ya da sağlayıcı yanıt vermezse otomatik yedeğe geçer. |
| **Çapraz doğrulama** | Ağır görevlerde cevap, farklı bir sağlayıcının modeline denetlettirilir. Model itiraz ederse hesap, itiraz notuyla bir kez yeniden yaptırılır. |
| **Onay kapısı** | Kod çalıştırma, kabuk komutu, dosya silme, kalıcı hafıza yazımı onay ister. Onay ekranında *gerçekte çalışacak* kod (başvurulan dosyalar dahil) gösterilir. |
| **Durdur düğmesi** | Çalışan görevi her an durdurur; çalışan kod/komut süreci de öldürülür. |
| **Adım kaydı** | Her görevin araç adımları ve süreleri sohbetle birlikte kaydedilir. |
| **Rapor** | Cevabı tek tıkla Word (.docx) veya PDF rapora dönüştürür (şekiller gömülü). |
| **Dosya ve görsel girişi** | Sürükle-bırak, yapıştırma ya da düğme ile; PDF, Excel, Word, CSV, PNG/JPG. Sesli komut (Groq anahtarı varsa). |
| **Yerel ve gizli** | Arayüz yalnızca `127.0.0.1`'de çalışır. Sohbetler ve notlar diskinde kalır. |
| **Açık/koyu tema** | Mühendislik çizim kâğıdı (mavi kopya) esinli, tam ekran arayüz; telefon ve tablete uyumlu. |

![Görev çalışırken: durdur düğmesi](docs/img/calisiyor-durdur.png)

## Kurulum

Gereksinimler: **Windows**, **Python 3.12**, en az bir sağlayıcı anahtarı (ücretsiz katmanlar yeterli).

```bash
git clone https://github.com/mbmakes/nodus.git
cd nodus
copy .env.example .env      # ardından .env içine anahtarlarını yaz
run_nodus.bat
```

`run_nodus.bat` eksik kütüphaneleri otomatik kurar, sunucuyu başlatır ve arayüzü Edge/Chrome'da uygulama penceresi olarak açar (`http://127.0.0.1:8765`).

Anahtarlar (`.env`) — en az biri gerekli:

| Değişken | Nereden |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio |
| `GROQ_API_KEY` | console.groq.com (sesli komut için de gerekir) |
| `OPENROUTER_API_KEY` | openrouter.ai |

İsteğe bağlı ortam değişkenleri: `NODUS_PORT` (varsayılan 8765), `NODUS_NO_WINDOW=1` (pencere açma), `NODUS_WORKSPACE` (çalışma alanı klasörü), `NODUS_MEMORY_DIR` (bellek klasörü), `NODUS_SANDBOX=docker` (kodu Docker içinde çalıştır).

Komut satırı: `python main.py "görev metni"` · Eski Streamlit arayüzü: `run_nodus_classic.bat`.

## Nasıl çalışır?

```
Tarayıcı (web/)  ──SSE──►  server.py (Starlette)
                              │
                       orchestrator.py   ReAct döngüsü, onay politikası, iptal
                              │
              ┌───────────────┼────────────────┐
         agent_core.py    providers.py       tools.py
         sistem istemi    model yönlendirici  araç kayıt defteri,
         araç çağrıları   kota/sağlık         workspace kafesi, sandbox
                                                  │
                                              engcalc.py  doğrulanmış hesaplar
```

- **ReAct döngüsü:** model bir araç çağırır, sonucu görür, devam eder; en fazla 12 adım. Aynı eylem 3 kez tekrarlanırsa döngü kesilir.
- **Araçlar:** `eng_calc`, `execute_code`, `solve_math`, `web_search`, `fetch_url`, `browse_url`, `read_document`, `read_file`/`write_file`/`apply_patch`, `export_report`, `update_plan`, `remember`/`recall` ve dahası.
- **Hafıza:** kalıcı kurallar ("SI birim sistemi kullan"), notlar (SQLite) ve sohbet geçmişi yerel `memory/` klasöründe.

![Başlangıç ekranı ve şablonlar](docs/img/baslangic.png)

## Güvenlik modeli

- **Workspace kafesi:** Tüm dosya işlemleri çalışma alanında kalır; `..`, sembolik link ve mutlak yol kaçışları reddedilir.
- **Onay politikası:** Kod/komut çalıştırma ve silme her zaman onay ister. İnternetten ya da belgeden içerik okunduktan sonra, "otomatik çalıştır" açık olsa bile onay istenir (prompt injection riskine karşı).
- **Yerel sunucu:** Yalnızca `127.0.0.1`/`localhost` Host başlığı, değiştirici isteklerde özel başlık + aynı origin, sıkı CSP. SVG/HTML hiçbir zaman satır içi sunulmaz.
- **Alt süreçler** API anahtarları olmadan, çalışma alanı içinde, zaman aşımıyla çalışır.

> ⚠️ **Docker sandbox kapalıyken** onaylanan kod senin makinende, kullanıcı hesabının yetkileriyle çalışır. Kodu okumadan onaylama. Güçlü izolasyon için Docker kur ve `.env`'e `NODUS_SANDBOX=docker` ekle (`sandbox/Dockerfile`).

## Testler

```bash
python -m pytest tests -q -p no:cacheprovider      # 48 test
```

Ajan/araç davranışı, güvenlik politikası, sunucu uçları (gerçek uvicorn + sahte model), durdurma ve süreç öldürme, rapor, arama ve hesap doğrulukları kapsanır.

## Sınırlar ve beta notları

- Yalnızca **Windows** üzerinde denendi.
- Kod/komut çalıştırma, Docker kurulmadıkça işletim sistemi düzeyinde izole değildir.
- Model hesapları hatalı olabilir; hazır hesaplar (`eng_calc`) ve çapraz doğrulama bunu azaltır ama ortadan kaldırmaz. Sonuçları kritik işlerde bağımsız doğrula.
- Ücretsiz sağlayıcı katmanlarında kota dolabilir; Nodus yedeğe geçer ama yanıt süresi uzayabilir.
- Sesli komut Groq'a ses gönderir.
- Henüz CI yok; testler elle çalıştırılır.

## Yol haritası

- Daha fazla doğrulanmış hesap (ısı transferi, pompa/fan seçimi, mil ve cıvata hesapları)
- Docker sandbox'ı varsayılan yapma ve kurulum sihirbazı
- Cevap içi grafikler için etkileşimli önizleme
- macOS/Linux başlatıcıları
- CI (GitHub Actions)

## Lisans

[MIT](LICENSE) © 2026 mbmakes
