# Выпуск новой версии PTW: сборка + релиз на GitHub.
# Перед запуском: поднять __version__ в src\version.py и описать изменения в CHANGELOG.md.
# После публикации у всех установленных PTW при запуске появится предложение обновиться.
# внешние программы пишут прогресс в stderr — ошибки проверяем по $LASTEXITCODE
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$version = (Select-String -Path "src\version.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$tag = "v$version"

if (git status --porcelain) { throw "Есть незакоммиченные изменения — сначала сделайте коммит." }
if (git tag --list $tag) { throw "Версия $version уже выпущена — поднимите номер в src\version.py." }

# описание версии — раздел "## <версия>" из CHANGELOG.md
$notes = [System.Collections.Generic.List[string]]::new()
$inside = $false
foreach ($line in Get-Content CHANGELOG.md -Encoding UTF8) {
    if ($line -match '^## ') { if ($inside) { break }; $inside = $line -match [regex]::Escape($version); continue }
    if ($inside) { $notes.Add($line) }
}
$notesFile = Join-Path $env:TEMP "ptw-notes-$version.md"
[IO.File]::WriteAllText($notesFile, ($notes -join "`n").Trim(), (New-Object System.Text.UTF8Encoding($false)))

$gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $gh) {
    $gh = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter gh.exe -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $gh) { throw "Не найден GitHub CLI (winget install GitHub.cli)" }

& "$PSScriptRoot\build.ps1"

git tag $tag
git push origin HEAD $tag
if ($LASTEXITCODE) { git tag -d $tag; throw "Не удалось отправить код на GitHub" }
& $gh release create $tag "dist\PTW-Setup-$version.exe" --title "PTW $version" --notes-file $notesFile
if ($LASTEXITCODE) { throw "Не удалось создать релиз" }
Write-Host "Опубликовано: PTW $version"
