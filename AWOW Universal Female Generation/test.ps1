[CmdletBinding()]
param([string]$ToolchainPath)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'build.ps1') -ToolchainPath $ToolchainPath
$nativeTestSources=@('tests/native_tests.cpp','src/ufg_generation.cpp','src/ufg_history.cpp','src/ufg_build_profile.cpp','src/ufg_patch_runtime.cpp') | ForEach-Object { '"'+(Join-Path $scriptRoot $_)+'"' }
$nativeTestOutput=Join-Path $buildDirectory 'ufg-native-tests.exe'
Push-Location $buildDirectory
try {
    Invoke-VcCommand $vcVarsAll ("cl.exe /nologo /std:c++17 /EHsc /O2 /I `"$buildDirectory`" /I `"$scriptRoot/src`" "+($nativeTestSources -join ' ')+" /link bcrypt.lib /OUT:`"$nativeTestOutput`"") $toolchain
    & $nativeTestOutput
    if ($LASTEXITCODE -ne 0) {throw 'Native UFG tests failed.'}
} finally {Pop-Location}
