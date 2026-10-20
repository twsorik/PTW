# Сборка PTW: dist\PTW\PTW.exe и установщик dist\PTW-Setup-<версия>.exe
# внешние программы пишут прогресс в stderr — ошибки проверяем по $LASTEXITCODE
$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
Set-Location $root

# движок mpv (в git не хранится — больше 100 МБ)
$dll = Join-Path $root "assets\libmpv-2.dll"
if (-not (Test-Path $dll)) {
    Write-Host "Скачиваю libmpv..."
    $rel = Invoke-RestMethod -ErrorAction Stop "https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest"
    $asset = $rel.assets | Where-Object { $_.name -like "mpv-dev-x86_64-2*.7z" } | Select-Object -First 1
    $tmp = Join-Path $env:TEMP "ptw-libmpv"
    New-Item -ItemType Directory -Force $tmp | Out-Null
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -ErrorAction Stop $asset.browser_download_url -OutFile "$tmp\mpv-dev.7z"
    & "$env:SystemRoot\System32\tar.exe" -xf "$tmp\mpv-dev.7z" -C $tmp libmpv-2.dll
    Move-Item "$tmp\libmpv-2.dll" $dll
}

$version = (Select-String -Path "src\version.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "Сборка PTW $version"

python -m PyInstaller --noconfirm --clean --windowed --name PTW `
    --icon "$root\assets\ptw.ico" `
    --add-binary "$root\assets\libmpv-2.dll;." `
    --add-data "$root\assets\ptw.ico;." `
    --collect-all tkinterdnd2 `
    --paths "$root\src" `
    --distpath "$root\dist" --workpath "$root\build" --specpath "$root\build" `
    "$root\src\ptw.py"
if ($LASTEXITCODE) { throw "PyInstaller завершился с ошибкой" }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Не найден Inno Setup 6 (winget install JRSoftware.InnoSetup)" }
& $iscc /Q "/DMyAppVersion=$version" installer\ptw.iss
if ($LASTEXITCODE) { throw "Inno Setup завершился с ошибкой" }

Write-Host "Готово: dist\PTW-Setup-$version.exe"
