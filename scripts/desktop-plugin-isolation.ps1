[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Install", "Remove", "Verify", "Probe")]
    [string]$Action,
    [ValidatePattern("^[a-z0-9]+(?:[._-][a-z0-9]+)+$")]
    [string]$PluginId,
    [switch]$DeleteAppContainerProfile,
    [string]$ResultPath
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [System.Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "此操作需要使用 Windows 管理员权限运行 PowerShell。"
    }
}

function Initialize-NativeMethods {
    if ("PasswordDetectivePluginIsolation.NativeMethods" -as [type]) {
        return
    }

    Add-Type @"
using System;
using System.Runtime.InteropServices;

namespace PasswordDetectivePluginIsolation {
    public static class NativeMethods {
        [DllImport("userenv.dll", CharSet = CharSet.Unicode)]
        public static extern int CreateAppContainerProfile(
            string name,
            string displayName,
            string description,
            IntPtr capabilities,
            uint capabilityCount,
            out IntPtr appContainerSid);

        [DllImport("userenv.dll", CharSet = CharSet.Unicode)]
        public static extern int DeriveAppContainerSidFromAppContainerName(
            string name,
            out IntPtr appContainerSid);

        [DllImport("userenv.dll", CharSet = CharSet.Unicode)]
        public static extern int DeleteAppContainerProfile(string name);

        [DllImport("advapi32.dll", SetLastError = true)]
        public static extern IntPtr FreeSid(IntPtr sid);
    }
}
"@
}

function Get-PluginProfileName([string]$Value) {
    $digest = [System.Security.Cryptography.SHA256]::HashData(
        [System.Text.Encoding]::UTF8.GetBytes($Value))
    $hex = [System.Convert]::ToHexString($digest)
    return "PasswordDetective.Plugin.$($hex.Substring(0, 24))"
}

function Get-PluginRuleName([string]$Value) {
    $digest = [System.Security.Cryptography.SHA256]::HashData(
        [System.Text.Encoding]::UTF8.GetBytes($Value))
    return "Password Detective Plugin Outbound Block $([System.Convert]::ToHexString($digest).Substring(0, 24))"
}

function Get-AppContainerSid([string]$ProfileName) {
    $sidPointer = [IntPtr]::Zero
    $result = [PasswordDetectivePluginIsolation.NativeMethods]::CreateAppContainerProfile(
        $ProfileName,
        "Password Detective Plugin",
        "Isolated Password Detective plugin host",
        [IntPtr]::Zero,
        0,
        [ref]$sidPointer)
    if ($result -lt 0) {
        $alreadyExists = [int]0x800700B7
        if ($result -ne $alreadyExists) {
            throw "无法创建 AppContainer 配置文件，HRESULT: 0x{0:X8}" -f ($result -band 0xffffffff)
        }
        $result = [PasswordDetectivePluginIsolation.NativeMethods]::DeriveAppContainerSidFromAppContainerName(
            $ProfileName,
            [ref]$sidPointer)
        if ($result -lt 0) {
            throw "无法派生 AppContainer SID，HRESULT: 0x{0:X8}" -f ($result -band 0xffffffff)
        }
    }
    if ($sidPointer -eq [IntPtr]::Zero) {
        throw "AppContainer SID 不可用。"
    }
    return $sidPointer
}

function Get-RegistryRule([System.Security.Principal.SecurityIdentifier]$Sid) {
    $rights = [System.Security.AccessControl.RegistryRights]::WriteKey -bor [System.Security.AccessControl.RegistryRights]::Delete
    return [System.Security.AccessControl.RegistryAccessRule]::new(
        $Sid,
        $rights,
        [System.Security.AccessControl.InheritanceFlags]::ContainerInherit,
        [System.Security.AccessControl.PropagationFlags]::None,
        [System.Security.AccessControl.AccessControlType]::Deny)
}

function Open-RegistryRoot {
    $rights = [System.Security.AccessControl.RegistryRights]::ReadKey -bor [System.Security.AccessControl.RegistryRights]::ChangePermissions
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey(
        "Software",
        [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree,
        $rights)
    if ($null -eq $key) {
        throw "无法打开 HKCU\\Software 注册表根以应用插件隔离 ACL。"
    }
    return $key
}

function Test-RegistryRule(
    [Microsoft.Win32.RegistryKey]$Key,
    [System.Security.Principal.SecurityIdentifier]$Sid,
    [System.Security.AccessControl.RegistryAccessRule]$ExpectedRule
) {
    $expectedRights = $ExpectedRule.RegistryRights
    return $null -ne ($Key.GetAccessControl().GetAccessRules($true, $false, [System.Security.Principal.SecurityIdentifier]) |
        Where-Object {
            $_.IdentityReference.Value -eq $Sid.Value -and
            $_.AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Deny -and
            ($_.RegistryRights -band $expectedRights) -eq $expectedRights -and
            $_.InheritanceFlags -eq [System.Security.AccessControl.InheritanceFlags]::ContainerInherit
        } | Select-Object -First 1)
}

function Install-Isolation([string]$Value) {
    $profileName = Get-PluginProfileName $Value
    $ruleName = Get-PluginRuleName $Value
    $sidPointer = Get-AppContainerSid $profileName
    $firewallRuleAdded = $false
    $registryRuleAdded = $false
    $registryRoot = $null
    $registryRule = $null
    try {
        $sid = [System.Security.Principal.SecurityIdentifier]::new($sidPointer)
        $policy = New-Object -ComObject HNetCfg.FwPolicy2
        $existing = @($policy.Rules | Where-Object { $_.Name -eq $ruleName }) | Select-Object -First 1
        if ($null -ne $existing) {
            $policy.Rules.Remove($ruleName)
        }

        $firewallRule = New-Object -ComObject HNetCfg.FWRule
        $firewallRule.Name = $ruleName
        $firewallRule.Description = "Password Detective AppContainer outbound deny rule."
        $firewallRule.Grouping = "Password Detective Plugin Isolation"
        $firewallRule.Direction = 2
        $firewallRule.Action = 0
        $firewallRule.Enabled = $true
        $firewallRule.Profiles = [int]::MaxValue
        $firewallRule.InterfaceTypes = "All"
        $firewallRule.LocalAppPackageId = $sid.Value
        $policy.Rules.Add($firewallRule)
        $firewallRuleAdded = $true

        $registryRoot = Open-RegistryRoot
        try {
            $registryRule = Get-RegistryRule $sid
            if (-not (Test-RegistryRule $registryRoot $sid $registryRule)) {
                $security = $registryRoot.GetAccessControl()
                $security.AddAccessRule($registryRule)
                $registryRoot.SetAccessControl($security)
                $registryRuleAdded = $true
            }
        }
        finally {
            $registryRoot.Dispose()
            $registryRoot = $null
        }
        return Verify-Isolation $Value
    }
    catch {
        if ($registryRuleAdded -and $null -ne $registryRule) {
            try {
                $cleanupRoot = Open-RegistryRoot
                try {
                    $cleanupSecurity = $cleanupRoot.GetAccessControl()
                    $cleanupSecurity.RemoveAccessRuleSpecific($registryRule)
                    $cleanupRoot.SetAccessControl($cleanupSecurity)
                }
                finally {
                    $cleanupRoot.Dispose()
                }
            }
            catch {
            }
        }
        if ($firewallRuleAdded) {
            try {
                (New-Object -ComObject HNetCfg.FwPolicy2).Rules.Remove($ruleName)
            }
            catch {
            }
        }
        throw
    }
    finally {
        if ($null -ne $registryRoot) {
            $registryRoot.Dispose()
        }
        [void][PasswordDetectivePluginIsolation.NativeMethods]::FreeSid($sidPointer)
    }
}

function Remove-Isolation([string]$Value, [bool]$DeleteProfile) {
    $profileName = Get-PluginProfileName $Value
    $ruleName = Get-PluginRuleName $Value
    $policy = New-Object -ComObject HNetCfg.FwPolicy2
    $existing = @($policy.Rules | Where-Object { $_.Name -eq $ruleName }) | Select-Object -First 1
    if ($null -ne $existing) {
        $policy.Rules.Remove($ruleName)
    }

    $sidPointer = [IntPtr]::Zero
    try {
        $result = [PasswordDetectivePluginIsolation.NativeMethods]::DeriveAppContainerSidFromAppContainerName(
            $profileName,
            [ref]$sidPointer)
        if ($result -ge 0 -and $sidPointer -ne [IntPtr]::Zero) {
            $sid = [System.Security.Principal.SecurityIdentifier]::new($sidPointer)
            $registryRoot = Open-RegistryRoot
            try {
                $security = $registryRoot.GetAccessControl()
                $security.RemoveAccessRuleSpecific((Get-RegistryRule $sid))
                $registryRoot.SetAccessControl($security)
            }
            finally {
                $registryRoot.Dispose()
            }
        }
    }
    finally {
        if ($sidPointer -ne [IntPtr]::Zero) {
            [void][PasswordDetectivePluginIsolation.NativeMethods]::FreeSid($sidPointer)
        }
    }

    if ($DeleteProfile) {
        $result = [PasswordDetectivePluginIsolation.NativeMethods]::DeleteAppContainerProfile($profileName)
        if ($result -lt 0) {
            throw "无法删除 AppContainer 配置文件，HRESULT: 0x{0:X8}" -f ($result -band 0xffffffff)
        }
    }
}

function Verify-Isolation([string]$Value) {
    $profileName = Get-PluginProfileName $Value
    $ruleName = Get-PluginRuleName $Value
    $sidPointer = [IntPtr]::Zero
    try {
        $result = [PasswordDetectivePluginIsolation.NativeMethods]::DeriveAppContainerSidFromAppContainerName(
            $profileName,
            [ref]$sidPointer)
        if ($result -lt 0 -or $sidPointer -eq [IntPtr]::Zero) {
            throw "插件 AppContainer 配置文件不存在或 SID 不可用。"
        }
        $sid = [System.Security.Principal.SecurityIdentifier]::new($sidPointer)
        $firewallRule = @((New-Object -ComObject HNetCfg.FwPolicy2).Rules |
            Where-Object { $_.Name -eq $ruleName } | Select-Object -First 1)
        $firewallConfigured = $firewallRule.Count -eq 1 -and
            $firewallRule[0].Direction -eq 2 -and
            $firewallRule[0].Action -eq 0 -and
            $firewallRule[0].Enabled -and
            $firewallRule[0].LocalAppPackageId -eq $sid.Value
        $registryRoot = Open-RegistryRoot
        try {
            $registryConfigured = Test-RegistryRule $registryRoot $sid (Get-RegistryRule $sid)
        }
        finally {
            $registryRoot.Dispose()
        }
        if (-not $firewallConfigured -or -not $registryConfigured) {
            throw "插件显式隔离策略不完整。"
        }
        return [pscustomobject]@{
            plugin_id = $Value
            appcontainer_profile = $profileName
            appcontainer_sid = $sid.Value
            firewall_outbound_block = $firewallConfigured
            registry_write_deny = $registryConfigured
        }
    }
    finally {
        if ($sidPointer -ne [IntPtr]::Zero) {
            [void][PasswordDetectivePluginIsolation.NativeMethods]::FreeSid($sidPointer)
        }
    }
}

Assert-Administrator
Initialize-NativeMethods

try {
    if ($Action -eq "Probe") {
        $probePluginId = "com.passworddetective.policy-probe.$([Guid]::NewGuid().ToString('N'))"
        try {
            $output = Install-Isolation $probePluginId
        }
        finally {
            Remove-Isolation $probePluginId $true
        }
    }
    else {
        if ([string]::IsNullOrWhiteSpace($PluginId)) {
            throw "Install、Remove 和 Verify 操作必须提供 -PluginId。"
        }

        $output = switch ($Action) {
            "Install" { Install-Isolation $PluginId }
            "Remove" { Remove-Isolation $PluginId $DeleteAppContainerProfile; $null }
            "Verify" { Verify-Isolation $PluginId }
        }
    }

    $result = [pscustomobject]@{
        success = $true
        action = $Action
        result = $output
    }
    if ($ResultPath) {
        [System.IO.File]::WriteAllText(
            [System.IO.Path]::GetFullPath($ResultPath),
            ($result | ConvertTo-Json -Compress),
            [System.Text.UTF8Encoding]::new($false))
    }
    else {
        $result | ConvertTo-Json -Compress
    }
}
catch {
    if ($ResultPath) {
        $result = [pscustomobject]@{
            success = $false
            action = $Action
            error_type = $_.Exception.GetType().Name
            error_message = $_.Exception.Message
        }
        [System.IO.File]::WriteAllText(
            [System.IO.Path]::GetFullPath($ResultPath),
            ($result | ConvertTo-Json -Compress),
            [System.Text.UTF8Encoding]::new($false))
    }
    throw
}
