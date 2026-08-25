using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Registry;
using PasswordDetective.Desktop.Plugins.Storage;

namespace PasswordDetective.Desktop.Plugins.Market;

public sealed record PluginRevocationCacheSnapshot(
    [property: JsonPropertyName("fetched_at")] DateTimeOffset FetchedAt,
    [property: JsonPropertyName("expires_at")] DateTimeOffset ExpiresAt,
    [property: JsonPropertyName("policy_version")] string PolicyVersion,
    [property: JsonPropertyName("items")] IReadOnlyList<MarketPluginRevocation> Items)
{
    public bool IsExpired(DateTimeOffset now) => ExpiresAt <= now;

    public bool Revokes(InstalledPlugin plugin, DateTimeOffset now)
    {
        var current = plugin.Versions.TryGetValue(plugin.CurrentVersion, out var version)
            ? version
            : null;
        if (current is null)
        {
            return true;
        }

        return Items.Any(item =>
            item.EffectiveAt <= now
            && (item.Scope == "plugin" && string.Equals(item.PluginSlug, plugin.PluginId, StringComparison.Ordinal)
                || item.Scope == "version"
                    && string.Equals(item.PluginSlug, plugin.PluginId, StringComparison.Ordinal)
                    && string.Equals(item.Semver, current.Version, StringComparison.Ordinal)
                || item.Scope == "signing_key"
                    && item.AffectsHistoricalVersions
                    && string.Equals(item.SigningKeyFingerprint, plugin.PublisherKeyFingerprint, StringComparison.OrdinalIgnoreCase)));
    }
}

public sealed class PluginRevocationCache
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
        WriteIndented = true,
    };

    private readonly PluginStoragePaths _paths;

    public PluginRevocationCache(PluginStoragePaths paths) => _paths = paths;

    public async Task SaveAsync(
        MarketPluginRevocationList list,
        TimeSpan ttl,
        CancellationToken cancellationToken = default)
    {
        _paths.EnsureDirectories();
        var now = DateTimeOffset.UtcNow;
        var snapshot = new PluginRevocationCacheSnapshot(
            now,
            now.Add(ttl),
            list.PolicyVersion,
            list.Items.ToArray());
        var temporary = $"{_paths.RevocationCachePath}.{Guid.NewGuid():N}.tmp";
        try
        {
            await using (var stream = new FileStream(
                             temporary,
                             FileMode.CreateNew,
                             FileAccess.Write,
                             FileShare.None,
                             4096,
                             FileOptions.Asynchronous | FileOptions.WriteThrough))
            {
                await JsonSerializer.SerializeAsync(stream, snapshot, JsonOptions, cancellationToken);
                await stream.FlushAsync(cancellationToken);
                stream.Flush(flushToDisk: true);
            }

            if (File.Exists(_paths.RevocationCachePath))
            {
                File.Replace(temporary, _paths.RevocationCachePath, null);
            }
            else
            {
                File.Move(temporary, _paths.RevocationCachePath);
            }
        }
        finally
        {
            if (File.Exists(temporary))
            {
                File.Delete(temporary);
            }
        }
    }

    public async Task<PluginRevocationCacheSnapshot?> LoadAsync(
        CancellationToken cancellationToken = default)
    {
        if (!File.Exists(_paths.RevocationCachePath))
        {
            return null;
        }

        try
        {
            await using var stream = new FileStream(
                _paths.RevocationCachePath,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                4096,
                FileOptions.Asynchronous | FileOptions.SequentialScan);
            var snapshot = await JsonSerializer.DeserializeAsync<PluginRevocationCacheSnapshot>(
                stream,
                JsonOptions,
                cancellationToken);
            if (snapshot is null)
            {
                return null;
            }

            foreach (var item in snapshot.Items)
            {
                PlatformSignatureVerifier.Verify(item);
            }

            return snapshot;
        }
        catch (Exception exception) when (
            exception is IOException
            or JsonException
            or ArgumentException
            or InvalidOperationException
            or PluginPackageException)
        {
            return null;
        }
    }
}
