[CmdletBinding()]
param(
	[Alias('VsDevCmdPath')]
	[string]$VcVarsAllPath,
	[string]$ToolchainPath,
	[switch]$Clean
)

$ErrorActionPreference = 'Stop'

function Read-ToolchainContract {
	param([string]$Path)
	if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Native toolchain contract was not found: $Path" }
	$contract = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
	if ($contract.schema_version -ne 1 -or $contract.kind -ne 'ufg_native_toolchain') { throw 'Unsupported UFG native toolchain contract.' }
	foreach ($property in @('github_actions_runner', 'visual_studio_version_range', 'vc_tools_version', 'windows_sdk_version', 'host_architecture', 'target_architecture', 'vcvars_architecture')) {
		if (-not [string]$contract.$property) { throw "Native toolchain contract is missing $property." }
	}
	if ($contract.host_architecture -ne 'x64' -or $contract.target_architecture -ne 'x64' -or $contract.vcvars_architecture -ne 'amd64') { throw 'UFG native releases require the pinned x64 host and target toolchain.' }
	return $contract
}

function Resolve-VcVarsAll {
	param([string]$RequestedPath, [string]$VisualStudioVersionRange)
	if ($RequestedPath) {
		$resolved = [IO.Path]::GetFullPath($RequestedPath)
		if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) { throw "The requested Visual Studio vcvarsall file was not found: $resolved" }
		return $resolved
	}
	$vswhereCandidates = @(
		(Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'),
		(Join-Path $env:ProgramFiles 'Microsoft Visual Studio\Installer\vswhere.exe')
	) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
	foreach ($vswhere in $vswhereCandidates) {
		$installation = (& $vswhere -latest -version $VisualStudioVersionRange -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null | Select-Object -First 1)
		if ($LASTEXITCODE -eq 0 -and $installation) {
			$candidate = Join-Path $installation.Trim() 'VC\Auxiliary\Build\vcvarsall.bat'
			if (Test-Path -LiteralPath $candidate -PathType Leaf) { return [IO.Path]::GetFullPath($candidate) }
		}
	}
	$knownInstallations = @(${env:ProgramFiles}, ${env:ProgramFiles(x86)}) | Where-Object { $_ } | ForEach-Object { Join-Path $_ 'Microsoft Visual Studio\2022' } | Where-Object { Test-Path -LiteralPath $_ -PathType Container }
	foreach ($root in $knownInstallations) {
		foreach ($edition in @('Community', 'Professional', 'Enterprise', 'BuildTools')) {
			$candidate = Join-Path $root "$edition\VC\Auxiliary\Build\vcvarsall.bat"
			if (Test-Path -LiteralPath $candidate -PathType Leaf) { return [IO.Path]::GetFullPath($candidate) }
		}
	}
	throw 'The pinned Visual Studio 2022 x64 C++ build tools were not found. Install the VC x64 workload or pass -VcVarsAllPath.'
}

function Invoke-VcCommand {
	param([string]$EnvironmentCommand, [string]$CommandLine, [object]$Toolchain)
	$commandFile = Join-Path ([IO.Path]::GetTempPath()) ("ufg-native-build-{0}.cmd" -f [Guid]::NewGuid().ToString('N'))
	$contents = @(
		'@echo off',
		("call `"{0}`" {1} {2} -vcvars_ver={3}" -f $EnvironmentCommand, $Toolchain.vcvars_architecture, $Toolchain.windows_sdk_version, $Toolchain.vc_tools_version),
		'if errorlevel 1 exit /b %errorlevel%',
		("if /I not `"%VCToolsVersion:\=%`"==`"{0}`" (echo ERROR: Expected VCToolsVersion {0}, got %VCToolsVersion% & exit /b 1)" -f $Toolchain.vc_tools_version),
		("if /I not `"%WindowsSDKVersion:\=%`"==`"{0}`" (echo ERROR: Expected WindowsSDKVersion {0}, got %WindowsSDKVersion% & exit /b 1)" -f $Toolchain.windows_sdk_version),
		$CommandLine
	) -join "`r`n"
	[IO.File]::WriteAllText($commandFile, $contents + "`r`n", [Text.Encoding]::ASCII)
	try { & $env:ComSpec /d /c $commandFile; $exitCode = $LASTEXITCODE }
	finally { Remove-Item -LiteralPath $commandFile -Force -ErrorAction SilentlyContinue }
	if ($exitCode -ne 0) { throw "Native compiler command failed with exit code $exitCode." }
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ToolchainPath) { $ToolchainPath = Join-Path $scriptRoot 'toolchain.json' }
$toolchain = Read-ToolchainContract ([IO.Path]::GetFullPath($ToolchainPath))
$vcVarsAll = Resolve-VcVarsAll $VcVarsAllPath $toolchain.visual_studio_version_range
$buildDirectory = Join-Path $scriptRoot 'build'
$payloadDirectory = Join-Path $buildDirectory 'AWOW Universal Female Generation'
$payloadOutput = Join-Path $payloadDirectory 'awow_ufg.dll'
$loaderOutput = Join-Path $buildDirectory 'dxcompiler.dll'
$definition = Join-Path $scriptRoot 'dxcompiler_proxy.def'
$versionSource = Join-Path $scriptRoot 'version.rc'
$proxyVersionResource = Join-Path $buildDirectory 'ufg_proxy_version.res'
$payloadVersionResource = Join-Path $buildDirectory 'ufg_payload_version.res'
$payloadSources = @('ufg_generation_hook.cpp', 'ufg_patch_runtime.cpp', 'ufg_generation.cpp', 'ufg_history.cpp') | ForEach-Object { Join-Path $scriptRoot "src\$_" }
$loaderSources = @('ufg_dxcompiler_loader.cpp', 'ufg_patch_runtime.cpp') | ForEach-Object { Join-Path $scriptRoot "src\$_" }

foreach ($source in @($payloadSources) + $loaderSources + $definition + $versionSource) {
	if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Required native build input is missing: $source" }
}
New-Item -ItemType Directory -Force -Path $payloadDirectory | Out-Null
$intermediateFiles = @(
	'awow_ufg.exp', 'awow_ufg.lib', 'dxcompiler.exp', 'dxcompiler.lib',
	'ufg_generation_hook.obj', 'ufg_patch_runtime.obj', 'ufg_generation.obj', 'ufg_history.obj',
	'ufg_dxcompiler_loader.obj', 'ufg_proxy_version.res', 'ufg_payload_version.res'
) | ForEach-Object { Join-Path $buildDirectory $_ }
if ($Clean) { Remove-Item -LiteralPath (@($intermediateFiles) + @($loaderOutput, $payloadOutput)) -Force -ErrorAction SilentlyContinue }

$payloadArguments = ($payloadSources | ForEach-Object { '"' + $_ + '"' }) -join ' '
$loaderArguments = ($loaderSources | ForEach-Object { '"' + $_ + '"' }) -join ' '
$payloadImportLibrary = Join-Path $buildDirectory 'awow_ufg.lib'
$loaderImportLibrary = Join-Path $buildDirectory 'dxcompiler.lib'
Push-Location $buildDirectory
try {
	Write-Host ("Pinned native toolchain: runner {0}, MSVC {1}, Windows SDK {2}, x64" -f $toolchain.github_actions_runner, $toolchain.vc_tools_version, $toolchain.windows_sdk_version)
	Write-Host 'GitHub Actions output is the canonical release artifact; local output is for verification and smoke testing.'
	Invoke-VcCommand $vcVarsAll "rc.exe /nologo /dUFG_PROXY /fo `"$proxyVersionResource`" `"$versionSource`"" $toolchain
	Invoke-VcCommand $vcVarsAll "rc.exe /nologo /fo `"$payloadVersionResource`" `"$versionSource`"" $toolchain
	Invoke-VcCommand $vcVarsAll "cl.exe /nologo /std:c++17 /EHsc /LD /O2 $payloadArguments `"$payloadVersionResource`" /link /Brepro /OUT:`"$payloadOutput`" /IMPLIB:`"$payloadImportLibrary`" bcrypt.lib" $toolchain
	Invoke-VcCommand $vcVarsAll "cl.exe /nologo /std:c++17 /EHsc /LD /O2 $loaderArguments `"$proxyVersionResource`" /link /Brepro /DEF:`"$definition`" /OUT:`"$loaderOutput`" /IMPLIB:`"$loaderImportLibrary`" bcrypt.lib" $toolchain
}
finally { Pop-Location }

foreach ($output in @($loaderOutput, $payloadOutput)) {
	if (-not (Test-Path -LiteralPath $output -PathType Leaf)) { throw "Native build completed without producing $output" }
	$hash = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()
	$size = (Get-Item -LiteralPath $output).Length
	Write-Host ("Built {0} ({1} bytes, SHA-256 {2})" -f $output, $size, $hash)
}
Remove-Item -LiteralPath $intermediateFiles -Force -ErrorAction SilentlyContinue
