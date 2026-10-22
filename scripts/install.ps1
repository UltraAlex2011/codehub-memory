# Code Hub installer for Windows - one line in PowerShell:
#   irm https://raw.githubusercontent.com/UltraAlex2011/codehub-memory/main/scripts/install.ps1 | iex
# Installs Python with winget when it is missing, puts the newest version
# into %LOCALAPPDATA%\codehub\app, adds the "codehub" command, sets Code Hub
# up for Claude Code and opens the view. Running it again updates.
$ErrorActionPreference = 'Stop'
$Repo = 'UltraAlex2011/codehub-memory'
$De = (Get-Culture).Name -like 'de*'
function Say([string]$de, [string]$en) { if ($De) { Write-Host $de } else { Write-Host $en } }
function Fail([string]$de, [string]$en) { Say "x $de" "x $en"; exit 1 }

Say 'Code Hub wird installiert …' 'Installing Code Hub …'

# ---- Python 3.9+ ----
function Find-Python {
    foreach ($name in 'py', 'python', 'python3') {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        # the Microsoft Store placeholder "python" answers with an error code
        $exe = & $cmd.Source -c 'import sys; print(sys.executable) if sys.version_info >= (3, 9) else sys.exit(1)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
    }
    return $null
}
$Py = Find-Python
if (-not $Py) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail 'Python fehlt. Von https://www.python.org/downloads/ installieren (Haken bei „Add to PATH“), dann noch einmal.' `
             'Python is missing. Install it from https://www.python.org/downloads/ (tick “Add to PATH”), then run this again.'
    }
    Say 'Python fehlt – wird mit winget installiert …' 'Python is missing – installing it with winget …'
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements | Out-Null
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $Py = Find-Python
    if (-not $Py) {
        $guess = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
        if (Test-Path $guess) { $Py = $guess } else { Fail 'Python ließ sich nicht installieren.' 'Python could not be installed.' }
    }
}
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Say '! Claude Code ist noch nicht installiert – Code Hub richtet sich trotzdem ein; danach https://claude.com/claude-code installieren.' `
        '! Claude Code is not installed yet – Code Hub sets itself up anyway; install https://claude.com/claude-code afterwards.'
}

# ---- newest version ----
$Data = Join-Path $env:LOCALAPPDATA 'codehub'
$App = Join-Path $Data 'app'
$Tmp = Join-Path ([IO.Path]::GetTempPath()) ('codehub-' + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
try {
    $url = "https://codeload.github.com/$Repo/zip/refs/heads/main"
    Invoke-WebRequest $url -OutFile (Join-Path $Tmp 'codehub.zip') -UseBasicParsing
    Expand-Archive (Join-Path $Tmp 'codehub.zip') -DestinationPath (Join-Path $Tmp 'x') -Force
    $src = Get-ChildItem (Join-Path $Tmp 'x') -Directory | Select-Object -First 1
    if (-not (Test-Path (Join-Path $src.FullName 'codehub\__init__.py'))) { Fail 'Der Download ist unvollständig.' 'The download is incomplete.' }
    New-Item -ItemType Directory -Force -Path $Data | Out-Null
    if (Test-Path $App) { Remove-Item $App -Recurse -Force }
    Move-Item $src.FullName $App
} catch {
    Fail 'Download fehlgeschlagen – Internetverbindung prüfen.' 'Download failed – check the internet connection.'
} finally {
    Remove-Item $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}

# ---- the "codehub" command (WindowsApps is on every user's PATH) ----
$Bin = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps'
Set-Content -Path (Join-Path $Bin 'codehub.cmd') -Encoding ASCII -Value "@`"$Py`" `"$App\bin\codehub`" %*"

# ---- set up for Claude Code, then show it ----
& $Py (Join-Path $App 'bin\codehub') install
& $Py (Join-Path $App 'bin\codehub') open | Out-Null
if ($LASTEXITCODE -eq 0) {
    Say 'Fertig. Die Ansicht ist im Browser offen – später jederzeit: codehub open' `
        'Done. The view is open in your browser – any time later: codehub open'
} else {
    Say 'Fertig. Ansehen: codehub open' 'Done. Look at it: codehub open'
}
