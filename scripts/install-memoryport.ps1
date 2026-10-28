param(
    [string]$Extras = ""
)

$ErrorActionPreference = "Stop"
$allowedExtras = @("crypto", "mongodb", "server", "mcp")
$extraList = @()

if ($Extras) {
    $extraList = @($Extras -split "," | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
    foreach ($extra in $extraList) {
        if ($extra -notin $allowedExtras) {
            throw "Unknown extra '$extra'. Choose from: $($allowedExtras -join ', ')"
        }
    }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is required to install the package from GitHub. Install Git, then run this script again."
}

$pythonCommand = Get-Command py -ErrorAction SilentlyContinue
$pythonArgs = @("-3")
if (-not $pythonCommand) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    $pythonArgs = @()
}
if (-not $pythonCommand) {
    throw "Python 3.10 or newer is required. Install Python, then run this script again."
}

& $pythonCommand.Source @pythonArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.10 or newer is required."
}

$installRoot = if ($env:NEXORAI_HOME) {
    $env:NEXORAI_HOME
} else {
    Join-Path $env:LOCALAPPDATA "NexorAI\MemoryPort"
}
$venv = Join-Path $installRoot "venv"
$venvPython = Join-Path $venv "Scripts\python.exe"
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
& $pythonCommand.Source @pythonArgs -m venv $venv
if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment." }

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }

$package = "nexorai-smart-auto"
if ($extraList.Count -gt 0) {
    $package += "[$($extraList -join ',')]"
}
$packageSpec = "$package @ git+https://github.com/RohanNK86/Open_AI_Bot.git@main"
& $venvPython -m pip install --upgrade $packageSpec
if ($LASTEXITCODE -ne 0) { throw "Could not install MemoryPort from GitHub." }

$vaultCommand = Join-Path $venv "Scripts\nexor-vault.exe"
Write-Host "MemoryPort and SmartRouter installed in: $venv"
Write-Host "Vault database default: $(Join-Path $HOME '.nexorai\memory.sqlite3')"
Write-Host "CLI: & `"$vaultCommand`" --help"

