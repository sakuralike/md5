using System.Text.Json;
using PasswordDetective.Desktop.Plugins.Packages;

namespace PasswordDetective.Desktop.Plugins.Permissions;

public sealed record PluginPermissionDecision(
    IReadOnlyList<string> Granted,
    IReadOnlyList<string> DeniedRequired,
    IReadOnlyList<string> DeniedOptional,
    IReadOnlyList<PluginPermissionGrant> GrantedGrants);

public sealed record PluginPermissionGrant(
    string Capability,
    JsonElement? Constraints,
    PluginCapabilityQuota? Quota,
    DateTimeOffset? ExpiresAt);

public sealed class PluginPermissionPolicy
{
    public static readonly IReadOnlySet<string> LocallySupportedCapabilities = new HashSet<string>(
        [
            "ui:command",
            "ui:theme",
            "ui:window",
            "ui:panel",
            "ui:notification",
            "file:write:scoped",
            "clipboard:read",
            "clipboard:write",
            "compute:hash",
            "storage:private",
            "file:read:selected",
        ],
        StringComparer.Ordinal);

    public static readonly IReadOnlySet<string> MarketSupportedCapabilities = new HashSet<string>(
        LocallySupportedCapabilities.Concat(
        [
            "api:profile:read",
            "api:hash:read",
            "api:verification:submit",
        ]),
        StringComparer.Ordinal);

    public static readonly IReadOnlySet<string> KnownCapabilities = new HashSet<string>(
        LocallySupportedCapabilities.Concat(
        [
            "api:profile:read",
            "api:hash:read",
            "api:verification:submit",
            "network:internet",
            "secret:candidate:ephemeral",
            "process:spawn",
            "system:persistence",
            "credential:read",
        ]),
        StringComparer.Ordinal);

    public PluginPermissionDecision Evaluate(
        PluginManifest manifest,
        IEnumerable<string> userGrantedCapabilities)
        => EvaluateCore(manifest, userGrantedCapabilities, LocallySupportedCapabilities);

    public PluginPermissionDecision EvaluateMarket(
        PluginManifest manifest,
        IEnumerable<string> userGrantedCapabilities)
        => EvaluateCore(manifest, userGrantedCapabilities, MarketSupportedCapabilities);

    private static PluginPermissionDecision EvaluateCore(
        PluginManifest manifest,
        IEnumerable<string> userGrantedCapabilities,
        IReadOnlySet<string> supportedCapabilities)
    {
        var required = ValidateRequested(manifest.Capabilities.Required, "必需权限");
        var optional = ValidateRequested(manifest.Capabilities.Optional, "可选权限");
        if (required.Intersect(optional, StringComparer.Ordinal).Any())
        {
            throw new PluginPackageException("同一插件权限不能同时声明为必需和可选。");
        }

        var userGranted = userGrantedCapabilities.ToHashSet(StringComparer.Ordinal);
        var deniedRequired = required
            .Where(capability => !supportedCapabilities.Contains(capability)
                                 || !userGranted.Contains(capability))
            .Order(StringComparer.Ordinal)
            .ToArray();
        var deniedOptional = optional
            .Where(capability => !supportedCapabilities.Contains(capability)
                                 || !userGranted.Contains(capability))
            .Order(StringComparer.Ordinal)
            .ToArray();
        var granted = required.Concat(optional)
            .Where(capability => supportedCapabilities.Contains(capability)
                                 && userGranted.Contains(capability))
            .Distinct(StringComparer.Ordinal)
            .Order(StringComparer.Ordinal)
            .ToArray();
        var grantedSet = granted.ToHashSet(StringComparer.Ordinal);
        var grants = manifest.Capabilities.Grants is null
            ? []
            : manifest.Capabilities.Grants
                .Where(item => grantedSet.Contains(item.Capability))
                .Select(item => new PluginPermissionGrant(
                    item.Capability,
                    item.Constraints,
                    item.Quota,
                    item.TtlSeconds is { } seconds
                        ? DateTimeOffset.UtcNow.AddSeconds(seconds)
                        : null))
                .ToArray();
        return new PluginPermissionDecision(granted, deniedRequired, deniedOptional, grants);
    }

    private static string[] ValidateRequested(IEnumerable<string> capabilities, string fieldName)
    {
        var values = capabilities.ToArray();
        if (values.Length > 64
            || values.Any(value => string.IsNullOrWhiteSpace(value)
                                   || value.Length > 128
                                   || !KnownCapabilities.Contains(value))
            || values.Distinct(StringComparer.Ordinal).Count() != values.Length)
        {
            throw new PluginPackageException($"插件{fieldName}包含未知、重复或无效项。");
        }

        return values;
    }
}
