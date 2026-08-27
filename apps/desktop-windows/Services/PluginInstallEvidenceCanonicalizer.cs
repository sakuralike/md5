using System.Globalization;
using System.Text;

namespace PasswordDetective.Desktop.Services;

public static class PluginInstallEvidenceCanonicalizer
{
    public const string Version = "desktop-plugin-install-evidence-v1";

    public static byte[] Build(PluginInstallEventRequest payload)
    {
        ArgumentNullException.ThrowIfNull(payload);
        var permission = payload.PermissionEvidence;
        var migration = payload.MigrationEvidence;
        var values = new (string Key, string Value)[]
        {
            ("version", Version),
            ("event_id", payload.EventId),
            ("installation_id", payload.InstallationId?.ToString("D") ?? string.Empty),
            ("plugin_slug", payload.PluginSlug),
            ("semver", payload.Semver),
            ("architecture", payload.Architecture),
            ("source", payload.Source),
            ("kind", payload.Kind),
            ("result", payload.Result),
            ("client_version", payload.ClientVersion),
            ("permission_requested", Join(permission?.RequestedCapabilities)),
            ("permission_approved", Join(permission?.ApprovedCapabilities)),
            ("permission_granted", Join(permission?.GrantedCapabilities)),
            ("publisher_key_fingerprint", permission?.PublisherKeyFingerprint ?? string.Empty),
            ("risk_tier", permission?.RiskTier ?? string.Empty),
            ("consented_at", Timestamp(permission?.ConsentedAt)),
            ("migration_from", migration?.FromVersion ?? string.Empty),
            ("migration_to", migration?.ToVersion ?? string.Empty),
            ("migration_status", migration?.Status ?? string.Empty),
            ("migration_started_at", Timestamp(migration?.StartedAt)),
            ("migration_completed_at", Timestamp(migration?.CompletedAt)),
            ("migration_steps", JoinSteps(migration?.Steps)),
        };
        return Encoding.UTF8.GetBytes(
            string.Join('\n', values.Select(item => $"{item.Key}={item.Value}")) + "\n");
    }

    private static string Join(IReadOnlyList<string>? values) => values is null
        ? string.Empty
        : string.Join(',', values.Order(StringComparer.Ordinal));

    private static string Timestamp(DateTimeOffset? value) => value?.ToUniversalTime().ToString(
        "yyyy-MM-dd'T'HH:mm:ss.fff'Z'",
        CultureInfo.InvariantCulture) ?? string.Empty;

    private static string JoinSteps(IReadOnlyList<PluginMigrationStepEvidencePayload>? steps) =>
        steps is null
            ? string.Empty
            : string.Join(
                ';',
                steps.OrderBy(step => step.StepId, StringComparer.Ordinal)
                    .Select(step => $"{step.StepId}:{step.Status}:{step.AttemptCount}"));
}
