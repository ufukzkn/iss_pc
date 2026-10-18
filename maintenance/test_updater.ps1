$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Update-inFAMOUS.ps1')
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('iss-updater-tests-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $testRoot
$oldAppdata = $env:APPDATA
$env:APPDATA = Join-Path $testRoot 'appdata'
$script:BlockGame = $false
$script:FailTest = $false
function Assert-GameClosed { if ($script:BlockGame) { throw 'fixture: game is open' } }
function Invoke-LauncherSelfTest([string]$Root, [string]$ResultFile) {
    if ($script:FailTest) { throw 'fixture: launcher cannot start' }
    Set-Content -LiteralPath $ResultFile -Value 'selftest ok'
}
function Assert([bool]$Value, [string]$Message) { if (-not $Value) { throw $Message } }
function MustFail([scriptblock]$Action, [string]$Message) {
    $failed = $false
    try { & $Action | Out-Null } catch { $failed = $true }
    Assert $failed $Message
}
function Put([string]$Root, [string]$Relative, [string]$Value) {
    $path = Get-ChildPath $Root $Relative
    $null = New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force
    [IO.File]::WriteAllText($path, $Value)
}
function Fixture([string]$Name) {
    $folder = Join-Path $testRoot $Name
    $target = Join-Path $folder 'installed'
    $payload = Join-Path $folder 'payload'
    Put $target 'out/tlg-probe.exe' 'old-game'
    Put $target 'inFAMOUS Second Son.exe' 'old-launcher'
    Put $target 'user/savedata/manual' 'manual-save'
    Put $target 'user/tlg.ini' 'my-graphics'
    Put $target 'user/cache/pipeline' 'shader-cache'
    Put $target 'unknown-file.txt' 'keep-me'
    Put $payload 'out/tlg-probe.exe' 'new-game'
    Put $payload 'inFAMOUS Second Son.exe' 'new-launcher'
    Put $payload 'out/new-library.dll' 'new-library'
    Put $payload 'VERSION' 'v2026.10.18-1234567'
    Put $payload 'LICENSE' 'fixture-license'
    $hashes = @{}
    foreach ($file in Get-ChildItem -LiteralPath $payload -Recurse -File) {
        $hashes[$file.FullName.Substring($payload.Length+1).Replace('\','/')] = Get-Hash $file.FullName
    }
    @{schema=1; repository='ufukzkn/iss_pc'; features=@('dlc-unlockers','fps-menu-labels'); commit=('a'*40); version='v2026.10.18-1234567'; files=$hashes} |
        ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $payload 'FORK-BUILD.json') -Encoding UTF8
    return @{Folder=$folder; Target=$target; Payload=$payload; Backup=(Join-Path $folder 'backup')}
}
function ZipPayload($Fixture, [string]$ExtraEntry='') {
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = Join-Path $Fixture.Folder ([guid]::NewGuid().ToString('N') + '.zip')
    $archive = [IO.Compression.ZipFile]::Open($zip, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($file in Get-ChildItem -LiteralPath $Fixture.Payload -Recurse -File) {
            $name = 'infamous-windows-x86_64/' + $file.FullName.Substring($Fixture.Payload.Length+1).Replace('\','/')
            $null = [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $file.FullName, $name)
        }
        if ($ExtraEntry) {
            $entry = $archive.CreateEntry($ExtraEntry)
            $writer = New-Object IO.StreamWriter($entry.Open())
            $writer.Write('unexpected')
            $writer.Dispose()
        }
    } finally { $archive.Dispose() }
    return $zip
}
function RetentionBackup([string]$Root, [string]$Name, [string]$Target, [string]$Status='installed') {
    $path = Join-Path $Root $Name
    Put $path 'program/old.exe' 'recovery-copy'
    @{target=$Target; status=$Status; files=@()} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $path 'transaction.json') -Encoding UTF8
    return $path
}
try {
    foreach ($bad in @('../escape','/absolute','out/../../escape','out/name:stream','out/CON.txt','out/ends.','out/ends ')) {
        MustFail { Get-ChildPath $testRoot $bad } "Unsafe path accepted: $bad"
    }
    $ok = Fixture 'success'
    $zip = ZipPayload $ok
    $verified = Expand-VerifiedPackage $zip (Get-Hash $zip) (Join-Path $ok.Folder 'expanded')
    $count = Install-VerifiedPayload $verified.Root $ok.Target $ok.Backup $ok.Folder
    Assert ($count -gt 0) 'No files installed'
    Assert ((Get-Content -LiteralPath (Join-Path $ok.Target 'out/tlg-probe.exe') -Raw) -eq 'new-game') 'Game was not replaced'
    Assert ((Get-Content -LiteralPath (Join-Path $ok.Target 'user/savedata/manual') -Raw) -eq 'manual-save') 'Manual save changed'
    Assert ((Get-Content -LiteralPath (Join-Path $ok.Target 'user/tlg.ini') -Raw) -eq 'my-graphics') 'Graphics changed'
    Assert ((Get-Content -LiteralPath (Join-Path $ok.Target 'user/cache/pipeline') -Raw) -eq 'shader-cache') 'Shader cache changed'
    Assert ((Get-Content -LiteralPath (Join-Path $ok.Target 'unknown-file.txt') -Raw) -eq 'keep-me') 'Unrelated file changed'
    Assert ((Get-Content -LiteralPath (Join-Path $ok.Backup 'program/out/tlg-probe.exe') -Raw) -eq 'old-game') 'Original program not backed up'
    Assert (Test-Path -LiteralPath (Join-Path $ok.Backup 'player/portable/savedata/manual')) 'Player backup missing'

    $broken = Fixture 'rollback'
    $script:FailTest = $true
    MustFail { Install-VerifiedPayload $broken.Payload $broken.Target $broken.Backup $broken.Folder } 'Failed selftest did not stop update'
    $script:FailTest = $false
    Assert ((Get-Content -LiteralPath (Join-Path $broken.Target 'out/tlg-probe.exe') -Raw) -eq 'old-game') 'Rollback did not restore old program'
    Assert (-not (Test-Path -LiteralPath (Join-Path $broken.Target 'out/new-library.dll'))) 'Rollback left a new DLL'
    Assert ((Get-Content -LiteralPath (Join-Path $broken.Target 'user/savedata/manual') -Raw) -eq 'manual-save') 'Rollback changed a save'

    $blocked = Fixture 'open-game'
    $script:BlockGame = $true
    MustFail { Install-VerifiedPayload $blocked.Payload $blocked.Target $blocked.Backup $blocked.Folder } 'Open game did not stop update'
    $script:BlockGame = $false
    Assert (-not (Test-Path -LiteralPath $blocked.Backup)) 'Open-game check ran after changes'

    MustFail { Expand-VerifiedPackage $zip ('0'*64) (Join-Path $testRoot 'bad-sha') } 'Wrong archive checksum accepted'
    foreach ($extra in @('infamous-windows-x86_64/../escape.txt','infamous-windows-x86_64/unlisted.txt','infamous-windows-x86_64/user/savedata/injected','infamous-windows-x86_64/VERSION')) {
        $badZip = ZipPayload $ok $extra
        MustFail { Expand-VerifiedPackage $badZip (Get-Hash $badZip) (Join-Path $testRoot ([guid]::NewGuid().ToString('N'))) } "Bad ZIP accepted: $extra"
    }
    # The launcher prepares while open; installation happens only in the separate applying phase.
    $two=Fixture 'two-phase'
    $InstallDir=$two.Target
    $PackageZip=ZipPayload $two
    $ExpectedSha256=Get-Hash $PackageZip
    $PrepareOnly=$true
    $PreparedPlan=Join-Path $two.Folder 'prepared.json'
    Invoke-InfamousUpdate | Out-Null
    Assert ((Get-Content -LiteralPath (Join-Path $two.Target 'out/tlg-probe.exe') -Raw) -eq 'old-game') 'Prepare changed the live program'
    $plan=Get-Content -LiteralPath $PreparedPlan -Raw | ConvertFrom-Json
    Assert (Test-Path -LiteralPath $plan.payload) 'Prepared payload missing'
    $PrepareOnly=$false
    $ResultFile=Join-Path $two.Folder 'result.json'
    Invoke-PreparedUpdate $PreparedPlan | Out-Null
    Assert ((Get-Content -LiteralPath (Join-Path $two.Target 'out/tlg-probe.exe') -Raw) -eq 'new-game') 'Apply did not install'
    Assert (-not (Test-Path -LiteralPath $plan.stage)) 'Prepared stage was not cleaned'
    Assert ((Get-Content -LiteralPath $ResultFile -Raw | ConvertFrom-Json).status -eq 'success') 'Result handoff missing'

    $tampered=Fixture 'tampered-plan'
    $InstallDir=$tampered.Target
    $PackageZip=ZipPayload $tampered
    $ExpectedSha256=Get-Hash $PackageZip
    $PrepareOnly=$true
    $PreparedPlan=Join-Path $tampered.Folder 'prepared.json'
    Invoke-InfamousUpdate | Out-Null
    $plan=Get-Content -LiteralPath $PreparedPlan -Raw | ConvertFrom-Json
    Put $plan.payload 'out/tlg-probe.exe' 'tampered'
    $PrepareOnly=$false
    MustFail { Invoke-PreparedUpdate $PreparedPlan } 'Tampered prepared payload accepted'
    Assert ((Get-Content -LiteralPath (Join-Path $tampered.Target 'out/tlg-probe.exe') -Raw) -eq 'old-game') 'Tampered payload changed the install'

    $retention=Fixture 'retention'
    $retentionRoot=Join-Path $retention.Folder 'infamous-update-backups'
    $oldest=RetentionBackup $retentionRoot '20260101-010000-aaaaaaaa' $retention.Target
    $older=RetentionBackup $retentionRoot '20260102-010000-bbbbbbbb' $retention.Target
    $previous=RetentionBackup $retentionRoot '20260103-010000-cccccccc' $retention.Target
    $failed=RetentionBackup $retentionRoot '20260104-010000-dddddddd' $retention.Target 'rolled-back'
    $foreign=RetentionBackup $retentionRoot '20260104-020000-eeeeeeee' (Join-Path $retention.Folder 'other-install')
    $unrelated=RetentionBackup $retentionRoot 'my-manual-backup' $retention.Target
    $malformed=Join-Path $retentionRoot '20260104-030000-ffffffff'
    Put $malformed 'transaction.json' '{broken'
    $current=Join-Path $retentionRoot '20260105-010000-12345678'
    $script:FailTest=$true
    MustFail { Install-VerifiedPayload $retention.Payload $retention.Target $current $retention.Folder } 'Failed install unexpectedly succeeded'
    $script:FailTest=$false
    Assert ((Test-Path -LiteralPath $oldest) -and (Test-Path -LiteralPath $older)) 'Failed install deleted recovery backups'
    # Use a new transaction directory after the failed attempt.
    $current=Join-Path $retentionRoot '20260106-010000-12345678'
    Install-VerifiedPayload $retention.Payload $retention.Target $current $retention.Folder | Out-Null
    Assert (-not (Test-Path -LiteralPath $oldest)) 'Oldest successful backup was not removed'
    Assert (-not (Test-Path -LiteralPath $older)) 'Third successful backup was not removed'
    Assert ((Test-Path -LiteralPath $previous) -and (Test-Path -LiteralPath $current)) 'Last two successful backups were not kept'
    foreach ($kept in @($failed,$foreign,$unrelated,$malformed,(Join-Path $retentionRoot '20260105-010000-12345678'))) {
        Assert (Test-Path -LiteralPath $kept) 'Cleanup removed failed, foreign or unrelated backup data'
    }
    # A clock moving backwards must not put the active rollback copy at risk.
    $clock=RetentionBackup $retentionRoot '20200101-010000-11111111' $retention.Target
    Remove-OldUpdateBackups $retention.Target $clock
    Assert ((Test-Path -LiteralPath $clock) -and (Test-Path -LiteralPath $current)) 'Current backup was removed after a clock change'
    Assert (-not (Test-Path -LiteralPath $previous)) 'Retention kept more than two successful transactions'
    # A junction in an old backup must neither escape the backup root nor roll back
    # a successfully installed update when automatic cleanup refuses it.
    $cleanupFailure=Fixture 'cleanup-failure'
    $cleanupRoot=Join-Path $cleanupFailure.Folder 'infamous-update-backups'
    $linked=RetentionBackup $cleanupRoot '20260101-010000-aaaaaaaa' $cleanupFailure.Target
    $null=RetentionBackup $cleanupRoot '20260102-010000-bbbbbbbb' $cleanupFailure.Target
    $null=RetentionBackup $cleanupRoot '20260103-010000-cccccccc' $cleanupFailure.Target
    $protected=Join-Path $testRoot 'outside-backups'
    Put $protected 'keep.txt' 'protected'
    $junction=Join-Path $linked 'program/link'
    $null=New-Item -ItemType Junction -Path $junction -Target $protected
    try {
        $cleanupCurrent=Join-Path $cleanupRoot '20260104-010000-dddddddd'
        Install-VerifiedPayload $cleanupFailure.Payload $cleanupFailure.Target $cleanupCurrent $cleanupFailure.Folder | Out-Null
        Assert ((Get-Content -LiteralPath (Join-Path $cleanupFailure.Target 'out/tlg-probe.exe') -Raw) -eq 'new-game') 'Cleanup failure rolled back successful installation'
        Assert ((Get-Content -LiteralPath (Join-Path $cleanupCurrent 'transaction.json') -Raw | ConvertFrom-Json).status -eq 'installed') 'Cleanup failure changed transaction status'
        Assert ((Get-Content -LiteralPath (Join-Path $protected 'keep.txt') -Raw) -eq 'protected') 'Cleanup traversed a junction'
        Assert (Test-Path -LiteralPath $linked) 'Linked backup was deleted'
    } finally { [IO.Directory]::Delete($junction) }
    Write-Host 'Updater tests passed: preservation, backup, rollback, process gate, archive validation, two-phase handoff and two-backup retention.'
} finally {
    $env:APPDATA = $oldAppdata
    $resolved = [IO.Path]::GetFullPath($testRoot)
    $parent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\','/')
    if ((Split-Path -Parent $resolved) -eq $parent -and (Split-Path -Leaf $resolved) -like 'iss-updater-tests-*') {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
