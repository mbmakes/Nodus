# Security policy / Güvenlik politikası

**English** · [Türkçe aşağıda](#türkçe)

Nodus runs code and shell commands on your computer after you approve them, so security reports are taken seriously.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private reporting instead: open the repository's **Security** tab and choose **Report a vulnerability**. Include what you found, how to reproduce it and which version you used. You will get an answer as soon as I can manage; this is a one-person project, so please be patient.

## What counts

Examples of things I want to hear about: a way around the approval gate, reading or writing files the policy says are off-limits (for example Nodus's own `.env`), the local server accepting requests from another website, or the updater accepting an unsafe archive.

## Known and accepted limits

These are documented in the README and are not treated as vulnerabilities by themselves:

- Code or a command you **approve** runs with your user account's rights unless you set up the Docker sandbox.
- The update archive has no digital signature; trust rests on GitHub's HTTPS and this repository.
- If you switch on "Run code without approval", code runs without asking (except after web content was read).

## Supported versions

Only the latest release receives fixes. The in-app updater (Settings → Version) installs it.

---

## Türkçe

Nodus, sen onaylayınca bilgisayarında kod ve kabuk komutu çalıştırır; bu yüzden güvenlik bildirimlerini ciddiye alıyorum.

**Açık bildirmek için** herkese açık issue **açma**. Depodaki **Security** sekmesinden **Report a vulnerability** ile özel bildirim gönder. Neyi bulduğunu, nasıl yeniden üretilebileceğini ve hangi sürümü kullandığını yaz. Tek kişilik bir proje olduğu için yanıt biraz zaman alabilir.

**Duymak istediklerim:** onay kapısını aşan bir yol, politikanın yasakladığı dosyaları (örneğin Nodus'un kendi `.env`'i) okuma/yazma, yerel sunucunun başka bir siteden istek kabul etmesi, güncelleyicinin güvensiz arşiv kabul etmesi.

**Bilinen ve kabul edilen sınırlar** README'de yazıyor: onayladığın kod Docker sandbox yoksa kullanıcı yetkileriyle çalışır; güncelleme arşivinin dijital imzası yok; "Kodu onaysız çalıştır" açıksa kod sormadan çalışır.

**Desteklenen sürüm:** yalnızca son sürüm düzeltme alır.
