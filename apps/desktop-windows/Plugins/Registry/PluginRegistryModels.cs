using System.Text.Json.Serialization;
using PasswordDetective.Desktop.Plugins.Packages;

namespace PasswordDetective.Desktop.Plugins.Registry;

public static class PluginSource
{
    public const string LocalUnreviewed = "local_unreviewed";
    public const string LocalUnreviewedLabel = "未审核";
    public const string MarketReviewed = "market_reviewed";
    public const string MarketReviewedLabel = "平台已审核";
}

public sealed record InstalledPluginVersion(
    string Version,
    string PackageSha256,
    string EntryPointPath,
    PluginManifest Manifest,
    DateTimeOffset InstalledAt);

public sealed record PluginPermissionConsent(
    string Version,
    IReadOnlyList<string> RequestedCapabilities,
    IReadOnlyList<string> ApprovedCapabilities,
    IReadOnlyList<string> GrantedCapabilities,
    string PublisherKeyFingerprint,
    string RiskTier,
    DateTimeOffset ConsentedAt);

public sealed record InstalledPlugin(
    string PluginId,
    string DisplayName,
    string Description,
    string PublisherKeyId,
    string PublisherKeyFingerprint,
    string Source,
    string CurrentVersion,
    string? RollbackVersion,
    IReadOnlyDictionary<string, InstalledPluginVersion> Versions,
    IReadOnlyList<string> GrantedCapabilities,
    bool Enabled,
    int ConsecutiveFailures,
    string RuntimeStatus,
    string? LastError,
    DateTimeOffset InstalledAt,
    DateTimeOffset UpdatedAt,
    DateTimeOffset? LastStartedAt,
    string? PlatformKeyId = null,
    string? PlatformPublicKeyBase64 = null,
    string? PlatformSignatureBase64 = null,
    string? ReviewPolicyVersion = null,
    string RiskTier = "standard",
    IReadOnlyDictionary<string, PluginPermissionConsent>? PermissionConsents = null,
    IReadOnlyDictionary<string, PluginMigrationRecord>? MigrationRecords = null)
{
    [JsonIgnore]
    public string ReviewLabel => Source == PluginSource.MarketReviewed
        ? PluginSource.MarketReviewedLabel
        : PluginSource.LocalUnreviewedLabel;

    [JsonIgnore]
    public bool CanRollback => RollbackVersion is not null && Versions.ContainsKey(RollbackVersion);
}

public sealed record PluginMigrationRecord(
    string FromVersion,
    string ToVersion,
    string Status,
    DateTimeOffset StartedAt,
    DateTimeOffset? CompletedAt,
    string? Error,
    IReadOnlyList<PluginMigrationStepRecord>? Steps = null);

public sealed record PluginMigrationStepRecord(
    string StepId,
    string Status,
    int AttemptCount);

internal sealed record PluginRegistryDocument(
    int SchemaVersion,
    IReadOnlyList<InstalledPlugin> Plugins);

public sealed class PluginRegistryException : Exception
{
    public PluginRegistryException(string message) : base(message)
    {
    }

    public PluginRegistryException(string message, Exception innerException) : base(message, innerException)
    {
    }
}
