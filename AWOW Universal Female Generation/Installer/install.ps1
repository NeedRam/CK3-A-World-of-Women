[CmdletBinding()]
param(
    [string]$TargetRoot,
    [string]$PackageRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Confirmation,
    [switch]$Interactive,
    [switch]$Json,
    [string]$WriteFaultAt,
    [switch]$SkipElevationCheck
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($TargetRoot)) {
    $programFilesX86 = ${env:ProgramFiles(x86)}
    if ([string]::IsNullOrWhiteSpace($programFilesX86)) { $programFilesX86 = ${env:ProgramFiles} }
    $TargetRoot = Join-Path $programFilesX86 'Steam\steamapps\common\Crusader Kings III\binaries'
}

if (-not $SkipElevationCheck -and [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath), '-TargetRoot', ('"{0}"' -f $TargetRoot), '-PackageRoot', ('"{0}"' -f $PackageRoot), '-Interactive')
        if ($Confirmation) { $arguments += @('-Confirmation', ('"{0}"' -f $Confirmation)) }
        if ($WriteFaultAt) { $arguments += @('-WriteFaultAt', ('"{0}"' -f $WriteFaultAt)) }
        try {
            $child = Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $arguments -Wait -PassThru
            exit ([int]$child.ExitCode)
        }
        catch {
            Write-Error "Administrator elevation failed: $($_.Exception.Message)"
            exit 1
        }
    }
}

& (Join-Path $PSScriptRoot 'powershell\engine.ps1') -Operation install -TargetRoot $TargetRoot -PackageRoot $PackageRoot -Confirmation $Confirmation -Interactive:$Interactive -Json:$Json -WriteFaultAt $WriteFaultAt
exit $LASTEXITCODE
