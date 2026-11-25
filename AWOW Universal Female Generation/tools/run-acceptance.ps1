[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$GameExecutable,
    [ValidateSet('baseline','setup','reload','menu')][string]$Mode='setup',
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$SaveName='ufg_121_acceptance',
    [switch]$NormalMode,
    [switch]$PrepareOnly
)
$ErrorActionPreference='Stop'
$nativeRoot=Split-Path -Parent $PSScriptRoot
$userRoot=Join-Path $nativeRoot 'build/ck3-user'
$fixtureRoot=Join-Path $nativeRoot 'native_test_mod'
$overlayRoot=Join-Path $userRoot 'mod/ufg-controls'
if ($Mode -eq 'baseline' -and -not $PSBoundParameters.ContainsKey('SaveName')) {$SaveName='ufg_121_baseline'}
if (-not (Test-Path -LiteralPath $GameExecutable -PathType Leaf)) {throw 'CK3 executable is missing.'}
if ((Get-Process ck3 -ErrorAction SilentlyContinue) -and -not $PrepareOnly) {throw 'Close CK3 before starting another acceptance process.'}
if ($Mode -eq 'reload' -and -not (Test-Path -LiteralPath (Join-Path $userRoot "save games/$SaveName.ck3") -PathType Leaf)) {throw "Acceptance save is missing: $SaveName"}
New-Item -ItemType Directory -Force -Path (Join-Path $overlayRoot 'gui') | Out-Null
$encoding=[Text.UTF8Encoding]::new($true)
$fixturePath=$fixtureRoot -replace '\\','/'
$overlayPath=$overlayRoot -replace '\\','/'
[IO.File]::WriteAllText((Join-Path $userRoot 'mod/ufg-native-test.mod'),"name=`"UFG Native Acceptance Fixtures`"`nsupported_version=`"1.21.0.3`"`npath=`"$fixturePath`"`n",$encoding)
[IO.File]::WriteAllText((Join-Path $userRoot 'mod/ufg-controls.mod'),"name=`"UFG Disposable Controls`"`nsupported_version=`"1.21.0.3`"`npath=`"$overlayPath`"`n",$encoding)
[IO.File]::WriteAllText((Join-Path $userRoot 'dlc_load.json'),'{"enabled_mods":["mod/ufg-native-test.mod","mod/ufg-controls.mod"],"disabled_dlcs":[]}',[Text.UTF8Encoding]::new($false))
$panel=[IO.File]::ReadAllText((Join-Path $fixtureRoot 'gui/ufg_acceptance.gui')).Replace('save ufg_121_acceptance',"save $SaveName")
[IO.File]::WriteAllText((Join-Path $overlayRoot 'gui/ufg_acceptance.gui'),$panel,$encoding)
if ($PrepareOnly) {Write-Output "Prepared UFG disposable user data: $userRoot";return}
$arguments=@('-skip_checksum','-disable_encyclopedia',('-userdir="'+$userRoot+'"'),'-window_title="UFG 1.21 Acceptance"')
if (-not $NormalMode) {$arguments+='-debug_mode'}
if ($Mode -in @('baseline','setup')) {$arguments+=@('-skip','-play=k_england','-bookmark=bm_1066_hastings')}
if ($Mode -eq 'reload') {$arguments+="-loadsave=$SaveName"}
$process=Start-Process -FilePath $GameExecutable -ArgumentList $arguments -WorkingDirectory (Split-Path -Parent $GameExecutable) -PassThru
Write-Output "Acceptance process: $($process.Id); mode: $Mode; isolated user data: $userRoot"
