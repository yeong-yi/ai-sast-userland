param(
    [string]$Destination = "target/userland"
)

$ErrorActionPreference = "Stop"
$SourceUrl = "https://github.com/raspberrypi/userland.git"

if (Test-Path (Join-Path $Destination ".git")) {
    Write-Host "UserLand source already exists at $Destination"
    exit 0
}

if (Test-Path $Destination) {
    throw "Destination exists but is not a Git checkout: $Destination"
}

$Parent = Split-Path -Parent $Destination
if ($Parent) {
    New-Item -ItemType Directory -Force -Path $Parent | Out-Null
}

git clone $SourceUrl $Destination
Write-Host "UserLand source is ready at $Destination"
