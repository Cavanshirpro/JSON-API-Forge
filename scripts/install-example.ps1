param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("TaskBoard", "GuildLedger", "RealtimeSupport", "MediaLibrary", "PublicCatalog")]
    [string]$Name,
    [string]$Destination
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $Destination) {
    $Destination = Join-Path $RepositoryRoot "app"
}
$Source = Join-Path (Join-Path $RepositoryRoot "app") $Name
$Target = Join-Path $Destination $Name

if (-not (Test-Path (Join-Path $Source "app.json") -PathType Leaf)) {
    throw "Unknown example: $Name"
}
if (Test-Path $Target) {
    throw "Refusing to overwrite existing target: $Target"
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
Copy-Item -Path $Source -Destination $Target -Recurse
Write-Host "Installed $Name at $Target"
Write-Host "Next: run 'forge init', 'forge validate', and 'forge dev' in the destination checkout."
