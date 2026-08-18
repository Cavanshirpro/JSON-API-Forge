[CmdletBinding()]
param(
    [ValidatePattern('^[0-9A-Za-z._-]+$')][string]$Version = '0.5.0',
    [string]$Destination = '',
    [ValidatePattern('^[0-9A-Za-z._-]+/[0-9A-Za-z._-]+$')][string]$Repository = 'Cavanshirpro/JSON-API-Forge'
)

$ErrorActionPreference = 'Stop'
$architecture = switch ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()) {
    'X64' { 'x64' }
    'Arm64' { 'arm64' }
    default { throw "Unsupported Windows architecture: $_. Use scripts/install.ps1 for the portable Python build." }
}
$platform = "windows-$architecture"
$asset = "JSON-API-Forge-v$Version-$platform.zip"
$base = "https://github.com/$Repository/releases/download/v$Version"
$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("forge-install-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporaryRoot | Out-Null

try {
    $archive = Join-Path $temporaryRoot $asset
    $checksum = "$archive.sha256"
    Invoke-WebRequest -UseBasicParsing -Uri "$base/$asset" -OutFile $archive
    Invoke-WebRequest -UseBasicParsing -Uri "$base/$asset.sha256" -OutFile $checksum
    $expected = ((Get-Content -LiteralPath $checksum -TotalCount 1) -split '\s+')[0].ToLowerInvariant()
    if ($expected -notmatch '^[0-9a-f]{64}$') { throw 'Release checksum file is malformed.' }
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw 'SHA-256 verification failed; nothing was installed.' }

    if (-not $Destination) { $Destination = "JSON-API-Forge-v$Version" }
    $target = [System.IO.Path]::GetFullPath($Destination)
    $parent = Split-Path -Parent $target
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    if (Test-Path -LiteralPath $target) { throw "Destination already exists: $target" }
    Expand-Archive -LiteralPath $archive -DestinationPath $target
    Write-Host "Installed verified JSON API Forge v$Version for $platform in $target"
    Write-Host "Run '$target\bin\forge.exe --help' or '$target\bin\forge-server.exe --root YOUR_DEPLOYMENT_ROOT'."
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
