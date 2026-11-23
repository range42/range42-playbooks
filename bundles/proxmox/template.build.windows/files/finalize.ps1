# finalize.ps1 - first-logon build script of the range42 Windows templates.
# Runs once, as alice (elevated), from the payload CD (FirstLogonCommands of Autounattend.xml).
# Installs the virtio guest tools, the QEMU guest agent, the OpenSSH server and cloudbase-init,
# sets a few OS defaults, then runs sysprep, which shuts the VM down. Any error stops the
# script before sysprep : the VM stays up for inspection. Transcript : C:\range42-build.log

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Start-Transcript -Path 'C:\range42-build.log' -Append | Out-Null

$payload = Split-Path -Parent $MyInvocation.MyCommand.Path
$cbRoot = 'C:\Program Files\Cloudbase Solutions\Cloudbase-Init'
$isServer = (Get-CimInstance Win32_OperatingSystem).ProductType -ne 1

function Find-OnDrives([string]$relative) {
    foreach ($d in Get-PSDrive -PSProvider FileSystem) {
        $p = Join-Path $d.Root $relative
        if (Test-Path $p) { return $p }
    }
    throw "not found on any drive: $relative"
}

function Install-Msi([string]$msi, [string]$extra = '') {
    Write-Output "install $msi $extra"
    $p = Start-Process -FilePath 'msiexec.exe' -Wait -PassThru `
        -ArgumentList "/i `"$msi`" /qn /norestart $extra"
    if ($p.ExitCode -notin 0, 3010) { throw "msiexec $msi exit code $($p.ExitCode)" }
}

function Invoke-Sysprep {
    $unattend = Join-Path $payload 'unattend-sysprep.xml'
    $p = Start-Process -FilePath "$env:WINDIR\System32\Sysprep\sysprep.exe" -PassThru `
        -ArgumentList '/generalize', '/oobe', '/shutdown', '/quiet', "/unattend:$unattend"
    $p.WaitForExit(600000) | Out-Null
    # on success Windows is shutting down now
    Start-Sleep -Seconds 120
}

try {
    #### 1. virtio guest tools + QEMU guest agent (virtio-win ISO, ide2)
    Install-Msi (Find-OnDrives 'virtio-win-gt-x64.msi')
    Install-Msi (Find-OnDrives 'guest-agent\qemu-ga-x86_64.msi')
    Start-Service -Name 'QEMU-GA'

    #### 2. OpenSSH server (Windows Server 2025 ships it ; Windows 11 downloads it)
    $cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server*' | Select-Object -First 1
    for ($i = 1; $cap.State -ne 'Installed'; $i++) {
        if ($i -gt 3) { throw "OpenSSH.Server capability not installed: $($cap.State)" }
        Write-Output "Add-WindowsCapability $($cap.Name), attempt $i"
        try { Add-WindowsCapability -Online -Name $cap.Name | Out-Null } catch { Write-Output $_ ; Start-Sleep -Seconds 30 }
        $cap = Get-WindowsCapability -Online -Name $cap.Name
    }
    Set-Service -Name sshd -StartupType Automatic
    Start-Service -Name sshd    # sshd creates C:\ProgramData\ssh and missing host keys at start
    Stop-Service -Name sshd
    Copy-Item -Path (Join-Path $payload 'sshd_config') -Destination 'C:\ProgramData\ssh\sshd_config' -Force
    New-Item -Path 'HKLM:\SOFTWARE\OpenSSH' -Force | Out-Null
    New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell -PropertyType String -Force `
        -Value "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" | Out-Null
    if (Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue) {
        Set-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -Enabled True -Profile Any
    } else {
        New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' `
            -Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow -Profile Any | Out-Null
    }

    #### 3. cloudbase-init (MSI pinned by sha256 on the Proxmox side, signature checked here)
    # The check runs in a child process with a timeout : on Windows 11 the build once stalled
    # here, right after the OpenSSH capability install. Up to 3 attempts of 5 minutes.
    $msi = Join-Path $payload 'CloudbaseInitSetup_x64.msi'
    $sig = $null
    for ($i = 1; -not $sig; $i++) {
        if ($i -gt 3) { throw 'cloudbase-init MSI signature check did not return' }
        Write-Output "cloudbase-init MSI signature check, attempt $i"
        $job = Start-Job -ArgumentList $msi -ScriptBlock {
            param($p)
            $s = Get-AuthenticodeSignature -FilePath $p
            "$($s.Status)|$($s.SignerCertificate.Subject)"
        }
        if (Wait-Job -Job $job -Timeout 300) { $sig = Receive-Job -Job $job }
        Remove-Job -Job $job -Force
    }
    $status, $signer = $sig -split '\|', 2
    if ($status -ne 'Valid') { throw "cloudbase-init MSI signature: $status" }
    Write-Output "cloudbase-init MSI signer: $signer"
    Install-Msi $msi 'RUN_SERVICE_AS_LOCAL_SYSTEM=1 /l*v C:\range42-cloudbase-msi.log'
    Stop-Service -Name cloudbase-init -ErrorAction SilentlyContinue
    Copy-Item -Path (Join-Path $payload 'cloudbase-init.conf') -Destination "$cbRoot\conf\cloudbase-init.conf" -Force
    Copy-Item -Path (Join-Path $payload 'cloudbase-init-unattend.conf') -Destination "$cbRoot\conf\cloudbase-init-unattend.conf" -Force
    Set-Service -Name cloudbase-init -StartupType Automatic
    # no plugin state from the build may leak into the clones
    Get-ChildItem -Path 'HKLM:\SOFTWARE\Cloudbase Solutions\Cloudbase-Init' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
    Remove-Item -Path "$cbRoot\log\*" -Force -ErrorAction SilentlyContinue

    #### 4. OS defaults
    powercfg.exe /hibernate off
    powercfg.exe /change standby-timeout-ac 0
    powercfg.exe /change monitor-timeout-ac 0
    New-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU' -Force | Out-Null
    New-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU' -Name NoAutoUpdate `
        -PropertyType DWord -Value 1 -Force | Out-Null
    if ($isServer) {
        Get-ScheduledTask -TaskName 'ServerManager' -ErrorAction SilentlyContinue | Disable-ScheduledTask | Out-Null
    } else {
        Get-AppxPackage -AllUsers -Name 'Microsoft.OneDriveSync' | Remove-AppxPackage -AllUsers -ErrorAction SilentlyContinue
    }
    if (Get-Command -Name Get-BitLockerVolume -ErrorAction SilentlyContinue) {
        $bl = Get-BitLockerVolume -MountPoint 'C:'
        if ($bl.VolumeStatus -ne 'FullyDecrypted') {
            Disable-BitLocker -MountPoint 'C:' | Out-Null
            while ((Get-BitLockerVolume -MountPoint 'C:').VolumeStatus -ne 'FullyDecrypted') { Start-Sleep -Seconds 10 }
        }
        Write-Output "BitLocker C: $((Get-BitLockerVolume -MountPoint 'C:').VolumeStatus)"
    }
    # No Windows hypervisor, no VBS, no Credential Guard : under nested virtualisation a
    # Windows 11 clone stalled at boot while launching the hypervisor (README, Nested virtualisation).
    bcdedit.exe /set hypervisorlaunchtype off
    if ($LASTEXITCODE -ne 0) { throw "bcdedit hypervisorlaunchtype exit code $LASTEXITCODE" }
    $dg = 'HKLM:\SYSTEM\CurrentControlSet\Control\DeviceGuard'
    foreach ($v in @(
            @($dg, 'EnableVirtualizationBasedSecurity'),
            @($dg, 'RequirePlatformSecurityFeatures'),
            @("$dg\Scenarios\HypervisorEnforcedCodeIntegrity", 'Enabled'),
            @('HKLM:\SYSTEM\CurrentControlSet\Control\Lsa', 'LsaCfgFlags'))) {
        if (-not (Test-Path $v[0])) { New-Item -Path $v[0] -Force | Out-Null }
        New-ItemProperty -Path $v[0] -Name $v[1] -PropertyType DWord -Value 0 -Force | Out-Null
    }

    #### 5. cleanup : no stored logon password, no SSH host keys shared by every clone
    $winlogon = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
    Remove-ItemProperty -Path $winlogon -Name DefaultPassword -ErrorAction SilentlyContinue
    Set-ItemProperty -Path $winlogon -Name AutoAdminLogon -Value '0'
    Remove-Item -Path 'C:\ProgramData\ssh\ssh_host_*' -Force

    #### 6. sysprep (shuts the VM down). Classic failure : an Appx package installed for a
    #### user but not provisioned. Remove such packages once and retry.
    Write-Output 'sysprep, attempt 1'
    Invoke-Sysprep
    $log = "$env:WINDIR\System32\Sysprep\Panther\setupact.log"
    $pkgs = Select-String -Path $log -Pattern 'Package (\S+) was installed for a user, but not provisioned' |
        ForEach-Object { $_.Matches[0].Groups[1].Value } | Sort-Object -Unique
    if (-not $pkgs) { throw "sysprep did not shut down the VM, see $env:WINDIR\System32\Sysprep\Panther\setuperr.log" }
    foreach ($pkg in $pkgs) {
        Write-Output "remove Appx package $pkg"
        Get-AppxPackage -AllUsers | Where-Object PackageFullName -eq $pkg | Remove-AppxPackage -AllUsers
    }
    Write-Output 'sysprep, attempt 2'
    Invoke-Sysprep
    throw "sysprep did not shut down the VM after the Appx retry, see $env:WINDIR\System32\Sysprep\Panther\setuperr.log"
}
catch {
    Write-Output "range42 finalize FAILED: $_"
    Stop-Transcript | Out-Null
    exit 1
}
