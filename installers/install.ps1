<#
.SYNOPSIS
  Install focos on Windows without admin rights.

  irm https://raw.githubusercontent.com/m-swaney/focos/main/installers/install.ps1 | iex

  Installs uv + Python 3.13, a private Node runtime, the latest focos release into %USERPROFILE%\.focos\app,
  creates your data folder (default %USERPROFILE%\focos-home), registers the dashboard to start at login,
  and opens the setup wizard at http://localhost:3100/setup.

.PARAMETER DataDir   Where your config, history, and briefs live (default: %USERPROFILE%\focos-home)
.PARAMETER Version   Release tag to install (default: latest)
.PARAMETER Repo      GitHub repository (default: m-swaney/focos)
.PARAMETER Dev       Clone the repository with git instead of downloading a release (for contributors)
#>
[CmdletBinding()]
param(
  [string]$DataDir = "$env:USERPROFILE\focos-home",
  [string]$Version = "latest",
  [string]$Repo = "m-swaney/focos",
  [switch]$Dev,
  [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Base = Join-Path $env:USERPROFILE '.focos'
$Bin = Join-Path $Base 'bin'
$NodeDir = Join-Path $Base 'node'
New-Item -ItemType Directory -Force $Base, $Bin | Out-Null
function Log($m) { Write-Host "[focos] $m" }
function Refresh-Path { $env:PATH = [Environment]::GetEnvironmentVariable('PATH', 'User') + ';' + [Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' + $env:PATH }

# ---- uv (Python manager)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Log 'installing uv'
  Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
  Refresh-Path
}
Log 'ensuring Python 3.13'
uv python install 3.13 | Out-Null

# ---- the app
if ($Dev) {
  $App = Join-Path $Base 'app'
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git is required for -Dev' }
  if (Test-Path (Join-Path $App '.git')) { git -C $App pull -q } else { git clone -q "https://github.com/$Repo.git" $App }
  $Ver = 'dev'
} else {
  $api = if ($Version -eq 'latest') { "https://api.github.com/repos/$Repo/releases/latest" } else { "https://api.github.com/repos/$Repo/releases/tags/$Version" }
  Log "looking up release $Version"
  $rel = Invoke-RestMethod $api -Headers @{ 'User-Agent' = 'focos-installer' }
  $Ver = $rel.tag_name
  $asset = $rel.assets | Where-Object { $_.name -like 'focos-*.zip' } | Select-Object -First 1
  $sum = $rel.assets | Where-Object { $_.name -like 'focos-*.zip.sha256' } | Select-Object -First 1
  if (-not $asset) { throw "release $Ver has no focos-*.zip asset" }
  $App = Join-Path $Base "app-$Ver"
  if (-not (Test-Path (Join-Path $App 'pyproject.toml'))) {
    $zip = Join-Path $Base $asset.name
    Log "downloading $($asset.name)"
    Invoke-WebRequest $asset.browser_download_url -OutFile $zip -UseBasicParsing
    if ($sum) {
      $expected = ((Invoke-WebRequest $sum.browser_download_url -UseBasicParsing).Content -split '\s+')[0]
      $actual = (Get-FileHash $zip -Algorithm SHA256).Hash
      if ($actual -ne $expected) { throw "checksum mismatch for $($asset.name)" }
    }
    if (Test-Path $App) { Remove-Item -Recurse -Force $App }
    Expand-Archive $zip -DestinationPath $App -Force
    # archives may wrap everything in one top-level folder
    $inner = Get-ChildItem $App -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'pyproject.toml') } | Select-Object -First 1
    if ($inner -and -not (Test-Path (Join-Path $App 'pyproject.toml'))) { Get-ChildItem $inner.FullName -Force | Move-Item -Destination $App -Force; Remove-Item $inner.FullName -Recurse -Force }
    Remove-Item $zip -Force
  }
}
Set-Content (Join-Path $Base 'app.txt') $App

# ---- private Node runtime (for the dashboard)
if (-not (Test-Path (Join-Path $NodeDir 'node.exe'))) {
  Log 'downloading Node.js LTS runtime'
  $shas = (Invoke-WebRequest 'https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt' -UseBasicParsing).Content
  $name = ($shas -split "`n" | Where-Object { $_ -match 'node-v[\d.]+-win-x64\.zip' } | ForEach-Object { ($_ -split '\s+')[1] }) | Select-Object -First 1
  $nz = Join-Path $Base $name
  Invoke-WebRequest "https://nodejs.org/dist/latest-v22.x/$name" -OutFile $nz -UseBasicParsing
  $tmp = Join-Path $Base 'node-tmp'
  if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
  Expand-Archive $nz -DestinationPath $tmp -Force
  if (Test-Path $NodeDir) { Remove-Item -Recurse -Force $NodeDir }
  Move-Item (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName $NodeDir
  Remove-Item $tmp, $nz -Recurse -Force
}

# ---- python environment
Log 'creating the Python environment'
$Py = Join-Path $App '.venv\Scripts\python.exe'
if (-not (Test-Path $Py)) { uv venv (Join-Path $App '.venv') --python 3.13 -q }
if (Test-Path (Join-Path $App 'uv.lock')) { uv sync --project $App --frozen --all-extras --no-dev -q } else { uv pip install --python $Py -q -e "$App[all]" }

# ---- `focos` command shim on the user PATH
$shim = Join-Path $Bin 'focos.cmd'
@"
@echo off
setlocal
set /p APP=<"%USERPROFILE%\.focos\app.txt"
"%APP%\.venv\Scripts\python.exe" -I -m focos %*
"@ | Set-Content $shim -Encoding ASCII
$userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
if ($userPath -notlike "*$Bin*") { [Environment]::SetEnvironmentVariable('PATH', "$userPath;$Bin", 'User'); $env:PATH += ";$Bin" }

# ---- data folder + service
Log "initializing your data folder at $DataDir"
& $Py -I -m focos init --home $DataDir --set-default | Out-Null
& $Py -I -m focos --home $DataDir agent render-settings | Out-Null
Log 'registering the dashboard to start at login'
& $Py -I -m focos --home $DataDir service install | Out-Null

Log "installed focos $Ver"
Log 'open http://localhost:3100/setup to finish setup (the dashboard may take ~20 s to start the first time)'
if (-not $NoBrowser) { Start-Sleep 5; Start-Process 'http://localhost:3100/setup' }
