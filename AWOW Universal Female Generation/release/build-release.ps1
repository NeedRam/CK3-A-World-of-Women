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

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}

function Assert-Hash([string]$Path, [string]$Expected, [string]$Label) {
    $actual = Get-Sha256 $Path
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

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$legacyOutputs = @(
    "AWOW-Universal-Female-Generation-v$Version-win64.zip",
    "AWOW-Universal-Female-Generation-v$Version-win64.zip.sha256",
    "AWOW-Universal-Female-Generation-v$Version-provenance.json"
)
foreach ($legacyName in $legacyOutputs) {
    $legacyPath = Join-Path $OutputDirectory $legacyName
    if (Test-Path -LiteralPath $legacyPath -PathType Leaf) { Remove-Item -LiteralPath $legacyPath -Force }
}

$nativeProxy = Join-Path $repositoryRoot 'build\dxcompiler.dll'
$nativePayload = Join-Path $repositoryRoot 'build\AWOW Universal Female Generation\awow_ufg.dll'
$forbiddenNames = @('native_test_mod', 'src', 'build', 'dist', 'tests', 'fixtures', '__pycache__', '.git', '.github', '.venv', 'venv', 'A World of Women CORE', 'AWOW Vanilla History OVERRIDES', 'AWOW Vanilla Male Source OVERRIDES')
$forbiddenFiles = @('build.py', 'requirements-build.txt', 'UFGInstaller.spec', 'UFGUninstaller.spec', 'UFGInstaller.version.txt', 'UFGUninstaller.version.txt')
$commit = 'unavailable'
try { $commit = (& git -C $repositoryRoot rev-parse HEAD 2>$null | Select-Object -First 1).Trim(); if (-not $commit) { $commit = 'unavailable' } } catch { $commit = 'unavailable' }
$toolchain = Get-Content -LiteralPath (Join-Path $repositoryRoot 'toolchain.json') -Raw | ConvertFrom-Json

$packageDefinitions = @(
    @{
        Id = 'manual'
        Name = "AWOW UFG v$Version Base Files (Manual Install)"
        Readme = 'release\README_MANUAL.md'
        Files = @()
        Directories = @()
        Required = @('dxcompiler.dll', 'AWOW Universal Female Generation\awow_ufg.dll', 'README.md', 'LICENSE')
        Forbidden = @('UFG-Installer.exe', 'UFG-Uninstaller.exe', 'Install UFG.bat', 'Uninstall UFG.bat', 'Installer')
    },
    @{
        Id = 'batch'
        Name = "AWOW UFG v$Version Batch File Installer"
        Readme = 'release\README_BATCH.md'
        Files = @(
            @{ Source = 'Install UFG.bat'; Destination = 'Install UFG.bat' },
            @{ Source = 'Uninstall UFG.bat'; Destination = 'Uninstall UFG.bat' },
            @{ Source = 'Installer\release-manifest.json'; Destination = 'Installer\release-manifest.json' },
            @{ Source = 'Installer\install.ps1'; Destination = 'Installer\install.ps1' },
            @{ Source = 'Installer\uninstall.ps1'; Destination = 'Installer\uninstall.ps1' }
        )
        Directories = @(@{ Source = 'Installer\powershell'; Destination = 'Installer\powershell' })
        Required = @('dxcompiler.dll', 'AWOW Universal Female Generation\awow_ufg.dll', 'Install UFG.bat', 'Uninstall UFG.bat', 'README.md', 'LICENSE')
        Forbidden = @('UFG-Installer.exe', 'UFG-Uninstaller.exe', 'Installer\python')
    },
    @{
        Id = 'exe'
        Name = "AWOW UFG v$Version EXE Installer"
        Readme = 'release\README_EXE.md'
        Files = @(
            @{ Source = 'Installer\UFGInstaller.exe'; Destination = 'UFG-Installer.exe' },
            @{ Source = 'Installer\UFGUninstaller.exe'; Destination = 'UFG-Uninstaller.exe' },
            @{ Source = 'Installer\release-manifest.json'; Destination = 'Installer\release-manifest.json' }
        )
        Directories = @()
        Required = @('dxcompiler.dll', 'AWOW Universal Female Generation\awow_ufg.dll', 'UFG-Installer.exe', 'UFG-Uninstaller.exe', 'README.md', 'LICENSE')
        Forbidden = @('Install UFG.bat', 'Uninstall UFG.bat', 'Installer\install.ps1', 'Installer\uninstall.ps1', 'Installer\powershell', 'Installer\python')
    }
)

foreach ($definition in $packageDefinitions) {
    $stagingRoot = Join-Path $OutputDirectory "$($manifest.package.id)-$($definition.Id)-staging"
    $packageRoot = Join-Path $stagingRoot $definition.Name
    $zipPath = Join-Path $OutputDirectory "$($definition.Name).zip"
    $checksumPath = "$zipPath.sha256"
    $provenancePath = Join-Path $OutputDirectory "$($definition.Name)-provenance.json"
    if (Test-Path -LiteralPath $stagingRoot) { Remove-Item -LiteralPath $stagingRoot -Recurse -Force }
    foreach ($outputPath in @($zipPath, $checksumPath, $provenancePath)) {
        if (Test-Path -LiteralPath $outputPath) { Remove-Item -LiteralPath $outputPath -Force }
    }
    New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null

    Copy-RequiredFile $nativeProxy (Join-Path $packageRoot 'dxcompiler.dll')
    Copy-RequiredFile $nativePayload (Join-Path $packageRoot 'AWOW Universal Female Generation\awow_ufg.dll')
    Copy-RequiredFile (Join-Path $repositoryRoot $definition.Readme) (Join-Path $packageRoot 'README.md')
    Copy-RequiredFile (Join-Path $repositoryRoot 'LICENSE') (Join-Path $packageRoot 'LICENSE')
    foreach ($mapping in $definition.Files) {
        Copy-RequiredFile (Join-Path $repositoryRoot $mapping.Source) (Join-Path $packageRoot $mapping.Destination)
    }
    foreach ($mapping in $definition.Directories) {
        Copy-PackageDirectory (Join-Path $repositoryRoot $mapping.Source) (Join-Path $packageRoot $mapping.Destination)
    }

    $packageManifest = $manifest | ConvertTo-Json -Depth 32 | ConvertFrom-Json
    foreach ($artifact in @($packageManifest.artifacts)) {
        $path = Join-Path $packageRoot ([string]$artifact.relative_path -replace '/', '\')
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Manifest artifact is absent from $($definition.Name): $($artifact.relative_path)" }
        $artifact.sha256 = Get-Sha256 $path
        $artifact.size_bytes = [int64](Get-Item -LiteralPath $path).Length
    }
    $proxyArtifact = @($packageManifest.artifacts | Where-Object { $_.id -eq 'ufg-proxy' })[0]
    $payloadArtifact = @($packageManifest.artifacts | Where-Object { $_.id -eq 'ufg-payload' })[0]
    foreach ($seed in @($packageManifest.compatibility.seeds)) {
        foreach ($file in @($seed.match.required_files)) {
            if ($file.relative_path -eq $payloadArtifact.relative_path) {
                $file.sha256 = $payloadArtifact.sha256
                $file.size_bytes = $payloadArtifact.size_bytes
            } elseif ($file.relative_path -eq $proxyArtifact.relative_path -and $seed.state -in @('manual_ufg', 'managed_ufg', 'ufg_proxy_only')) {
                $file.sha256 = $proxyArtifact.sha256
                $file.size_bytes = $proxyArtifact.size_bytes
            }
        }
    }
    $packagedManifestPath = Join-Path $packageRoot 'Installer\release-manifest.json'
    if (Test-Path -LiteralPath $packagedManifestPath -PathType Leaf) {
        $packageManifest.package.id = "$($manifest.package.id)-$($definition.Id)"
        $packageManifest.package.entrypoints = @($packageManifest.package.entrypoints | Where-Object {
            Test-Path -LiteralPath (Join-Path $packageRoot ([string]$_.relative_path -replace '/', '\'))
        })
        [IO.File]::WriteAllText($packagedManifestPath, ($packageManifest | ConvertTo-Json -Depth 32) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    }

    $forbidden = Get-ChildItem -LiteralPath $packageRoot -Recurse -Force | Where-Object { $forbiddenNames -contains $_.Name }
    if ($forbidden) { throw "Forbidden development content entered $($definition.Name): $($forbidden.Name -join ', ')" }
    $forbiddenBuildFiles = Get-ChildItem -LiteralPath $packageRoot -Recurse -File -Force | Where-Object { $forbiddenFiles -contains $_.Name }
    if ($forbiddenBuildFiles) { throw "Forbidden installer build content entered $($definition.Name): $($forbiddenBuildFiles.Name -join ', ')" }
    foreach ($relative in $definition.Required) {
        if (-not (Test-Path -LiteralPath (Join-Path $packageRoot $relative))) { throw "$($definition.Name) is missing: $relative" }
    }
    foreach ($relative in $definition.Forbidden) {
        if (Test-Path -LiteralPath (Join-Path $packageRoot $relative)) { throw "$($definition.Name) unexpectedly contains: $relative" }
    }
    foreach ($artifact in @($packageManifest.artifacts)) {
        $path = Join-Path $packageRoot ([string]$artifact.relative_path -replace '/', '\')
        Assert-Hash $path ([string]$artifact.sha256) ([string]$artifact.relative_path) | Out-Null
    }

    $checksumLines = New-Object Collections.Generic.List[string]
    Get-ChildItem -LiteralPath $packageRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
        $relative = $_.FullName.Substring($packageRoot.Length).TrimStart('\').Replace('\', '/')
        [void]$checksumLines.Add("$(Get-Sha256 $_.FullName) *$relative")
    }
    [IO.File]::WriteAllLines((Join-Path $packageRoot 'SHA256SUMS.txt'), $checksumLines, [Text.UTF8Encoding]::new($false))
    Compress-Archive -Path (Join-Path $stagingRoot '*') -DestinationPath $zipPath -CompressionLevel Optimal
    $zipHash = Get-Sha256 $zipPath
    [IO.File]::WriteAllText($checksumPath, "$zipHash *$(Split-Path -Leaf $zipPath)`n", [Text.UTF8Encoding]::new($false))

    $provenance = [ordered]@{
        schema_version = 1
        kind = 'ufg_release_provenance'
        release = [ordered]@{ id = $manifest.release.id; version = $Version; channel = $manifest.release.channel; unsigned = $true; signing = 'not_performed' }
        source = [ordered]@{ repository = $manifest.release.source_repo; commit = $commit; workflow = 'release/build-release.ps1' }
        build = [ordered]@{ authority = $(if ($isCanonicalCi) { 'canonical_github_actions' } else { 'local_smoke_test' }); canonical_release_artifact = $isCanonicalCi; github_actions_runner = $toolchain.github_actions_runner; visual_studio_version_range = $toolchain.visual_studio_version_range; vc_tools_version = $toolchain.vc_tools_version; windows_sdk_version = $toolchain.windows_sdk_version; host_architecture = $toolchain.host_architecture; target_architecture = $toolchain.target_architecture; vcvars_architecture = $toolchain.vcvars_architecture; toolchain_contract = 'toolchain.json' }
        artifact = [ordered]@{ file = (Split-Path -Leaf $zipPath); sha256 = $zipHash; package_id = "$($manifest.package.id)-$($definition.Id)"; package_kind = $definition.Id; file_count = @(Get-ChildItem -LiteralPath $packageRoot -Recurse -File).Count }
        safety = [ordered]@{ excluded = $forbiddenNames; credentials_used = $false; agp_dependency = 'exact SHA-256 values declared in compatible_agp_builds' }
    }
    [IO.File]::WriteAllText($provenancePath, ($provenance | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-Host "Created $zipPath"
    Write-Host "SHA-256 $zipHash"
    Write-Host "Created $checksumPath and $provenancePath"
}
