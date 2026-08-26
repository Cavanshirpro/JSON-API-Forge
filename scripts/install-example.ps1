param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")]
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
$Links = @(Get-ChildItem -LiteralPath $Source -Recurse -Force | Where-Object {
    $_.Attributes -band [IO.FileAttributes]::ReparsePoint
})
if ($Links) {
    throw "Refusing to copy an example that contains symbolic links: $Name"
}
if (Test-Path $Target) {
    throw "Refusing to overwrite existing target: $Target"
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
Copy-Item -Path $Source -Destination $Target -Recurse
Write-Host "Installed $Name at $Target"
Write-Host "Next: run 'forge init', 'forge validate', and 'forge dev' in the destination checkout."
