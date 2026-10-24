# Nodus: uygun Python yoksa tasinabilir Python 3.12 kurar (uv ile, .nodus_tools\ ve .venv\ icine; yonetici izni gerekmez).
# run_nodus.bat tarafindan cagrilir. Cikis: 0 = .venv\Scripts\python.exe hazir.
# Ortam: NODUS_YES=1 (soru sorma). Dosya yalnizca ASCII: Windows PowerShell 5.1 BOM'suz UTF-8'i bozar.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host 'Python 3.12 bulunamadi (ya da surumu uygun degil).'
Write-Host 'Nodus klasorune (.nodus_tools ve .venv) tasinabilir bir Python 3.12 kurulacak (~60 MB).'
Write-Host 'Yonetici izni gerekmez, sistemine dokunulmaz; klasoru silince hepsi gider.'
if (-not $env:NODUS_YES -and [Environment]::UserInteractive) {
    $ans = Read-Host 'Devam edilsin mi? [E/h]'
    if ($ans -match '^[hHnN]') { Write-Host 'Iptal edildi.'; exit 1 }
}

$arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'aarch64' } else { 'x86_64' }
$url = "https://github.com/astral-sh/uv/releases/latest/download/uv-$arch-pc-windows-msvc.zip"
$tools = Join-Path $root '.nodus_tools'
New-Item -ItemType Directory -Force $tools | Out-Null
$zip = Join-Path $tools 'uv.zip'
$shaFile = Join-Path $tools 'uv.zip.sha256'

Write-Host '[0/2] Python kurulum araci (uv) indiriliyor...'
try {
    Invoke-WebRequest $url -OutFile $zip -UseBasicParsing
    Invoke-WebRequest "$url.sha256" -OutFile $shaFile -UseBasicParsing
} catch { Write-Host ('[HATA] uv indirilemedi (internet?): ' + $_.Exception.Message); exit 1 }
$want = ((Get-Content $shaFile -Raw) -split '\s+')[0].Trim().ToLower()
$got = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
Remove-Item $shaFile -Force -ErrorAction SilentlyContinue
if (-not $want -or $want -ne $got) {
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    Write-Host '[HATA] Indirilen dosyanin ozeti uyusmuyor; guvenlik icin durduruldu.'
    exit 1
}
Expand-Archive $zip -DestinationPath $tools -Force
Remove-Item $zip -Force
$uv = Get-ChildItem $tools -Recurse -Filter uv.exe | Select-Object -First 1
if (-not $uv) { Write-Host '[HATA] uv acilamadi.'; exit 1 }

$env:UV_PYTHON_INSTALL_DIR = Join-Path $tools 'python'
$env:UV_CACHE_DIR = Join-Path $tools 'cache'
Write-Host '[0/2] Python 3.12 indiriliyor ve sanal ortam hazirlaniyor...'
$venv = Join-Path $root '.venv'
if (Test-Path $venv) { Remove-Item $venv -Recurse -Force }
& $uv.FullName venv --python 3.12 --seed $venv
if ($LASTEXITCODE -ne 0) { Write-Host '[HATA] Python 3.12 kurulamadi.'; exit 1 }
exit 0
