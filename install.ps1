# Nodus tek satirlik kurulum (Windows PowerShell):
#   irm https://raw.githubusercontent.com/mbmakes/Nodus/master/install.ps1 | iex
# Son surumu %USERPROFILE%\Nodus klasorune indirir ve baslatir.
# Ortam: NODUS_HOME (hedef klasor), NODUS_ARCHIVE_REF (belirli etiket/dal/commit; test icin). Dosya yalnizca ASCII (PowerShell 5.1).
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$repo = 'mbmakes/Nodus'
$dest = if ($env:NODUS_HOME) { $env:NODUS_HOME } else { Join-Path $env:USERPROFILE 'Nodus' }

Write-Host '==================================================='
Write-Host '                 NODUS KURULUYOR'
Write-Host '==================================================='

if (Test-Path (Join-Path $dest 'version.py')) {
    Write-Host "Nodus zaten kurulu: $dest  (guncellemeler uygulamanin icinden gelir)"
} else {
    $ref = $env:NODUS_ARCHIVE_REF
    if (-not $ref) {
        # GitHub liste sirasi surum sirasi DEGIL: en buyuk surum numarasini kendimiz seciyoruz (kararli > on-surum);
        # eski platforma ozel etiketler (-macos vb.) atlanir
        function Get-VerKey($tag) {
            $parts = ($tag -replace '^v', '') -split '[.-]'
            $nums = @(); $i = 0
            while ($i -lt $parts.Count -and $parts[$i] -match '^\d+$' -and $nums.Count -lt 4) { $nums += [int]$parts[$i]; $i++ }
            while ($nums.Count -lt 4) { $nums += 0 }
            $stable = if ($i -ge $parts.Count) { 1 } else { 0 }
            return (($nums | ForEach-Object { '{0:D5}' -f $_ }) -join '') + $stable
        }
        $rel = Invoke-RestMethod "https://api.github.com/repos/$repo/releases?per_page=30" -Headers @{ 'User-Agent' = 'Nodus-installer' }
        $ref = ($rel | Where-Object { -not $_.draft -and $_.tag_name -match '^v?\d' -and $_.tag_name -notmatch '-(macos|windows|linux)$' } |
            Sort-Object { Get-VerKey $_.tag_name } -Descending | Select-Object -First 1).tag_name
        if (-not $ref) { throw 'Surum bilgisi alinamadi (internet baglantisini kontrol et).' }
        if ($env:NODUS_DRY_RUN) { Write-Host "REF=$ref"; return }
    }
    Write-Host "Surum indiriliyor: $ref"
    $tmp = Join-Path $env:TEMP ('nodus_' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory $tmp | Out-Null
    $zip = Join-Path $tmp 'nodus.zip'
    try { Invoke-WebRequest "https://github.com/$repo/archive/$ref.zip" -OutFile $zip -UseBasicParsing }
    catch { Invoke-WebRequest "https://github.com/$repo/archive/refs/tags/$ref.zip" -OutFile $zip -UseBasicParsing }
    Expand-Archive $zip -DestinationPath (Join-Path $tmp 'x')
    $src = Get-ChildItem (Join-Path $tmp 'x') -Directory | Select-Object -First 1
    if (-not $src -or -not (Test-Path (Join-Path $src.FullName 'version.py'))) { throw 'Arsiv beklenen icerikte degil.' }
    New-Item -ItemType Directory -Force (Split-Path $dest -Parent) | Out-Null
    Move-Item $src.FullName $dest
    Remove-Item $tmp -Recurse -Force
    Write-Host "Kuruldu: $dest"
}

# Masaustu kisayolu (yoksa olusturur; basarisiz olursa kurulumu engellemez)
try {
    $lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Nodus.lnk'
    if (-not (Test-Path $lnk)) {
        $sc = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
        $sc.TargetPath = Join-Path $dest 'run_nodus.bat'
        $sc.WorkingDirectory = $dest
        $sc.IconLocation = Join-Path $dest 'assets\Nodus.ico'
        $sc.WindowStyle = 7
        $sc.Description = 'Nodus'
        $sc.Save()
        Write-Host 'Masaustune Nodus kisayolu eklendi.'
    }
} catch { Write-Host "Kisayol olusturulamadi: $($_.Exception.Message)" }

Set-Location $dest
& cmd.exe /c ".\run_nodus.bat"
