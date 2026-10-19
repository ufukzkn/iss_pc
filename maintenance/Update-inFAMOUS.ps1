# SPDX-License-Identifier: GPL-2.0-or-later
[CmdletBinding()]
param(
    [string]$InstallDir,
    [switch]$CheckOnly,
    [string]$PackageZip,
    [string]$ExpectedSha256,
    [switch]$PrepareOnly,
    [string]$PreparedPlan,
    [string]$ApplyPrepared,
    [int]$WaitForProcessId,
    [string]$ResultFile,
    [switch]$RestartLauncher
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:ForkRepo = 'ufukzkn/iss_pc'
$script:PreparingUpdate = $false

function Write-UpdatePhase([string]$Phase, [string]$Message='') {
    Write-Output ('ISS_UPDATE:' + (@{phase=$Phase; message=$Message} | ConvertTo-Json -Compress))
}

function Get-ChildPath([string]$Root, [string]$Relative) {
    $parts = $Relative.Replace('\','/').Split('/')
    if (-not $Relative -or $parts.Count -eq 0) { throw 'Empty package path' }
    foreach ($part in $parts) {
        if (-not $part -or $part -in @('.','..') -or $part.EndsWith('.') -or $part.EndsWith(' ') -or
            $part.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0 -or
            $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') { throw "Unsafe package path: $Relative" }
    }
    $absolute = [IO.Path]::GetFullPath((Join-Path $Root ($parts -join [IO.Path]::DirectorySeparatorChar)))
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
    if (-not $absolute.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Path escapes package root' }
    return $absolute
}

function Assert-NoLinks([string]$Root, [string]$Relative) {
    $current = $Root
    foreach ($part in @('') + $Relative.Replace('\','/').Split('/')) {
        if ($part) { $current = Join-Path $current $part }
        if (Test-Path -LiteralPath $current) {
            if ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Linked paths cannot be updated safely: $current"
            }
        }
    }
}

function Assert-GameClosed {
    $running = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
        $_.Name -in @('tlg-probe.exe','Play inFAMOUS Second Son.exe') -or
        (-not $script:PreparingUpdate -and $_.Name -in @('inFAMOUS Second Son.exe','inFAMOUS Second Son (classic).exe'))
    })
    if ($running.Count) { throw 'Save your game and close the game and both launchers, then run this updater again.' }
}

function Get-Hash([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }

function Expand-VerifiedPackage([string]$Zip, [string]$Sha256, [string]$Destination) {
    if ($Sha256 -notmatch '^[a-fA-F0-9]{64}$' -or (Get-Hash $Zip) -ne $Sha256.ToLowerInvariant()) { throw 'Package SHA256 mismatch' }
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($Zip)
    try {
        $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        [long]$bytes = 0
        foreach ($entry in $archive.Entries) {
            $name = $entry.FullName.Replace('\','/')
            if (-not $name.StartsWith('infamous-windows-x86_64/', [StringComparison]::Ordinal)) { throw "Unexpected ZIP root: $name" }
            if (($entry.ExternalAttributes -shr 16 -band 61440) -eq 40960) { throw 'ZIP symlinks are not allowed' }
            if ($name.EndsWith('/')) { $name = $name.TrimEnd('/') }
            if ($name -eq 'infamous-windows-x86_64') { continue }
            $null = Get-ChildPath $Destination $name
            if (-not $seen.Add($name)) { throw "Duplicate ZIP path: $name" }
            $rel = $name.Substring('infamous-windows-x86_64/'.Length)
            if ($rel -match '^(?i:user|savedata|logs|cache)(/|$)' -or $rel -match '^(?i:out)/(logs|cache|savedata)(/|$)' -or
                $rel -match '(?i)(^|/)(tlg\.ini|settings\.json|eboot\.bin|content\.bin|boot-linked\.bin)$' -or
                $rel -match '(?i)\.(pkg|sfo|prx|sprx|psarc)$') { throw "Package contains player/game data: $rel" }
            $bytes += $entry.Length
            if ($bytes -gt 6GB) { throw 'Package is unexpectedly large' }
        }
    } finally { $archive.Dispose() }
    [IO.Compression.ZipFile]::ExtractToDirectory($Zip, $Destination)
    $payload = Join-Path $Destination 'infamous-windows-x86_64'
    return Read-VerifiedPayload $payload
}

function Read-VerifiedPayload([string]$payload) {
    $manifest = Get-Content -LiteralPath (Join-Path $payload 'FORK-BUILD.json') -Raw | ConvertFrom-Json
    if ($manifest.schema -ne 1 -or $manifest.repository -ne $script:ForkRepo -or
        $manifest.features -notcontains 'dlc-unlockers' -or $manifest.features -notcontains 'fps-menu-labels' -or
        $manifest.commit -notmatch '^[a-f0-9]{40}$') { throw 'Package is not the expected DLC-enabled fork build' }
    $expected = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $null = $expected.Add('FORK-BUILD.json')
    # Migration to upstream's manifest installer: the archive digest authenticates
    # this manifest; all program bytes remain checked by the legacy file list.
    if (Test-Path -LiteralPath (Join-Path $payload 'package-files.json')) {
        $null = $expected.Add('package-files.json')
    }
    foreach ($property in $manifest.files.PSObject.Properties) {
        $relative = $property.Name
        $file = Get-ChildPath $payload $relative
        if (-not $expected.Add($relative.Replace('\','/')) -or $property.Value -notmatch '^[a-f0-9]{64}$' -or
            -not (Test-Path -LiteralPath $file -PathType Leaf) -or (Get-Hash $file) -ne $property.Value) {
            throw "Missing, duplicate or damaged package file: $relative"
        }
    }
    $actual = @(Get-ChildItem -LiteralPath $payload -Recurse -File -Force)
    if ($actual.Count -ne $expected.Count) { throw 'ZIP contains unlisted files' }
    foreach ($file in $actual) {
        $relative = $file.FullName.Substring($payload.Length + 1).Replace('\','/')
        if (-not $expected.Contains($relative)) { throw "Unlisted package file: $relative" }
    }
    foreach ($required in @('inFAMOUS Second Son.exe','out/tlg-probe.exe','VERSION','LICENSE')) {
        if (-not $expected.Contains($required)) { throw "Incomplete package: $required" }
    }
    return [pscustomobject]@{Root=$payload; Manifest=$manifest}
}

function Invoke-LauncherSelfTest([string]$Root, [string]$ResultFile) {
    $old = $env:ISS_SELFTEST_OUT
    try {
        $env:ISS_SELFTEST_OUT = $ResultFile
        $p = Start-Process -FilePath (Join-Path $Root 'inFAMOUS Second Son.exe') -ArgumentList '--selftest' -WorkingDirectory $Root -WindowStyle Hidden -PassThru
        if (-not $p.WaitForExit(180000)) { $p.Kill(); throw 'Launcher selftest timed out' }
        $p.Refresh()
        if ($p.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $ResultFile) -or
            (Get-Content -LiteralPath $ResultFile -Raw) -notmatch '(?m)^selftest ok\s*$') { throw 'Launcher selftest failed' }
    } finally { $env:ISS_SELFTEST_OUT = $old }
}

function Backup-PlayerData([string]$Root, [string]$Backup) {
    $pointer = Join-Path $env:APPDATA 'inFAMOUS-PC\launcher.json'
    $userData = Join-Path $Root 'user'
    if (Test-Path -LiteralPath $pointer) {
        $configured = (Get-Content -LiteralPath $pointer -Raw | ConvertFrom-Json).user_dir
        if ($configured) { $userData = $configured }
    }
    $locations = [ordered]@{shared=$userData; portable=(Join-Path $Root 'user')}
    foreach ($entry in $locations.GetEnumerator()) {
        foreach ($name in @('savedata','tlg.ini','mods.json')) {
            $source = Join-Path $entry.Value $name
            if (Test-Path -LiteralPath $source) {
                $dest = Join-Path $Backup ('player\' + $entry.Key)
                $null = New-Item -ItemType Directory -Path $dest -Force
                Copy-Item -LiteralPath $source -Destination $dest -Recurse -Force
            }
        }
    }
    foreach ($entry in @{pointer=$pointer; settings=(Join-Path $env:APPDATA 'infamous-launcher\settings.json')}.GetEnumerator()) {
        if (Test-Path -LiteralPath $entry.Value) {
            $dest = Join-Path $Backup 'player'
            $null = New-Item -ItemType Directory -Path $dest -Force
            Copy-Item -LiteralPath $entry.Value -Destination (Join-Path $dest ($entry.Key + '.json'))
        }
    }
}

function Remove-OldUpdateBackups([string]$Target, [string]$CurrentBackup) {
    # Only completed transactions for this installation belong to automatic retention.
    # Failed/incomplete transactions may still be needed for manual recovery.
    $targetPath = [IO.Path]::GetFullPath($Target).TrimEnd('\','/')
    $root = Join-Path (Split-Path -Parent $targetPath) 'infamous-update-backups'
    if (-not (Test-Path -LiteralPath $root)) { return }
    Assert-NoLinks (Split-Path -Parent $root) (Split-Path -Leaf $root)
    $eligible = @(
        foreach ($folder in Get-ChildItem -LiteralPath $root -Directory -Force) {
            if ($folder.Name -notmatch '^\d{8}-\d{6}-[a-f0-9]{8}$' -or
                $folder.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
            $transaction = Join-Path $folder.FullName 'transaction.json'
            if (-not (Test-Path -LiteralPath $transaction -PathType Leaf)) { continue }
            try {
                Assert-NoLinks $folder.FullName 'transaction.json'
                $data = Get-Content -LiteralPath $transaction -Raw | ConvertFrom-Json
                if ($data.status -eq 'installed' -and $data.target -and
                    [IO.Path]::GetFullPath($data.target).TrimEnd('\','/') -eq $targetPath) {
                    $folder
                }
            } catch { continue }
        }
    )
    $ordered = @($eligible | Sort-Object @{Expression={$_.FullName -eq $CurrentBackup}; Descending=$true},
        @{Expression={$_.Name}; Descending=$true})
    foreach ($folder in @($ordered | Select-Object -Skip 2)) {
        # Recheck the absolute boundary and links immediately before recursive deletion.
        $path = [IO.Path]::GetFullPath($folder.FullName)
        if ((Split-Path -Parent $path) -ne $root -or $path -eq $CurrentBackup) {
            throw 'Backup cleanup path is outside the owned backup folder'
        }
        Assert-NoLinks $root $folder.Name
        $links = @(Get-ChildItem -LiteralPath $path -Recurse -Force | Where-Object {
            $_.Attributes -band [IO.FileAttributes]::ReparsePoint
        })
        if ($links.Count) { throw 'Linked backup contents cannot be cleaned automatically' }
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

function Install-VerifiedPayload([string]$Payload, [string]$Target, [string]$Backup, [string]$TestFolder) {
    Assert-GameClosed
    $plan = @()
    foreach ($file in Get-ChildItem -LiteralPath $Payload -Recurse -File -Force) {
        $relative = $file.FullName.Substring($Payload.Length + 1).Replace('\','/')
        $dest = Get-ChildPath $Target $relative
        Assert-NoLinks $Target $relative
        $before = $null
        if (Test-Path -LiteralPath $dest) {
            if (-not (Test-Path -LiteralPath $dest -PathType Leaf)) { throw "Expected a file: $dest" }
            $before = Get-Hash $dest
        }
        $after = Get-Hash $file.FullName
        if ($before -ne $after) { $plan += [pscustomobject]@{Path=$relative; Before=$before; After=$after} }
    }
    $null = New-Item -ItemType Directory -Path $Backup
    @{target=$Target; files=$plan; status='prepared'} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Backup 'transaction.json') -Encoding UTF8
    Backup-PlayerData $Target $Backup
    foreach ($item in $plan) {
        if ($item.Before) {
            $saved = Get-ChildPath (Join-Path $Backup 'program') $item.Path
            $null = New-Item -ItemType Directory -Path (Split-Path -Parent $saved) -Force
            Copy-Item -LiteralPath (Get-ChildPath $Target $item.Path) -Destination $saved -Force
            if ((Get-Hash $saved) -ne $item.Before) { throw 'Backup verification failed; installation has not started' }
        }
    }
    Assert-GameClosed
    $applied = New-Object System.Collections.Generic.List[object]
    try {
        foreach ($item in $plan) {
            $dest = Get-ChildPath $Target $item.Path
            Assert-NoLinks $Target $item.Path
            # Detect a concurrently changed file before replacing it.
            $current = $null
            if (Test-Path -LiteralPath $dest) { $current = Get-Hash $dest }
            if ($current -ne $item.Before) { throw "File changed during update: $($item.Path)" }
            $null = New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force
            $applied.Add($item)
            Copy-Item -LiteralPath (Get-ChildPath $Payload $item.Path) -Destination $dest -Force
            if ((Get-Hash $dest) -ne $item.After) { throw "Installed hash mismatch: $($item.Path)" }
        }
        Invoke-LauncherSelfTest $Target (Join-Path $TestFolder 'installed-selftest.txt')
        @{target=$Target; files=$plan; status='installed'} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Backup 'transaction.json') -Encoding UTF8
    } catch {
        $failure = $_
        $rollbackErrors = @()
        for ($i=$applied.Count-1; $i -ge 0; $i--) {
            $item = $applied[$i]
            try {
                $dest = Get-ChildPath $Target $item.Path
                Assert-NoLinks $Target $item.Path
                if ($item.Before) {
                    Copy-Item -LiteralPath (Get-ChildPath (Join-Path $Backup 'program') $item.Path) -Destination $dest -Force
                    if ((Get-Hash $dest) -ne $item.Before) { throw 'Restored hash mismatch' }
                } elseif (Test-Path -LiteralPath $dest) {
                    Remove-Item -LiteralPath $dest -Force
                }
            } catch { $rollbackErrors += $item.Path }
        }
        @{target=$Target; files=$plan; status='rolled-back'; rollback_errors=$rollbackErrors} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Backup 'transaction.json') -Encoding UTF8
        if ($rollbackErrors.Count) { throw "Update failed; some locked files could not be restored. Backup: $Backup. Files: $($rollbackErrors -join ', ')" }
        throw "Update failed; previous program files restored. Backup: $Backup. Cause: $failure"
    }
    # Cleanup errors must never undo an otherwise successful installation.
    try { Remove-OldUpdateBackups $Target $Backup }
    catch { Write-Warning ('Update installed, but old backup cleanup was skipped: ' + $_.Exception.Message) }
    return $plan.Count
}

function Invoke-InfamousUpdate {
    $script:PreparingUpdate = [bool]$PrepareOnly
    if ($PrepareOnly -and -not $PreparedPlan) { throw 'PrepareOnly requires a plan output path' }
    if (-not $InstallDir) {
        if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'out\tlg-probe.exe')) { $InstallDir=$PSScriptRoot }
        else { $InstallDir=Join-Path $PSScriptRoot 'infamous-windows-x86_64' }
    }
    $InstallDir = (Resolve-Path -LiteralPath $InstallDir).Path.TrimEnd('\','/')
    if (-not (Test-Path -LiteralPath (Join-Path $InstallDir 'inFAMOUS Second Son.exe'))) { throw 'Select the existing inFAMOUS installation directory' }
    $parent = Split-Path -Parent $InstallDir
    $headers = @{Accept='application/vnd.github+json'; 'User-Agent'='iss-pc-fork-updater'}
    $latest = $null
    if ($PackageZip) {
        if (-not $ExpectedSha256) { throw 'An offline package requires -ExpectedSha256' }
        $PackageZip=(Resolve-Path -LiteralPath $PackageZip).Path
    } else {
        $latest = Invoke-RestMethod -Uri ('https://api.github.com/repos/' + $script:ForkRepo + '/releases/latest') -Headers $headers
        if ($latest.draft -or $latest.prerelease) { throw 'Expected a published stable release' }
        Write-Host ('Latest DLC build: ' + $latest.tag_name)
        $current = Join-Path $InstallDir 'VERSION'
        if (Test-Path -LiteralPath $current) { Write-Host ('Installed: ' + (Get-Content -LiteralPath $current -Raw).Trim()) }
        if ($CheckOnly) { return }
        if ((Test-Path -LiteralPath (Join-Path $InstallDir 'FORK-BUILD.json')) -and
            (Test-Path -LiteralPath $current) -and (Get-Content -LiteralPath $current -Raw).Trim() -eq $latest.tag_name) {
            Write-Host 'Already using the latest fork release.'; return
        }
    }
    Assert-GameClosed
    $mutexName = 'Local\iss-pc-update-' + ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($InstallDir.ToLowerInvariant())))).Replace('-','')
    $mutex = New-Object Threading.Mutex($false, $mutexName)
    $acquired = $mutex.WaitOne(0)
    if (-not $acquired) { $mutex.Dispose(); throw 'Another update is already running' }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $suffix = [guid]::NewGuid().ToString('N').Substring(0,8)
    $stage = Join-Path $parent ('.iss-update-stage-' + $stamp + '-' + $suffix)
    $backup = Join-Path $parent ('infamous-update-backups\' + $stamp + '-' + $suffix)
    $keepStage = $false
    try {
        $null = New-Item -ItemType Directory -Path $stage
        if ($PrepareOnly -and $PackageZip) {
            $preparedZip=Join-Path $stage 'infamous-windows-x86_64.zip'
            Copy-Item -LiteralPath $PackageZip -Destination $preparedZip
            $PackageZip=$preparedZip
        }
        if (-not $PackageZip) {
            $assetName = 'infamous-windows-x86_64.zip'
            $zipAsset = @($latest.assets | Where-Object name -eq $assetName)
            $hashAsset = @($latest.assets | Where-Object name -eq ($assetName + '.sha256'))
            if ($zipAsset.Count -ne 1 -or $hashAsset.Count -ne 1) { throw 'Release has no complete Windows package and checksum pair' }
            foreach ($asset in @($zipAsset[0],$hashAsset[0])) {
                if (-not $asset.browser_download_url.StartsWith(('https://github.com/' + $script:ForkRepo + '/releases/download/'), [StringComparison]::Ordinal)) { throw 'Unexpected release download URL' }
            }
            $PackageZip = Join-Path $stage $assetName
            $hashFile = Join-Path $stage 'checksum.txt'
            Invoke-WebRequest -UseBasicParsing -Uri $hashAsset[0].browser_download_url -OutFile $hashFile
            $ExpectedSha256 = ((Get-Content -LiteralPath $hashFile -Raw).Trim() -split '\s+')[0]
            Write-Host 'Downloading verified fork package...'
            Write-UpdatePhase 'download'
            Invoke-WebRequest -UseBasicParsing -Uri $zipAsset[0].browser_download_url -OutFile $PackageZip
        }
        Write-UpdatePhase 'verify'
        $verified = Expand-VerifiedPackage $PackageZip $ExpectedSha256 (Join-Path $stage 'payload')
        if ($latest -and $verified.Manifest.version -ne $latest.tag_name) { throw 'Release version and package version disagree' }
        Write-UpdatePhase 'selftest'
        Invoke-LauncherSelfTest $verified.Root (Join-Path $stage 'staged-selftest.txt')
        if ($PrepareOnly) {
            Assert-GameClosed
            if ($WaitForProcessId -gt 0 -and -not (Get-Process -Id $WaitForProcessId -ErrorAction SilentlyContinue)) {
                throw 'The launcher closed; prepared update cancelled'
            }
            @{schema=1; target=$InstallDir; stage=$stage; payload=$verified.Root; zip=$PackageZip;
              sha256=$ExpectedSha256; version=$verified.Manifest.version; backup=$backup} |
                ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $PreparedPlan -Encoding UTF8
            $keepStage=$true
            Write-UpdatePhase 'ready'
            return
        }
        Write-UpdatePhase 'install'
        $count = Install-VerifiedPayload $verified.Root $InstallDir $backup $stage
        Write-Host ('Updated to ' + $verified.Manifest.version + ' (' + $count + ' files).')
        Write-Host ('Saves/settings backup and previous program files: ' + $backup)
        Write-Host 'Open your usual launcher and press Play.'
    } finally {
        # Only this invocation's literal, verified stage directory can be removed recursively.
        if (-not $keepStage -and (Split-Path -Parent ([IO.Path]::GetFullPath($stage))) -eq $parent -and
            (Split-Path -Leaf $stage) -like '.iss-update-stage-*' -and (Test-Path -LiteralPath $stage)) {
            Remove-Item -LiteralPath $stage -Recurse -Force
        }
        if ($acquired) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}

function Invoke-PreparedUpdate([string]$PlanPath) {
    $script:PreparingUpdate=$false
    $plan=Get-Content -LiteralPath $PlanPath -Raw | ConvertFrom-Json
    if ($plan.schema -ne 1) { throw 'Unsupported update plan' }
    $target=[IO.Path]::GetFullPath($plan.target).TrimEnd('\','/')
    $parent=Split-Path -Parent $target
    $stage=[IO.Path]::GetFullPath($plan.stage).TrimEnd('\','/')
    if ((Split-Path -Parent $stage) -ne $parent -or (Split-Path -Leaf $stage) -notlike '.iss-update-stage-*' -or
        $plan.payload -ne (Join-Path $stage 'payload\infamous-windows-x86_64') -or
        $plan.zip -ne (Join-Path $stage 'infamous-windows-x86_64.zip') -or
        (Split-Path -Parent $plan.backup) -ne (Join-Path $parent 'infamous-update-backups') -or
        -not (Test-Path -LiteralPath (Join-Path $target 'inFAMOUS Second Son.exe'))) { throw 'Invalid update plan paths' }
    Assert-NoLinks $parent (Split-Path -Leaf $stage)
    if ($WaitForProcessId -gt 0) {
        Write-UpdatePhase 'waiting'
        $process=Get-Process -Id $WaitForProcessId -ErrorAction SilentlyContinue
        if ($process -and -not $process.WaitForExit(60000)) { throw 'Launcher did not exit; installation has not started' }
    }
    # A frozen launcher has a short-lived bootloader parent, which can exit just after Python.
    $closed=$false
    for ($i=0; $i -lt 30; $i++) {
        try { Assert-GameClosed; $closed=$true; break } catch { Start-Sleep -Milliseconds 200 }
    }
    if (-not $closed) { throw 'Close all game and launcher windows; installation has not started' }
    $mutexName='Local\iss-pc-update-' + ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($target.ToLowerInvariant())))).Replace('-','')
    $mutex=New-Object Threading.Mutex($false,$mutexName)
    $acquired=$mutex.WaitOne(0)
    if (-not $acquired) { $mutex.Dispose(); throw 'Another update is already running' }
    try {
        Write-UpdatePhase 'verify'
        if ((Get-Hash $plan.zip) -ne $plan.sha256) { throw 'Prepared archive changed; installation has not started' }
        $verified=Read-VerifiedPayload $plan.payload
        if ($verified.Manifest.version -ne $plan.version) { throw 'Prepared version changed' }
        Write-UpdatePhase 'install'
        $count=Install-VerifiedPayload $verified.Root $target $plan.backup $stage
        if ($ResultFile) {
            @{status='success'; version=$plan.version; backup=$plan.backup; files=$count} |
                ConvertTo-Json | Set-Content -LiteralPath $ResultFile -Encoding UTF8
        }
        Write-UpdatePhase 'done'
    } finally {
        $mutex.ReleaseMutex(); $mutex.Dispose()
        # The applying script lives in TEMP, outside both the live install and this owned stage.
        if ((Split-Path -Parent $stage) -eq $parent -and (Split-Path -Leaf $stage) -like '.iss-update-stage-*' -and
            (Test-Path -LiteralPath $stage)) { Remove-Item -LiteralPath $stage -Recurse -Force }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    [Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
    $exitCode=0
    try {
        if ($ApplyPrepared) { Invoke-PreparedUpdate $ApplyPrepared }
        else { Invoke-InfamousUpdate }
    } catch {
        $exitCode=1
        if ($ResultFile) {
            @{status='error'; message=$_.Exception.Message} | ConvertTo-Json |
                Set-Content -LiteralPath $ResultFile -Encoding UTF8
        }
        Write-UpdatePhase 'error' $_.Exception.Message
        Write-Error $_ -ErrorAction Continue
    }
    if ($ApplyPrepared -and $RestartLauncher) {
        $plan=Get-Content -LiteralPath $ApplyPrepared -Raw | ConvertFrom-Json
        if ($ResultFile) { $env:ISS_UPDATE_RESULT_FILE=$ResultFile }
        Start-Process -FilePath (Join-Path $plan.target 'inFAMOUS Second Son.exe') -WorkingDirectory $plan.target
    }
    exit $exitCode
}
