using System.Collections;
using System.Reflection;
using Microsoft.Win32;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;

namespace PasswordDetective.Desktop.Plugins.Windows;

internal interface IWindowsPluginIsolationPolicy
{
    void Verify(string pluginId, AppContainerProfile profile);
}

internal sealed class RequiredWindowsPluginIsolationPolicy : IWindowsPluginIsolationPolicy
{
    public static RequiredWindowsPluginIsolationPolicy Instance { get; } = new();

    public void Verify(string pluginId, AppContainerProfile profile)
    {
        if (!HasOutboundFirewallBlock(pluginId, profile.Sid)
            || !HasRegistryWriteDeny(profile.Sid))
        {
            throw new PluginExplicitIsolationException(
                $"插件未安装完整的显式网络和注册表隔离策略，已拒绝启动。管理员需要运行桌面安装目录中的 desktop-plugin-isolation.ps1 -Action Install -PluginId {pluginId}。");
        }
    }

    private static bool HasOutboundFirewallBlock(string pluginId, SecurityIdentifier appContainerSid)
    {
        var policyType = Type.GetTypeFromProgID("HNetCfg.FwPolicy2")
            ?? throw new PluginExplicitIsolationException("Windows 防火墙策略接口不可用，已拒绝启动插件。");
        var policy = Activator.CreateInstance(policyType)
            ?? throw new PluginExplicitIsolationException("Windows 防火墙策略接口不可用，已拒绝启动插件。");
        var rules = ReadComProperty(policy, "Rules") as IEnumerable
            ?? throw new PluginExplicitIsolationException("无法读取 Windows 防火墙策略，已拒绝启动插件。");
        var ruleName = BuildFirewallRuleName(pluginId);
        foreach (var rule in rules)
        {
            if (rule is null || !string.Equals(ReadComProperty(rule, "Name") as string, ruleName, StringComparison.Ordinal))
            {
                continue;
            }

            return Equals(ReadComProperty(rule, "Direction"), 2)
                && Equals(ReadComProperty(rule, "Action"), 0)
                && Equals(ReadComProperty(rule, "Enabled"), true)
                && string.Equals(
                    ReadComProperty(rule, "LocalAppPackageId") as string,
                    appContainerSid.Value,
                    StringComparison.Ordinal);
        }

        return false;
    }

    private static bool HasRegistryWriteDeny(SecurityIdentifier appContainerSid)
    {
        using var root = Microsoft.Win32.Registry.CurrentUser.OpenSubKey("Software", writable: false)
            ?? throw new PluginExplicitIsolationException("无法读取插件注册表隔离策略，已拒绝启动插件。");
        var requiredRights = RegistryRights.WriteKey | RegistryRights.Delete;
        return root.GetAccessControl()
            .GetAccessRules(includeExplicit: true, includeInherited: false, typeof(SecurityIdentifier))
            .OfType<RegistryAccessRule>()
            .Any(rule => rule.IdentityReference.Value == appContainerSid.Value
                && rule.AccessControlType == AccessControlType.Deny
                && (rule.RegistryRights & requiredRights) == requiredRights
                && rule.InheritanceFlags == InheritanceFlags.ContainerInherit);
    }

    internal static string BuildFirewallRuleName(string pluginId)
    {
        var digest = SHA256.HashData(Encoding.UTF8.GetBytes(pluginId));
        return $"Password Detective Plugin Outbound Block {Convert.ToHexString(digest)[..24]}";
    }

    private static object? ReadComProperty(object instance, string name) =>
        instance.GetType().InvokeMember(
            name,
            BindingFlags.GetProperty,
            binder: null,
            target: instance,
            args: null);
}

internal sealed class NoOpWindowsPluginIsolationPolicy : IWindowsPluginIsolationPolicy
{
    public static NoOpWindowsPluginIsolationPolicy Instance { get; } = new();

    public void Verify(string pluginId, AppContainerProfile profile)
    {
    }
}

public sealed class PluginExplicitIsolationException(string message) : PdppProtocolException(message);
