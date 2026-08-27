using System.Text.Json.Serialization;

namespace PasswordDetective.Desktop.Plugins.Packages;

public sealed record PluginManifest(
    [property: JsonPropertyName("schema")] string Schema,
    [property: JsonPropertyName("plugin_id")] string PluginId,
    [property: JsonPropertyName("version")] string Version,
    [property: JsonPropertyName("display_name")] string DisplayName,
    [property: JsonPropertyName("description")] string Description,
    [property: JsonPropertyName("publisher_key_id")] string PublisherKeyId,
    [property: JsonPropertyName("publisher_public_key")] string PublisherPublicKey,
    [property: JsonPropertyName("protocol")] PluginProtocolRange Protocol,
    [property: JsonPropertyName("host")] PluginHostRange Host,
    [property: JsonPropertyName("runtime")] PluginRuntimeManifest Runtime,
    [property: JsonPropertyName("commands")] IReadOnlyList<PluginCommandManifest> Commands,
    [property: JsonPropertyName("capabilities")] PluginCapabilitiesManifest Capabilities,
    [property: JsonPropertyName("limits")] PluginLimitsManifest Limits,
    [property: JsonPropertyName("migration")] PluginMigrationManifest? Migration = null);

public sealed record PluginProtocolRange(
    [property: JsonPropertyName("min")] int Min,
    [property: JsonPropertyName("max")] int Max);

public sealed record PluginHostRange(
    [property: JsonPropertyName("min_version")] string MinVersion,
    [property: JsonPropertyName("max_version")] string MaxVersion);

public sealed record PluginRuntimeManifest(
    [property: JsonPropertyName("kind")] string Kind,
    [property: JsonPropertyName("entrypoints")] IReadOnlyDictionary<string, string> Entrypoints);

public sealed record PluginCommandManifest(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("input_schema")] string InputSchema);

public sealed record PluginCapabilitiesManifest(
    [property: JsonPropertyName("required")] IReadOnlyList<string> Required,
    [property: JsonPropertyName("optional")] IReadOnlyList<string> Optional);

public sealed record PluginLimitsManifest(
    [property: JsonPropertyName("memory_mb")] int MemoryMb,
    [property: JsonPropertyName("cpu_percent")] int CpuPercent,
    [property: JsonPropertyName("command_timeout_seconds")] int CommandTimeoutSeconds,
    [property: JsonPropertyName("child_processes")] int ChildProcesses);

public sealed record PluginMigrationManifest(
    [property: JsonPropertyName("required")] bool Required,
    [property: JsonPropertyName("from_versions")] IReadOnlyList<string> FromVersions,
    [property: JsonPropertyName("strategy")] string Strategy);

public sealed record PluginPackageFile(
    string Path,
    long Length,
    string Sha256);

public sealed record PluginPackageInspection(
    string PackagePath,
    string PackageSha256,
    PluginManifest Manifest,
    string EntryPointPath,
    string Architecture,
    string PublisherKeyFingerprint,
    IReadOnlyList<PluginPackageFile> Files,
    long ExpandedSizeBytes);
