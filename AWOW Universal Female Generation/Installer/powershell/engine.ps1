[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('install', 'uninstall')]
    [string]$Operation,
    [Parameter(Mandatory = $true)]
    [string]$TargetRoot,
    [string]$PackageRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$Confirmation,
    [switch]$Interactive,
    [switch]$Json,
    [string]$WriteFaultAt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Fail([string]$Message) {
    throw [InvalidOperationException]::new($Message)
}

function Get-FullPath([string]$Path) {
    return [IO.Path]::GetFullPath($Path)
}

function Get-Sha256([string]$Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $stream.Dispose()
        $algorithm.Dispose()
    }
}

function Get-CanonicalRelative([string]$Path) {
    return ($Path -replace '\\', '/')
}

function Test-RelativePath([string]$RelativePath) {
    if ([string]::IsNullOrWhiteSpace($RelativePath)) { return $false }
    if ([IO.Path]::IsPathRooted($RelativePath)) { return $false }
    if ($RelativePath -match '^[A-Za-z]:') { return $false }
    if ($RelativePath -match '(^|[\\/])\.\.?(?:[\\/]|$)') { return $false }
    if ($RelativePath -match '[<>:"|?*\x00-\x1f]') { return $false }
    return $true
}

function Test-PathSafety([hashtable]$Context, [string]$Path) {
    $root = Get-FullPath $Context.Root
    $candidate = Get-FullPath $Path
    $prefix = $root.TrimEnd('\') + '\'
    if (-not ($candidate.Equals($root, [StringComparison]::OrdinalIgnoreCase) -or $candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase))) {
        Fail "Resolved path is outside target root: $Path"
    }
    $current = $candidate
    while ($null -ne $current -and $current.Length -ge $root.Length) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                Fail "Reparse point is not an authorized installer path: $current"
            }
        }
        if ($current.Equals($root, [StringComparison]::OrdinalIgnoreCase)) { break }
        $parent = Split-Path -Parent $current
        if ([string]::IsNullOrEmpty($parent) -or $parent.Equals($current, [StringComparison]::OrdinalIgnoreCase)) { break }
        $current = $parent
    }
}

function Get-ContainedPath([hashtable]$Context, [string]$RelativePath) {
    if (-not (Test-RelativePath $RelativePath)) { Fail "Rejected non-relative path: $RelativePath" }
    $root = Get-FullPath $Context.Root
    $candidate = Get-FullPath (Join-Path $root ($RelativePath -replace '/', '\'))
    $prefix = $root.TrimEnd('\') + '\'
    if (-not $candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { Fail "Path escapes target root: $RelativePath" }
    Test-PathSafety $Context $candidate
    return $candidate
}

function Get-Observation([hashtable]$Context, [string]$RelativePath) {
    $path = Get-ContainedPath $Context $RelativePath
    if (-not (Test-Path -LiteralPath $path)) {
        return [ordered]@{ exists = $false; kind = 'absent'; is_reparse_point = $false }
    }
    $item = Get-Item -LiteralPath $path -Force
    if ($item.PSIsContainer) {
        return [ordered]@{ exists = $true; kind = 'directory'; is_reparse_point = $false }
    }
    $hash = Get-Sha256 $path
    return [ordered]@{ exists = $true; kind = 'file'; sha256 = $hash; size_bytes = [int64]$item.Length; is_reparse_point = $false }
}

function Write-JsonFile([string]$Path, $Value) {
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $temporary = Join-Path $parent ('.' + [IO.Path]::GetFileName($Path) + '.' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $json = $Value | ConvertTo-Json -Depth 32
    $encoding = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllText($temporary, $json + "`n", $encoding)
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Get-JsonObject([string]$Path) {
    try { return (Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json) }
    catch { return $null }
}

function Test-Sha([object]$Value) {
    return ($null -ne $Value -and [string]$Value -match '^[0-9a-fA-F]{64}$')
}

function Test-UfgStateShape([hashtable]$Context, $State) {
    if ($null -eq $State) { return $false }
    try {
        if ($State.schema_version -ne 1 -or $State.kind -ne 'ufg_install_state' -or $State.status -notin @('managed_ufg', 'ufg_proxy_only')) { return $false }
        if ([string]$State.transaction_id -notmatch '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$') { return $false }
        if ($State.release.id -ne 'awow-ufg' -or $State.release.version -notmatch '^\d+\.\d+\.\d+$' -or -not (Test-Sha $State.release.manifest_sha256)) { return $false }
        if ($State.target.game_id -ne 'crusader_kings_iii' -or $State.target.binaries_relative_path -ne 'binaries' -or $State.target.executable_relative_path -ne 'ck3.exe' -or $State.target.target_root_kind -ne 'steam_game_binaries') { return $false }
        foreach ($base in @($State.baseline.original_dxcompiler, $State.baseline.executable)) {
            if ($null -eq $base -or $base.relative_path -notin @($Context.Manifest.target.original_dxcompiler_relative_path, 'ck3.exe') -or -not (Test-RelativePath ([string]$base.relative_path)) -or -not (Test-Sha $base.sha256) -or [int64]$base.size_bytes -lt 0 -or $base.ownership -ne 'steam') { return $false }
        }
        if ($State.baseline.original_dxcompiler.relative_path -ne $Context.Manifest.target.original_dxcompiler_relative_path -or $State.baseline.executable.relative_path -ne 'ck3.exe') { return $false }
        $dependency = $State.agp_dependency
        if ($null -eq $dependency -or $dependency.proxy_relative_path -ne 'dxcompiler.dll' -or $dependency.payload_relative_path -ne 'AGP Native Hook/agp_parenthook.dll' -or $dependency.state_relative_path -ne 'AGP Native Hook/agp-install-state.json' -or -not (Test-Sha $dependency.proxy_sha256) -or -not (Test-Sha $dependency.payload_sha256) -or -not (Test-Sha $dependency.original_dxcompiler_sha256)) { return $false }
        if ([string]$dependency.state_sha256 -ne 'absent' -and -not (Test-Sha $dependency.state_sha256)) { return $false }
        $managed = @($State.managed_files)
        if ($managed.Count -ne 2) { return $false }
        $paths = @{}
        foreach ($item in $managed) {
            if ($null -eq $item -or $item.relative_path -notin @($Context.Manifest.target.active_dxcompiler_relative_path, 'AWOW Universal Female Generation/awow_ufg.dll') -or $paths.ContainsKey([string]$item.relative_path) -or $item.role -notin @('ufg_proxy', 'ufg_payload') -or $item.ownership -ne 'managed' -or -not (Test-Sha $item.installed_sha256) -or [int64]$item.installed_size_bytes -lt 0 -or $item.present -notin @($true, $false) -or $item.restore.action -notin @('leave_managed_file', 'remove_managed_file')) { return $false }
            if (($item.relative_path -eq $Context.Manifest.target.active_dxcompiler_relative_path -and ($item.role -ne 'ufg_proxy' -or $item.restore.action -ne 'leave_managed_file')) -or ($item.relative_path -eq 'AWOW Universal Female Generation/awow_ufg.dll' -and ($item.role -ne 'ufg_payload' -or $item.restore.action -ne 'remove_managed_file'))) { return $false }
            $paths[[string]$item.relative_path] = $item
        }
        if (-not $paths.ContainsKey($Context.Manifest.target.active_dxcompiler_relative_path) -or -not $paths.ContainsKey('AWOW Universal Female Generation/awow_ufg.dll')) { return $false }
        if (-not $paths[$Context.Manifest.target.active_dxcompiler_relative_path].present -or [bool]$paths['AWOW Universal Female Generation/awow_ufg.dll'].present -ne ($State.status -eq 'managed_ufg')) { return $false }
        if ($null -eq @($State.quarantined_files)) { return $false }
        if ($State.foreign_cleanup.kind -ne 'none' -or $State.foreign_cleanup.uninstall_policy -ne 'none' -or @($State.foreign_cleanup.removed_paths).Count -ne 0 -or -not (Test-RelativePath ([string]$State.foreign_cleanup.quarantine_relative_path))) { return $false }
        if ([string]::IsNullOrWhiteSpace([string]$State.created_utc) -or [string]::IsNullOrWhiteSpace([string]$State.updated_utc)) { return $false }
        return $true
    }
    catch { return $false }
}

function Test-AgpState([hashtable]$Context, $Candidate) {
    $statePath = Get-ContainedPath $Context 'AGP Native Hook/agp-install-state.json'
    if (-not (Test-Path -LiteralPath $statePath)) { return $true }
    $state = Get-JsonObject $statePath
    if ($null -eq $state -or $state.schema_version -ne 1 -or $state.kind -ne 'agp_install_state' -or $state.status -ne 'managed_agp') { return $false }
    if ([string]$state.baseline.original_dxcompiler.sha256 -notlike ([string]$Candidate.original_dxcompiler_sha256)) { return $false }
    $found = @{}
    foreach ($item in @($state.managed_files)) {
        if ($null -ne $item -and $item.relative_path -in @($Candidate.proxy_relative_path, $Candidate.payload_relative_path) -and $item.ownership -eq 'managed') { $found[[string]$item.relative_path] = ([string]$item.installed_sha256).ToLowerInvariant() }
    }
    return ($found[[string]$Candidate.proxy_relative_path] -eq ([string]$Candidate.proxy_sha256).ToLowerInvariant() -and $found[[string]$Candidate.payload_relative_path] -eq ([string]$Candidate.payload_sha256).ToLowerInvariant())
}

function Get-ManagedItem($State, [string]$RelativePath) {
    if ($null -eq $State) { return $null }
    foreach ($item in @($State.managed_files)) {
        if ($null -ne $item -and [string]$item.relative_path -eq $RelativePath) { return $item }
    }
    return $null
}

function Get-AgpCandidate([hashtable]$Context, [string]$AllowedActiveSha = '') {
    foreach ($candidate in @($Context.Manifest.compatible_agp_builds)) {
        $exe = Get-Observation $Context 'ck3.exe'
        if (-not $exe.exists -or $exe.kind -ne 'file' -or $exe.sha256 -ne ([string]$candidate.executable_sha256).ToLowerInvariant()) { continue }
        $active = Get-Observation $Context ([string]$candidate.proxy_relative_path)
        $activeMatch = ($active.exists -and $active.kind -eq 'file' -and $active.sha256 -eq ([string]$candidate.proxy_sha256).ToLowerInvariant())
        if (-not $activeMatch -and -not [string]::IsNullOrWhiteSpace($AllowedActiveSha)) {
            $activeMatch = ($active.exists -and $active.kind -eq 'file' -and $active.sha256 -eq $AllowedActiveSha.ToLowerInvariant())
        }
        if (-not $activeMatch) { continue }
        $payload = Get-Observation $Context ([string]$candidate.payload_relative_path)
        if (-not $payload.exists -or $payload.kind -ne 'file' -or $payload.sha256 -ne ([string]$candidate.payload_sha256).ToLowerInvariant()) { continue }
        $original = Get-Observation $Context ([string]$Context.Manifest.target.original_dxcompiler_relative_path)
        if (-not $original.exists -or $original.kind -ne 'file' -or $original.sha256 -ne ([string]$candidate.original_dxcompiler_sha256).ToLowerInvariant()) { continue }
        if (-not (Test-AgpState $Context $candidate)) { continue }
        return $candidate
    }
    return $null
}

function Test-ManagedState([hashtable]$Context, $State, $Candidate) {
    if (-not (Test-UfgStateShape $Context $State) -or $null -eq $Candidate) { return $false }
    $exe = Get-Observation $Context 'ck3.exe'
    $original = Get-Observation $Context ([string]$Context.Manifest.target.original_dxcompiler_relative_path)
    $active = Get-Observation $Context ([string]$Context.Manifest.target.active_dxcompiler_relative_path)
    $payload = Get-Observation $Context 'AWOW Universal Female Generation/awow_ufg.dll'
    $agpRebasedProxyOnly = ($State.status -eq 'ufg_proxy_only' -and $active.exists -and $active.kind -eq 'file' -and $active.sha256 -eq ([string]$Candidate.proxy_sha256).ToLowerInvariant() -and -not $payload.exists)
    if (-not $agpRebasedProxyOnly) {
        if (-not $exe.exists -or $exe.sha256 -ne ([string]$State.baseline.executable.sha256).ToLowerInvariant() -or [int64]$exe.size_bytes -ne [int64]$State.baseline.executable.size_bytes) { return $false }
        if (-not $original.exists -or $original.sha256 -ne ([string]$State.baseline.original_dxcompiler.sha256).ToLowerInvariant() -or [int64]$original.size_bytes -ne [int64]$State.baseline.original_dxcompiler.size_bytes) { return $false }
        foreach ($field in @('proxy_sha256', 'payload_sha256', 'original_dxcompiler_sha256')) {
            if (([string]$State.agp_dependency.$field).ToLowerInvariant() -ne ([string]$Candidate.$field).ToLowerInvariant()) { return $false }
        }
    }
    $agpState = Get-ContainedPath $Context 'AGP Native Hook/agp-install-state.json'
    $agpHash = if (Test-Path -LiteralPath $agpState) { Get-Sha256 $agpState } else { 'absent' }
    if (-not $agpRebasedProxyOnly -and ([string]$State.agp_dependency.state_sha256).ToLowerInvariant() -ne $agpHash) { return $false }
    foreach ($item in @($State.managed_files)) {
        $obs = Get-Observation $Context ([string]$item.relative_path)
        if ($item.relative_path -eq 'AWOW Universal Female Generation/awow_ufg.dll' -and -not [bool]$item.present) {
            if ($obs.exists) { return $false }
            continue
        }
        if ($item.relative_path -eq $Context.Manifest.target.active_dxcompiler_relative_path -and $agpRebasedProxyOnly) { continue }
        if (-not $item.present -or -not $obs.exists -or $obs.kind -ne 'file' -or $obs.sha256 -ne ([string]$item.installed_sha256).ToLowerInvariant() -or [int64]$obs.size_bytes -ne [int64]$item.installed_size_bytes) { return $false }
    }
    return $true
}

function New-Context {
    $root = Get-FullPath $TargetRoot
    $package = Get-FullPath $PackageRoot
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { Fail "TargetRoot must be an existing directory: $root" }
    if (-not (Test-Path -LiteralPath $package -PathType Container)) { Fail "PackageRoot must be an existing directory: $package" }
    $manifestPath = Join-Path $package 'Installer\release-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { Fail "Missing UFG release manifest: $manifestPath" }
    $manifest = Get-JsonObject $manifestPath
    if ($null -eq $manifest -or $manifest.schema_version -ne 1 -or $manifest.kind -ne 'ufg_release_manifest') { Fail 'Release manifest is not UFG schema-v1.' }
    $build = @($manifest.target.supported_builds)[0]
    if ($null -eq $build) { Fail 'Manifest has no supported CK3 build.' }
    $ctx = @{
        Root = $root
        PackageRoot = $package
        Manifest = $manifest
        ManifestPath = $manifestPath
        ManifestHash = Get-Sha256 $manifestPath
        Build = $build
        State = $null
        StateValid = $false
        StatePresent = $false
        Classification = $null
        TransactionId = [Guid]::NewGuid().ToString()
        StageRelative = ''
        QuarantineRelative = ''
        JournalPath = $null
        Journal = $null
        Snapshots = @{}
        Quarantined = New-Object Collections.Generic.List[object]
        ArtifactSources = @{}
        Result = $null
        Candidate = $null
        ReplaceProxy = $false
        ProxyOnlyCrossRelease = $false
    }
    Test-PathSafety $ctx $root
    $ctx.StageRelative = "$($manifest.target.journal_relative_directory)/$($ctx.TransactionId)/stage"
    $ctx.QuarantineRelative = "$($manifest.target.quarantine_relative_directory)/$($ctx.TransactionId)"
    $ctx.JournalPath = Get-ContainedPath $ctx "$($manifest.target.journal_relative_directory)/$($ctx.TransactionId).json"
    foreach ($artifact in @($manifest.artifacts)) {
        $source = Join-Path $package ([string]$artifact.relative_path -replace '/', '\')
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { $source = Join-Path $package ([string]$artifact.source_relative_path -replace '/', '\') }
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { Fail "Missing UFG package artifact: $($artifact.relative_path)" }
        $hash = Get-Sha256 $source
        if ($hash -ne ([string]$artifact.sha256).ToLowerInvariant()) { Fail "Package artifact hash mismatch: $($artifact.relative_path)" }
        $ctx.ArtifactSources[[string]$artifact.id] = $source
    }
    return $ctx
}

function Test-Preflight([hashtable]$Context) {
    if (Get-Process -Name 'ck3' -ErrorAction SilentlyContinue) { Fail 'Crusader Kings III is running; close ck3.exe before changing UFG files.' }
    Test-PathSafety $Context $Context.Root
    foreach ($relative in @('ck3.exe', $Context.Manifest.target.active_dxcompiler_relative_path, $Context.Manifest.target.original_dxcompiler_relative_path, $Context.Manifest.target.state_relative_path, $Context.Manifest.target.journal_relative_directory, $Context.Manifest.target.quarantine_relative_directory, 'AGP Native Hook/agp_parenthook.dll', 'AGP Native Hook/agp-install-state.json')) { [void](Get-ContainedPath $Context $relative) }
    $exe = Get-Observation $Context ([string]$Context.Manifest.target.executable_relative_path)
    if (-not $exe.exists -or $exe.kind -ne 'file' -or $exe.sha256 -ne ([string]$Context.Build.executable_sha256).ToLowerInvariant()) { Fail 'Unsupported or missing CK3 executable hash.' }
    $journalRoot = Get-ContainedPath $Context ([string]$Context.Manifest.target.journal_relative_directory)
    if (Test-Path -LiteralPath $journalRoot) {
        if (-not (Get-Item -LiteralPath $journalRoot).PSIsContainer -or @(Get-ChildItem -LiteralPath $journalRoot -Force).Count -gt 0) { Fail 'An incomplete UFG transaction journal exists; manual recovery is required.' }
    }
}

function Get-Classification([hashtable]$Context) {
    $statePath = Get-ContainedPath $Context ([string]$Context.Manifest.target.state_relative_path)
    $Context.StatePresent = Test-Path -LiteralPath $statePath
    $Context.State = $null
    $Context.StateValid = $false
    if ($Context.StatePresent) {
        $Context.State = Get-JsonObject $statePath
        $Context.StateValid = Test-UfgStateShape $Context $Context.State
        if (-not $Context.StateValid) {
            $Context.Classification = 'unknown_conflicting'
            return $Context.Classification
        }
    }
    $stateProxy = if ($Context.StateValid) { Get-ManagedItem $Context.State ([string]$Context.Manifest.target.active_dxcompiler_relative_path) } else { $null }
    $allowedActive = if ($null -ne $stateProxy) { [string]$stateProxy.installed_sha256 } else { [string]$Context.Manifest.artifacts[0].sha256 }
    $candidate = Get-AgpCandidate $Context $allowedActive
    $Context.Candidate = $candidate
    if ($Context.StateValid -and (Test-ManagedState $Context $Context.State $candidate)) {
        $Context.Classification = [string]$Context.State.status
        $active = Get-Observation $Context ([string]$Context.Manifest.target.active_dxcompiler_relative_path)
        $incoming = ([string]$Context.Manifest.artifacts[0].sha256).ToLowerInvariant()
        $Context.ProxyOnlyCrossRelease = ($Context.Classification -eq 'ufg_proxy_only' -and $null -ne $stateProxy -and $active.sha256 -eq ([string]$stateProxy.installed_sha256).ToLowerInvariant() -and $active.sha256 -ne $incoming)
        $Context.ReplaceProxy = ($Context.Classification -eq 'managed_ufg' -or $active.sha256 -ne $incoming)
        return $Context.Classification
    }
    if ($Context.StateValid) {
        $Context.Classification = 'unknown_conflicting'
        return $Context.Classification
    }
    if ($null -eq $candidate) {
        $Context.Classification = 'unknown_conflicting'
        return $Context.Classification
    }
    $active = Get-Observation $Context ([string]$Context.Manifest.target.active_dxcompiler_relative_path)
    $payload = Get-Observation $Context 'AWOW Universal Female Generation/awow_ufg.dll'
    $ufgHash = ([string]$Context.Manifest.artifacts[0].sha256).ToLowerInvariant()
    $payloadHash = ([string]$Context.Manifest.artifacts[1].sha256).ToLowerInvariant()
    if ($active.exists -and $active.sha256 -eq $ufgHash -and $payload.exists -and $payload.sha256 -eq $payloadHash) {
        $Context.Classification = 'manual_ufg'
        return $Context.Classification
    }
    if ($active.exists -and $active.sha256 -eq $ufgHash -and -not $payload.exists) {
        $Context.Classification = 'unknown_conflicting'
        return $Context.Classification
    }
    if ($payload.exists) {
        $Context.Classification = 'unknown_conflicting'
        return $Context.Classification
    }
    $Context.Classification = 'agp_ready'
    $Context.ReplaceProxy = $true
    return $Context.Classification
}

function Get-ExpectedConfirmation([hashtable]$Context) {
    if ($Operation -ne 'install') { return $null }
    switch ($Context.Classification) {
        'managed_ufg' { return 'UPGRADE_UFG_IN_PLACE' }
        'manual_ufg' { return 'ADOPT_UFG_LAYOUT' }
        'ufg_proxy_only' { if ($Context.ProxyOnlyCrossRelease) { return 'UPGRADE_UFG_IN_PLACE' }; return 'RE_ENABLE_UFG' }
        default { return $null }
    }
}

function Get-ConfirmationPrompt([hashtable]$Context) {
    switch ($Context.Classification) {
        'managed_ufg' {
            return [ordered]@{ title = 'UFG is already installed'; message = 'UFG is already managed here. Continue to replace its proxy and payload with this release?' }
        }
        'manual_ufg' {
            return [ordered]@{ title = 'Existing UFG files found'; message = 'Matching UFG files were installed manually. Continue to verify them and add installer management without replacing them?' }
        }
        'ufg_proxy_only' {
            if ($Context.ProxyOnlyCrossRelease) {
                return [ordered]@{ title = 'Disabled UFG upgrade found'; message = 'An older UFG proxy remains while UFG is disabled. Continue to replace it and install this release?' }
            }
            $active = Get-Observation $Context ([string]$Context.Manifest.target.active_dxcompiler_relative_path)
            $incoming = ([string]$Context.Manifest.artifacts[0].sha256).ToLowerInvariant()
            if ($active.sha256 -eq $incoming) {
                return [ordered]@{ title = 'UFG is currently disabled'; message = 'The UFG proxy remains, but its payload was removed. Continue to restore the payload and enable UFG?' }
            }
            return [ordered]@{ title = 'Compatible AGP replacement found'; message = 'UFG is disabled and a compatible standalone AGP proxy is active. Continue to install this UFG proxy and payload?' }
        }
        default { return $null }
    }
}

function Confirm-Transition([hashtable]$Context) {
    $expected = Get-ExpectedConfirmation $Context
    if ($null -eq $expected) { return $true }
    $answer = $Confirmation
    if ([string]::IsNullOrEmpty($answer) -and $Interactive) {
        $prompt = Get-ConfirmationPrompt $Context
        try {
            Add-Type -AssemblyName System.Windows.Forms
            $choice = [System.Windows.Forms.MessageBox]::Show(
                [string]$prompt.message,
                [string]$prompt.title,
                [System.Windows.Forms.MessageBoxButtons]::OKCancel,
                [System.Windows.Forms.MessageBoxIcon]::Question,
                [System.Windows.Forms.MessageBoxDefaultButton]::Button2
            )
        }
        catch {
            $Context.Result = [ordered]@{ operation = $Operation; classification = $Context.Classification; decision = 'abort'; next_state = $Context.Classification; message = 'The confirmation window could not be opened; no changes were made.' }
            return $false
        }
        if ($choice -eq [System.Windows.Forms.DialogResult]::OK) { return $true }
        $Context.Result = [ordered]@{ operation = $Operation; classification = $Context.Classification; decision = 'abort'; next_state = $Context.Classification; message = 'Installation cancelled; no changes were made.' }
        return $false
    }
    if ($answer -ne $expected) {
        $Context.Result = [ordered]@{ operation = $Operation; classification = $Context.Classification; decision = 'abort'; next_state = $Context.Classification; message = "Required confirmation was not supplied: $expected" }
        return $false
    }
    return $true
}

function Add-Snapshot([hashtable]$Context, [string]$RelativePath) {
    if ($Context.Snapshots.ContainsKey($RelativePath)) { return }
    $obs = Get-Observation $Context $RelativePath
    $safe = ($RelativePath -replace '/', '__')
    $stageRel = "$($Context.StageRelative)/snapshot/$safe"
    $stagePath = Get-ContainedPath $Context $stageRel
    $snapshot = [ordered]@{ relative_path = $RelativePath; stage_relative_path = $stageRel; before = $obs }
    if ($obs.exists) {
        if ($obs.kind -eq 'directory') {
            New-Item -ItemType Directory -Path (Split-Path -Parent $stagePath) -Force | Out-Null
            Copy-Item -LiteralPath (Get-ContainedPath $Context $RelativePath) -Destination $stagePath -Recurse -Force
        }
        else {
            New-Item -ItemType Directory -Path (Split-Path -Parent $stagePath) -Force | Out-Null
            Copy-Item -LiteralPath (Get-ContainedPath $Context $RelativePath) -Destination $stagePath -Force
        }
    }
    $Context.Snapshots[$RelativePath] = $snapshot
}

function New-JournalEntry([hashtable]$Context, [string]$RelativePath, [string]$Kind, [string]$OperationName, [string]$Staged, [string]$Owner) {
    $entry = [ordered]@{ relative_path = Get-CanonicalRelative $RelativePath; kind = $Kind; operation = $OperationName; before = Get-Observation $Context $RelativePath; staged_relative_path = Get-CanonicalRelative $Staged }
    if ($Owner) { $entry.ownership = $Owner }
    return $entry
}

function Get-PreservedAgpObservations([hashtable]$Context, $Candidate) {
    $paths = [ordered]@{}
    foreach ($relative in @('dxcompiler.dll', 'dxcompiler_original.dll', [string]$Candidate.payload_relative_path, [string]$Candidate.state_relative_path)) {
        $paths[$relative] = Get-Observation $Context $relative
    }
    return [ordered]@{ dependency_id = [string]$Candidate.id; paths = $paths }
}

function Assert-PreservedAgpObservations([hashtable]$Context, $Preserved, [switch]$SkipActive) {
    foreach ($entry in $Preserved.paths.GetEnumerator()) {
        $relative = [string]$entry.Key
        if ($SkipActive -and $relative -eq 'dxcompiler.dll') { continue }
        $beforeJson = $entry.Value | ConvertTo-Json -Compress -Depth 8
        $afterJson = (Get-Observation $Context $relative) | ConvertTo-Json -Compress -Depth 8
        if ($beforeJson -ne $afterJson) { Fail "Preserved dependency changed: $relative" }
    }
}

function New-InstallJournal([hashtable]$Context) {
    $entries = New-Object Collections.Generic.List[object]
    $active = [string]$Context.Manifest.target.active_dxcompiler_relative_path
    $payload = 'AWOW Universal Female Generation/awow_ufg.dll'
    $state = [string]$Context.Manifest.target.state_relative_path
    $activeOp = if ($Context.ReplaceProxy) { 'replace' } else { 'verify_only' }
    [void]$entries.Add((New-JournalEntry $Context $active 'file' $activeOp "$($Context.StageRelative)/package/dxcompiler.dll" 'managed'))
    $payloadOp = if ((Get-Observation $Context $payload).exists) { 'replace' } else { 'create' }
    [void]$entries.Add((New-JournalEntry $Context $payload 'file' $payloadOp "$($Context.StageRelative)/package/$payload" 'managed'))
    $stateOp = if ((Get-Observation $Context $state).exists) { 'replace' } else { 'create' }
    [void]$entries.Add((New-JournalEntry $Context $state 'file' $stateOp "$($Context.StageRelative)/state.json" 'managed'))
    foreach ($log in @($Context.Manifest.target.logs)) { [void]$entries.Add((New-JournalEntry $Context ([string]$log.relative_path) 'file' 'verify_only' "$($Context.StageRelative)/snapshot/$([string]$log.relative_path -replace '/', '__')" 'managed')) }
    $Context.Journal = [ordered]@{
        '$schema' = 'https://awow-ufg.invalid/schema/install-journal-v1.json'
        schema_version = 1
        kind = 'ufg_install_journal'
        transaction_id = $Context.TransactionId
        operation = 'install'
        source_state = $Context.Classification
        target_state = 'managed_ufg'
        phase = 'journal'
        target = [ordered]@{ game_id = 'crusader_kings_iii'; build_id = [string]$Context.Build.id; binaries_relative_path = 'binaries'; target_root_kind = 'steam_game_binaries' }
        entries = $entries.ToArray()
        preserved_agp = Get-PreservedAgpObservations $Context $Context.Candidate
    }
    Write-JsonFile $Context.JournalPath $Context.Journal
}

function Stage-Install([hashtable]$Context) {
    New-Item -ItemType Directory -Path (Get-ContainedPath $Context $Context.StageRelative) -Force | Out-Null
    foreach ($artifact in @($Context.Manifest.artifacts)) {
        $stageRel = "$($Context.StageRelative)/package/$([string]$artifact.relative_path)"
        $stagePath = Get-ContainedPath $Context $stageRel
        New-Item -ItemType Directory -Path (Split-Path -Parent $stagePath) -Force | Out-Null
        Copy-Item -LiteralPath $Context.ArtifactSources[[string]$artifact.id] -Destination $stagePath -Force
        $hash = Get-Sha256 $stagePath
        if ($hash -ne ([string]$artifact.sha256).ToLowerInvariant()) { Fail "Staged artifact hash mismatch: $($artifact.relative_path)" }
    }
}

function Copy-StagedArtifact([hashtable]$Context, [string]$RelativePath) {
    if ($WriteFaultAt -and $WriteFaultAt -eq $RelativePath) { Fail "Simulated write failure at $RelativePath" }
    $destination = Get-ContainedPath $Context $RelativePath
    $stage = Get-ContainedPath $Context "$($Context.StageRelative)/package/$RelativePath"
    if (Test-Path -LiteralPath $destination -PathType Container) { Fail "Artifact destination is a directory: $RelativePath" }
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath $stage -Destination $destination -Force
}

function New-UfgState([hashtable]$Context, $Candidate, [string]$Status, [string]$CreatedUtc, $OwnedState = $null) {
    $original = Get-Observation $Context ([string]$Context.Manifest.target.original_dxcompiler_relative_path)
    $exe = Get-Observation $Context 'ck3.exe'
    $agpState = Get-ContainedPath $Context 'AGP Native Hook/agp-install-state.json'
    $agpHash = if (Test-Path -LiteralPath $agpState) { Get-Sha256 $agpState } else { 'absent' }
    $now = [DateTime]::UtcNow.ToString('o')
    $release = [ordered]@{ id = [string]$Context.Manifest.release.id; version = [string]$Context.Manifest.release.version; manifest_sha256 = $Context.ManifestHash }
    $proxyHash = ([string]$Context.Manifest.artifacts[0].sha256).ToLowerInvariant()
    $proxySize = [int64]$Context.Manifest.artifacts[0].size_bytes
    $payloadHash = ([string]$Context.Manifest.artifacts[1].sha256).ToLowerInvariant()
    $payloadSize = [int64]$Context.Manifest.artifacts[1].size_bytes
    if ($null -ne $OwnedState) {
        $ownedProxy = Get-ManagedItem $OwnedState ([string]$Context.Manifest.target.active_dxcompiler_relative_path)
        $ownedPayload = Get-ManagedItem $OwnedState 'AWOW Universal Female Generation/awow_ufg.dll'
        if ($null -eq $ownedProxy -or $null -eq $ownedPayload) { Fail 'Owned UFG state is missing managed artifacts.' }
        $release = [ordered]@{ id = [string]$OwnedState.release.id; version = [string]$OwnedState.release.version; manifest_sha256 = [string]$OwnedState.release.manifest_sha256 }
        $proxyHash = ([string]$ownedProxy.installed_sha256).ToLowerInvariant(); $proxySize = [int64]$ownedProxy.installed_size_bytes
        $payloadHash = ([string]$ownedPayload.installed_sha256).ToLowerInvariant(); $payloadSize = [int64]$ownedPayload.installed_size_bytes
    }
    return [ordered]@{
        '$schema' = 'https://awow-ufg.invalid/schema/install-state-v1.json'
        schema_version = 1
        kind = 'ufg_install_state'
        status = $Status
        transaction_id = $Context.TransactionId
        release = $release
        target = [ordered]@{ game_id = 'crusader_kings_iii'; build_id = [string]$Context.Build.id; binaries_relative_path = 'binaries'; executable_relative_path = 'ck3.exe'; target_root_kind = 'steam_game_binaries' }
        baseline = [ordered]@{ original_dxcompiler = [ordered]@{ relative_path = [string]$Context.Manifest.target.original_dxcompiler_relative_path; sha256 = $original.sha256; size_bytes = [int64]$original.size_bytes; ownership = 'steam' }; executable = [ordered]@{ relative_path = 'ck3.exe'; sha256 = $exe.sha256; size_bytes = [int64]$exe.size_bytes; ownership = 'steam' } }
        agp_dependency = [ordered]@{ build_id = [string]$Candidate.id; version = [string]$Candidate.version; proxy_relative_path = [string]$Candidate.proxy_relative_path; proxy_sha256 = ([string]$Candidate.proxy_sha256).ToLowerInvariant(); payload_relative_path = [string]$Candidate.payload_relative_path; payload_sha256 = ([string]$Candidate.payload_sha256).ToLowerInvariant(); original_dxcompiler_sha256 = ([string]$Candidate.original_dxcompiler_sha256).ToLowerInvariant(); state_relative_path = [string]$Candidate.state_relative_path; state_sha256 = $agpHash }
        managed_files = @(
            [ordered]@{ relative_path = [string]$Context.Manifest.target.active_dxcompiler_relative_path; role = 'ufg_proxy'; ownership = 'managed'; installed_sha256 = $proxyHash; installed_size_bytes = $proxySize; present = $true; restore = [ordered]@{ action = 'leave_managed_file' } },
            [ordered]@{ relative_path = 'AWOW Universal Female Generation/awow_ufg.dll'; role = 'ufg_payload'; ownership = 'managed'; installed_sha256 = $payloadHash; installed_size_bytes = $payloadSize; present = ($Status -eq 'managed_ufg'); restore = [ordered]@{ action = 'remove_managed_file' } }
        )
        quarantined_files = @()
        foreign_cleanup = [ordered]@{ kind = 'none'; quarantine_relative_path = [string]$Context.Manifest.target.quarantine_relative_directory; removed_paths = @(); uninstall_policy = 'none' }
        created_utc = if ($CreatedUtc) { $CreatedUtc } else { $now }
        updated_utc = $now
    }
}

function Verify-Install([hashtable]$Context, $State, $Candidate) {
    foreach ($artifact in @($Context.Manifest.artifacts)) {
        $obs = Get-Observation $Context ([string]$artifact.relative_path)
        if (-not $obs.exists -or $obs.kind -ne 'file' -or $obs.sha256 -ne ([string]$artifact.sha256).ToLowerInvariant()) { Fail "Installed UFG artifact verification failed: $($artifact.relative_path)" }
    }
    $statePath = Get-ContainedPath $Context ([string]$Context.Manifest.target.state_relative_path)
    Write-JsonFile $statePath $State
    $readBack = Get-JsonObject $statePath
    if (-not (Test-UfgStateShape $Context $readBack) -or -not (Test-ManagedState $Context $readBack $Candidate)) { Fail 'Committed UFG state failed ownership/hash verification.' }
}

function Remove-Exact([hashtable]$Context, [string]$RelativePath, [bool]$Recursive) {
    $path = Get-ContainedPath $Context $RelativePath
    if (-not (Test-Path -LiteralPath $path)) { return }
    if ($Recursive) { Remove-Item -LiteralPath $path -Recurse -Force }
    else { Remove-Item -LiteralPath $path -Force }
}

function Restore-Snapshots([hashtable]$Context) {
    foreach ($snapshot in ($Context.Snapshots.Values | Sort-Object { $_.relative_path.Length } -Descending)) {
        $target = Get-ContainedPath $Context ([string]$snapshot.relative_path)
        if (Test-Path -LiteralPath $target) {
            $item = Get-Item -LiteralPath $target -Force
            if ($item.PSIsContainer) { Remove-Item -LiteralPath $target -Recurse -Force } else { Remove-Item -LiteralPath $target -Force }
        }
    }
    foreach ($snapshot in ($Context.Snapshots.Values | Sort-Object { $_.relative_path.Length })) {
        if (-not $snapshot.before.exists) { continue }
        $source = Get-ContainedPath $Context ([string]$snapshot.stage_relative_path)
        $target = Get-ContainedPath $Context ([string]$snapshot.relative_path)
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        if ($snapshot.before.kind -eq 'directory') { Copy-Item -LiteralPath $source -Destination $target -Recurse -Force } else { Copy-Item -LiteralPath $source -Destination $target -Force }
    }
}

function Commit-Transaction([hashtable]$Context) {
    $journalDir = Split-Path -Parent $Context.JournalPath
    if (Test-Path -LiteralPath $journalDir) { Remove-Item -LiteralPath $journalDir -Recurse -Force }
    $journalRoot = Split-Path -Parent $journalDir
    if ((Test-Path -LiteralPath $journalRoot -PathType Container) -and @(Get-ChildItem -LiteralPath $journalRoot -Force).Count -eq 0) { Remove-Item -LiteralPath $journalRoot -Force }
}

function Remove-FailedTransaction([hashtable]$Context) {
    $journalDir = Split-Path -Parent $Context.JournalPath
    if (Test-Path -LiteralPath $journalDir) { Remove-Item -LiteralPath $journalDir -Recurse -Force }
    $journalRoot = Split-Path -Parent $journalDir
    if ((Test-Path -LiteralPath $journalRoot -PathType Container) -and @(Get-ChildItem -LiteralPath $journalRoot -Force).Count -eq 0) { Remove-Item -LiteralPath $journalRoot -Force }
    $ufgRoot = Get-ContainedPath $Context 'AWOW Universal Female Generation'
    if ((Test-Path -LiteralPath $ufgRoot -PathType Container) -and @(Get-ChildItem -LiteralPath $ufgRoot -Force).Count -eq 0) { Remove-Item -LiteralPath $ufgRoot -Force }
}

function Invoke-Install([hashtable]$Context) {
    foreach ($relative in @($Context.Manifest.target.active_dxcompiler_relative_path, 'AWOW Universal Female Generation/awow_ufg.dll', $Context.Manifest.target.state_relative_path)) { Add-Snapshot $Context ([string]$relative) }
    foreach ($log in @($Context.Manifest.target.logs)) { Add-Snapshot $Context ([string]$log.relative_path) }
    New-InstallJournal $Context
    $stateProxy = if ($Context.StateValid) { Get-ManagedItem $Context.State ([string]$Context.Manifest.target.active_dxcompiler_relative_path) } else { $null }
    $allowedActive = if ($null -ne $stateProxy) { [string]$stateProxy.installed_sha256 } else { [string]$Context.Manifest.artifacts[0].sha256 }
    $candidate = Get-AgpCandidate $Context $allowedActive
    if ($null -eq $candidate) { Fail 'Compatible AGP dependency changed before mutation.' }
    $created = if ($Context.StateValid) { [string]$Context.State.created_utc } else { '' }
    try {
        $Context.Journal.phase = 'stage'; Write-JsonFile $Context.JournalPath $Context.Journal
        Stage-Install $Context
        $Context.Journal.phase = 'mutate'; Write-JsonFile $Context.JournalPath $Context.Journal
        if ($Context.ReplaceProxy) { Copy-StagedArtifact $Context 'dxcompiler.dll' }
        if ($Context.Classification -ne 'manual_ufg') { Copy-StagedArtifact $Context 'AWOW Universal Female Generation/awow_ufg.dll' }
        $Context.Journal.phase = 'verify'; Write-JsonFile $Context.JournalPath $Context.Journal
        $state = New-UfgState $Context $candidate 'managed_ufg' $created
        Verify-Install $Context $state $candidate
        Assert-PreservedAgpObservations $Context $Context.Journal.preserved_agp -SkipActive
        $Context.Journal.phase = 'commit'; Write-JsonFile $Context.JournalPath $Context.Journal
        Commit-Transaction $Context
        $Context.Result = [ordered]@{ operation = 'install'; classification = $Context.Classification; decision = 'proceed'; next_state = 'managed_ufg'; transaction_id = $Context.TransactionId; message = 'UFG installed' }
    }
    catch {
        try {
            Restore-Snapshots $Context
            Remove-FailedTransaction $Context
            $Context.Result = [ordered]@{ operation = 'install'; classification = $Context.Classification; decision = 'rollback'; next_state = $Context.Classification; transaction_id = $Context.TransactionId; message = $_.Exception.Message }
        }
        catch {
            $Context.Result = [ordered]@{ operation = 'install'; classification = $Context.Classification; decision = 'manual_recovery_required'; next_state = 'manual_recovery_required'; transaction_id = $Context.TransactionId; message = $_.Exception.Message }
        }
    }
}

function Invoke-Uninstall([hashtable]$Context) {
    foreach ($relative in @($Context.Manifest.target.active_dxcompiler_relative_path, 'AWOW Universal Female Generation/awow_ufg.dll', $Context.Manifest.target.state_relative_path)) { Add-Snapshot $Context ([string]$relative) }
    foreach ($log in @($Context.Manifest.target.logs)) { Add-Snapshot $Context ([string]$log.relative_path) }
    $stateProxy = Get-ManagedItem $Context.State ([string]$Context.Manifest.target.active_dxcompiler_relative_path)
    $allowedActive = if ($null -ne $stateProxy) { [string]$stateProxy.installed_sha256 } else { '' }
    $candidate = Get-AgpCandidate $Context $allowedActive
    if ($null -eq $candidate) { Fail 'Compatible AGP dependency changed before mutation.' }
    $Context.Journal = [ordered]@{
        '$schema' = 'https://awow-ufg.invalid/schema/install-journal-v1.json'; schema_version = 1; kind = 'ufg_install_journal'; transaction_id = $Context.TransactionId; operation = 'uninstall'; source_state = $Context.Classification; target_state = 'ufg_proxy_only'; phase = 'journal'; target = [ordered]@{ game_id = 'crusader_kings_iii'; build_id = [string]$Context.Build.id; binaries_relative_path = 'binaries'; target_root_kind = 'steam_game_binaries' }; entries = @((New-JournalEntry $Context 'dxcompiler.dll' 'file' 'verify_only' "$($Context.StageRelative)/snapshot/dxcompiler.dll" 'managed'), (New-JournalEntry $Context 'AWOW Universal Female Generation/awow_ufg.dll' 'file' 'remove' "$($Context.StageRelative)/snapshot/AWOW Universal Female Generation__awow_ufg.dll" 'managed'), (New-JournalEntry $Context ([string]$Context.Manifest.target.state_relative_path) 'file' 'replace' "$($Context.StageRelative)/state.json" 'managed')); preserved_agp = Get-PreservedAgpObservations $Context $candidate
    }
    foreach ($log in @($Context.Manifest.target.logs)) { $Context.Journal.entries += ,(New-JournalEntry $Context ([string]$log.relative_path) 'file' 'remove' "$($Context.StageRelative)/snapshot/$([string]$log.relative_path -replace '/', '__')" 'managed') }
    Write-JsonFile $Context.JournalPath $Context.Journal
    try {
        $Context.Journal.phase = 'mutate'; Write-JsonFile $Context.JournalPath $Context.Journal
        $payload = Get-Observation $Context 'AWOW Universal Female Generation/awow_ufg.dll'
        $payloadItem = Get-ManagedItem $Context.State 'AWOW Universal Female Generation/awow_ufg.dll'
        if ($null -eq $payloadItem -or -not $payload.exists -or $payload.sha256 -ne ([string]$payloadItem.installed_sha256).ToLowerInvariant() -or [int64]$payload.size_bytes -ne [int64]$payloadItem.installed_size_bytes) { Fail 'UFG payload hash changed; refusing uninstall.' }
        Remove-Exact $Context 'AWOW Universal Female Generation/awow_ufg.dll' $false
        foreach ($log in @($Context.Manifest.target.logs)) { Remove-Exact $Context ([string]$log.relative_path) $false }
        $activeAfter = Get-Observation $Context 'dxcompiler.dll'
        $activeBefore = $Context.Snapshots['dxcompiler.dll'].before
        if ($activeAfter.sha256 -ne $activeBefore.sha256 -or [int64]$activeAfter.size_bytes -ne [int64]$activeBefore.size_bytes) { Fail 'Active dxcompiler.dll changed during uninstall.' }
        $state = New-UfgState $Context $candidate 'ufg_proxy_only' ([string]$Context.State.created_utc) $Context.State
        $Context.Journal.phase = 'verify'; Write-JsonFile $Context.JournalPath $Context.Journal
        $statePath = Get-ContainedPath $Context ([string]$Context.Manifest.target.state_relative_path)
        Write-JsonFile $statePath $state
        $readBack = Get-JsonObject $statePath
        if (-not (Test-UfgStateShape $Context $readBack) -or (Get-Observation $Context 'AWOW Universal Female Generation/awow_ufg.dll').exists) { Fail 'Proxy-only state verification failed.' }
        Assert-PreservedAgpObservations $Context $Context.Journal.preserved_agp
        $Context.Journal.phase = 'commit'; Write-JsonFile $Context.JournalPath $Context.Journal
        Commit-Transaction $Context
        $Context.Result = [ordered]@{ operation = 'uninstall'; classification = $Context.Classification; decision = 'proceed'; next_state = 'ufg_proxy_only'; transaction_id = $Context.TransactionId; message = 'UFG payload disabled; active UFG proxy remains unchanged and AGP continues loading alone' }
    }
    catch {
        try {
            Restore-Snapshots $Context
            Remove-FailedTransaction $Context
            $Context.Result = [ordered]@{ operation = 'uninstall'; classification = $Context.Classification; decision = 'rollback'; next_state = 'managed_ufg'; transaction_id = $Context.TransactionId; message = $_.Exception.Message }
        }
        catch {
            $Context.Result = [ordered]@{ operation = 'uninstall'; classification = $Context.Classification; decision = 'manual_recovery_required'; next_state = 'manual_recovery_required'; transaction_id = $Context.TransactionId; message = $_.Exception.Message }
        }
    }
}

function Write-Result([hashtable]$Context) {
    if ($null -eq $Context.Result) { $Context.Result = [ordered]@{ operation = $Operation; classification = $Context.Classification; decision = 'reject'; next_state = $Context.Classification } }
    if ($Json) { [Console]::Out.WriteLine(($Context.Result | ConvertTo-Json -Depth 16)) }
    else {
        [Console]::Out.WriteLine(("UFG {0}: {1} ({2})" -f $Context.Result.operation, $Context.Result.decision, $Context.Result.classification))
        if ($Context.Result.message) { [Console]::Out.WriteLine([string]$Context.Result.message) }
    }
    if ($Context.Result.decision -in @('proceed', 'no_op')) { return 0 }
    if ($Context.Result.decision -in @('abort', 'reject')) { return 2 }
    return 1
}

$ctx = $null
try {
    $ctx = New-Context
    Test-Preflight $ctx
    Get-Classification $ctx | Out-Null
    if ($Operation -eq 'install' -and $ctx.Classification -eq 'unknown_conflicting') {
        $ctx.Result = [ordered]@{ operation = 'install'; classification = 'unknown_conflicting'; decision = 'reject'; next_state = 'unknown_conflicting'; message = 'No exact compatible AGP/UFG layout was found; install compatible AGP first or resolve drift manually.' }
        exit (Write-Result $ctx)
    }
    if ($Operation -eq 'uninstall' -and $ctx.Classification -in @('unknown_conflicting', 'manual_ufg')) {
        $ctx.Result = [ordered]@{ operation = 'uninstall'; classification = $ctx.Classification; decision = 'reject'; next_state = $ctx.Classification; message = 'UFG layout is not state-owned or has drifted; active dxcompiler.dll is left unchanged.' }
        exit (Write-Result $ctx)
    }
    if ($Operation -eq 'uninstall' -and $ctx.Classification -in @('agp_ready', 'ufg_proxy_only')) {
        $ctx.Result = [ordered]@{ operation = 'uninstall'; classification = $ctx.Classification; decision = 'no_op'; next_state = $ctx.Classification; message = 'UFG is not enabled; active UFG/AGP files remain unchanged.' }
        exit (Write-Result $ctx)
    }
    if (-not (Confirm-Transition $ctx)) { exit (Write-Result $ctx) }
    if ($Operation -eq 'install') { Invoke-Install $ctx } else { Invoke-Uninstall $ctx }
    exit (Write-Result $ctx)
}
catch {
    $result = [ordered]@{ operation = $Operation; decision = 'reject'; next_state = 'manual_recovery_required'; message = $_.Exception.Message }
    if ($Json) { [Console]::Out.WriteLine(($result | ConvertTo-Json -Depth 8)) } else { [Console]::Out.WriteLine(("UFG {0}: reject" -f $Operation)); [Console]::Out.WriteLine([string]$_.Exception.Message) }
    exit 2
}
