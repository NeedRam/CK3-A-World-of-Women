$ErrorActionPreference = 'Stop'

$vsDevCmd = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat'
if (-not (Test-Path $vsDevCmd)) {
	throw "Visual Studio developer prompt was not found at $vsDevCmd"
}

$payloadSources = @(
	(Join-Path $PSScriptRoot 'src\ufg_generation_hook.cpp'),
	(Join-Path $PSScriptRoot 'src\ufg_patch_runtime.cpp'),
	(Join-Path $PSScriptRoot 'src\ufg_generation.cpp'),
	(Join-Path $PSScriptRoot 'src\ufg_history.cpp')
)
$loaderSources = @(
	(Join-Path $PSScriptRoot 'src\ufg_dxcompiler_loader.cpp'),
	(Join-Path $PSScriptRoot 'src\ufg_patch_runtime.cpp')
)
$definition = Join-Path $PSScriptRoot 'dxcompiler_proxy.def'
$buildDirectory = Join-Path $PSScriptRoot 'build'
$payloadDirectory = Join-Path $buildDirectory 'AWOW Universal Female Generation'
$payloadOutput = Join-Path $payloadDirectory 'awow_ufg.dll'
$loaderOutput = Join-Path $buildDirectory 'dxcompiler.dll'

New-Item -ItemType Directory -Force $payloadDirectory | Out-Null

$payloadSourceArguments = ($payloadSources | ForEach-Object { '"' + $_ + '"' }) -join ' '
$loaderSourceArguments = ($loaderSources | ForEach-Object { '"' + $_ + '"' }) -join ' '
Push-Location $buildDirectory
try {
	cmd.exe /c "call `"$vsDevCmd`" -arch=x64 -host_arch=x64 >nul && cl.exe /nologo /std:c++17 /EHsc /LD /O2 $payloadSourceArguments /link /OUT:`"$payloadOutput`" /IMPLIB:`"$buildDirectory\awow_ufg.lib`" bcrypt.lib"
	if ($LASTEXITCODE -ne 0) { throw 'UFG payload build failed.' }

	cmd.exe /c "call `"$vsDevCmd`" -arch=x64 -host_arch=x64 >nul && cl.exe /nologo /std:c++17 /EHsc /LD /O2 $loaderSourceArguments /link /DEF:`"$definition`" /OUT:`"$loaderOutput`" /IMPLIB:`"$buildDirectory\dxcompiler.lib`" bcrypt.lib"
	if ($LASTEXITCODE -ne 0) { throw 'DXCompiler loader build failed.' }
}
finally {
	Pop-Location
}

Remove-Item -Force -ErrorAction SilentlyContinue `
	(Join-Path $buildDirectory 'awow_ufg.exp'), `
	(Join-Path $buildDirectory 'awow_ufg.lib'), `
	(Join-Path $buildDirectory 'ufg_generation_hook.obj'), `
	(Join-Path $buildDirectory 'ufg_patch_runtime.obj'), `
	(Join-Path $buildDirectory 'ufg_generation.obj'), `
	(Join-Path $buildDirectory 'ufg_history.obj'), `
	(Join-Path $buildDirectory 'ufg_dxcompiler_loader.obj'), `
	(Join-Path $buildDirectory 'dxcompiler.exp'), `
	(Join-Path $buildDirectory 'dxcompiler.lib')
Write-Host "Built $loaderOutput and $payloadOutput"
