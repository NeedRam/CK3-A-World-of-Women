[CmdletBinding()]
param(
    [string]$Version = '1.0.0',
    [string]$OutputDirectory,
    [switch]$SkipNativeBuild,
    [switch]$RequireCanonicalCi
)

$ErrorActionPreference = 'Stop'
$releaseRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $releaseRoot
$isCanonicalCi = $env:GITHUB_ACTIONS -eq 'true'
if ($RequireCanonicalCi -and -not $isCanonicalCi) { throw 'Canonical release assembly is restricted to GitHub Actions.' }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $releaseRoot 'out' }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)

function Copy-RequiredFile([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Required release input is missing: $Source" }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function Copy-PackageDirectory([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) { throw "Required release directory is missing: $Source" }
    Get-ChildItem -LiteralPath $Source -Recurse -File | Where-Object {
        $relative = $_.FullName.Substring($Source.TrimEnd('\').Length).TrimStart('\')
        $relative -notmatch '^(tests?|__pycache__|\.pytest_cache|\.venv|venv|build|dist)(\\|$)' -and
        $_.Extension -notin @('.pyc', '.pyo', '.spec') -and
        $_.Name -notin @('build.py', 'requirements-build.txt', 'UFGInstaller.version.txt', 'UFGUninstaller.version.txt')
    } | ForEach-Object {
        $relative = $_.FullName.Substring($Source.TrimEnd('\').Length).TrimStart('\')
        $destinationPath = Join-Path $Destination $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destinationPath) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $destinationPath -Force
    }
}

function Assert-Hash([string]$Path, [string]$Expected, [string]$Label) {
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Expected.ToLowerInvariant()) { throw "$Label hash mismatch. Expected $Expected, got $actual." }
    return $actual
}

$manifestPath = Join-Path $repositoryRoot 'Installer\release-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Release manifest is missing: $manifestPath" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ([string]$manifest.release.version -ne $Version) { throw "Requested version $Version does not match manifest version $($manifest.release.version)." }
if (-not $manifest.release.unsigned) { throw 'UFG v1.0.0 must remain explicitly unsigned.' }
if (-not $SkipNativeBuild) {
    & (Join-Path $repositoryRoot 'build.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Native UFG build failed.' }
}

$packageId = [string]$manifest.package.id
$stagingRoot = Join-Path $OutputDirectory "$packageId-staging"
$packageRoot = Join-Path $stagingRoot "AWOW Universal Female Generation v$Version"
$zipPath = Join-Path $OutputDirectory "AWOW-Universal-Female-Generation-v$Version-win64.zip"
$checksumPath = "$zipPath.sha256"
$provenancePath = Join-Path $OutputDirectory "AWOW-Universal-Female-Generation-v$Version-provenance.json"
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
foreach ($path in @($stagingRoot, $zipPath, $checksumPath, $provenancePath)) {
    if (Test-Path -LiteralPath $path) {
        if ((Get-Item -LiteralPath $path).PSIsContainer) { Remove-Item -LiteralPath $path -Recurse -Force } else { Remove-Item -LiteralPath $path -Force }
    }
}
New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null

Copy-RequiredFile (Join-Path $repositoryRoot 'build\dxcompiler.dll') (Join-Path $packageRoot 'dxcompiler.dll')
Copy-RequiredFile (Join-Path $repositoryRoot 'build\AWOW Universal Female Generation\awow_ufg.dll') (Join-Path $packageRoot 'AWOW Universal Female Generation\awow_ufg.dll')
Copy-RequiredFile (Join-Path $repositoryRoot 'Install UFG.bat') (Join-Path $packageRoot 'Install UFG.bat')
Copy-RequiredFile (Join-Path $repositoryRoot 'Uninstall UFG.bat') (Join-Path $packageRoot 'Uninstall UFG.bat')
Copy-RequiredFile (Join-Path $repositoryRoot 'Installer\UFGInstaller.exe') (Join-Path $packageRoot 'UFG-Installer.exe')
Copy-RequiredFile (Join-Path $repositoryRoot 'Installer\UFGUninstaller.exe') (Join-Path $packageRoot 'UFG-Uninstaller.exe')
Copy-RequiredFile (Join-Path $releaseRoot 'END_USER_README.md') (Join-Path $packageRoot 'README.md')
Copy-RequiredFile (Join-Path $releaseRoot 'RELEASE_NOTES.md') (Join-Path $packageRoot 'RELEASE_NOTES.md')
Copy-RequiredFile (Join-Path $repositoryRoot 'toolchain.json') (Join-Path $packageRoot 'BUILD_TOOLCHAIN.json')
Copy-RequiredFile (Join-Path $repositoryRoot 'LICENSE') (Join-Path $packageRoot 'LICENSE')
Copy-RequiredFile (Join-Path $repositoryRoot 'PRIVACY.md') (Join-Path $packageRoot 'PRIVACY.md')
Copy-RequiredFile (Join-Path $repositoryRoot 'SECURITY.md') (Join-Path $packageRoot 'SECURITY.md')
Copy-RequiredFile (Join-Path $repositoryRoot 'SIGNING.md') (Join-Path $packageRoot 'SIGNING.md')
Copy-RequiredFile $manifestPath (Join-Path $packageRoot 'Installer\release-manifest.json')
Copy-RequiredFile (Join-Path $repositoryRoot 'Installer\install.ps1') (Join-Path $packageRoot 'Installer\install.ps1')
Copy-RequiredFile (Join-Path $repositoryRoot 'Installer\uninstall.ps1') (Join-Path $packageRoot 'Installer\uninstall.ps1')
Copy-PackageDirectory (Join-Path $repositoryRoot 'Installer\python') (Join-Path $packageRoot 'Installer\python')
Copy-PackageDirectory (Join-Path $repositoryRoot 'Installer\powershell') (Join-Path $packageRoot 'Installer\powershell')
Copy-PackageDirectory (Join-Path $repositoryRoot 'Installer\spec') (Join-Path $packageRoot 'Installer\spec')

# The checked-in manifest is the contract template. The packaged manifest is
# regenerated from the exact staged DLL bytes on every assembly.
foreach ($artifact in @($manifest.artifacts)) {
    $path = Join-Path $packageRoot ([string]$artifact.relative_path -replace '/', '\')
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Manifest artifact is absent from package: $($artifact.relative_path)" }
    $artifact.sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    $artifact.size_bytes = [int64](Get-Item -LiteralPath $path).Length
}
# Keep compatibility seed evidence synchronized with the staged UFG artifacts.
$proxyArtifact = @($manifest.artifacts | Where-Object { $_.id -eq 'ufg-proxy' })[0]
$payloadArtifact = @($manifest.artifacts | Where-Object { $_.id -eq 'ufg-payload' })[0]
foreach ($seed in @($manifest.compatibility.seeds)) {
    foreach ($file in @($seed.match.required_files)) {
        if ($file.relative_path -eq $payloadArtifact.relative_path) {
            $file.sha256 = $payloadArtifact.sha256; $file.size_bytes = $payloadArtifact.size_bytes
        }
        elseif ($file.relative_path -eq $proxyArtifact.relative_path -and $seed.state -in @('manual_ufg', 'managed_ufg', 'ufg_proxy_only')) {
            $file.sha256 = $proxyArtifact.sha256; $file.size_bytes = $proxyArtifact.size_bytes
        }
    }
}
$packagedManifestPath = Join-Path $packageRoot 'Installer\release-manifest.json'
$manifestJson = $manifest | ConvertTo-Json -Depth 32
[IO.File]::WriteAllText($packagedManifestPath, $manifestJson + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

$forbiddenNames = @('native_test_mod', 'src', 'build', 'dist', 'tests', 'fixtures', '__pycache__', '.git', '.github', '.venv', 'venv', 'A World of Women CORE', 'AWOW Vanilla History OVERRIDES', 'AWOW Vanilla Male Source OVERRIDES')
$forbiddenFiles = @('build.py', 'requirements-build.txt', 'UFGInstaller.spec', 'UFGUninstaller.spec', 'UFGInstaller.version.txt', 'UFGUninstaller.version.txt')
$forbidden = Get-ChildItem -LiteralPath $packageRoot -Recurse -Force | Where-Object { $forbiddenNames -contains $_.Name }
if ($forbidden) { throw "Forbidden development content entered package: $($forbidden.Name -join ', ')" }
$forbiddenBuildFiles = Get-ChildItem -LiteralPath $packageRoot -Recurse -File -Force | Where-Object { $forbiddenFiles -contains $_.Name }
if ($forbiddenBuildFiles) { throw "Forbidden installer build content entered package: $($forbiddenBuildFiles.Name -join ', ')" }
foreach ($relative in @('UFG-Installer.exe', 'UFG-Uninstaller.exe', 'Install UFG.bat', 'Uninstall UFG.bat', 'README.md', 'PRIVACY.md', 'SECURITY.md', 'SIGNING.md', 'dxcompiler.dll', 'AWOW Universal Female Generation\awow_ufg.dll')) {
    if (-not (Test-Path -LiteralPath (Join-Path $packageRoot $relative) -PathType Leaf)) { throw "Required package entry is missing: $relative" }
}
foreach ($artifact in @($manifest.artifacts)) {
    $path = Join-Path $packageRoot ([string]$artifact.relative_path -replace '/', '\')
    Assert-Hash $path ([string]$artifact.sha256) ([string]$artifact.relative_path) | Out-Null
}

$checksumLines = New-Object Collections.Generic.List[string]
Get-ChildItem -LiteralPath $packageRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
    $relative = $_.FullName.Substring($packageRoot.Length).TrimStart('\').Replace('\', '/')
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    [void]$checksumLines.Add("$hash *$relative")
}
[IO.File]::WriteAllLines((Join-Path $packageRoot 'SHA256SUMS.txt'), $checksumLines, [Text.UTF8Encoding]::new($false))
Compress-Archive -Path (Join-Path $stagingRoot '*') -DestinationPath $zipPath -CompressionLevel Optimal
$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText($checksumPath, "$zipHash *$(Split-Path -Leaf $zipPath)`n", [Text.UTF8Encoding]::new($false))

$commit = 'unavailable'
try { $commit = (& git -C $repositoryRoot rev-parse HEAD 2>$null | Select-Object -First 1).Trim(); if (-not $commit) { $commit = 'unavailable' } } catch { $commit = 'unavailable' }
$toolchain = Get-Content -LiteralPath (Join-Path $repositoryRoot 'toolchain.json') -Raw | ConvertFrom-Json
$provenance = [ordered]@{
    schema_version = 1
    kind = 'ufg_release_provenance'
    release = [ordered]@{ id = $manifest.release.id; version = $Version; channel = $manifest.release.channel; unsigned = $true; signing = 'not_performed' }
    source = [ordered]@{ repository = $manifest.release.source_repo; commit = $commit; workflow = 'release/build-release.ps1' }
    build = [ordered]@{ authority = $(if ($isCanonicalCi) { 'canonical_github_actions' } else { 'local_smoke_test' }); canonical_release_artifact = $isCanonicalCi; github_actions_runner = $toolchain.github_actions_runner; visual_studio_version_range = $toolchain.visual_studio_version_range; vc_tools_version = $toolchain.vc_tools_version; windows_sdk_version = $toolchain.windows_sdk_version; host_architecture = $toolchain.host_architecture; target_architecture = $toolchain.target_architecture; vcvars_architecture = $toolchain.vcvars_architecture; toolchain_contract = 'toolchain.json' }
    artifact = [ordered]@{ file = (Split-Path -Leaf $zipPath); sha256 = $zipHash; package_id = $packageId; file_count = @(Get-ChildItem -LiteralPath $packageRoot -Recurse -File).Count }
    safety = [ordered]@{ excluded = $forbiddenNames; credentials_used = $false; agp_dependency = 'exact SHA-256 values declared in compatible_agp_builds' }
}
$provenanceJson = $provenance | ConvertTo-Json -Depth 12
[IO.File]::WriteAllText($provenancePath, $provenanceJson + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Created $zipPath"
Write-Host "SHA-256 $zipHash"
Write-Host "Created $checksumPath and $provenancePath"
