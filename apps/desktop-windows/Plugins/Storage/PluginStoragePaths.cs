using System.IO;
using System.Text.RegularExpressions;

namespace PasswordDetective.Desktop.Plugins.Storage;

public sealed class PluginStoragePaths
{
    private static readonly Regex SegmentPattern = new(
        "^[a-z0-9]+(?:[._-][a-z0-9]+)*$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);

    public PluginStoragePaths(string rootDirectory)
    {
        RootDirectory = Path.GetFullPath(rootDirectory);
        RegistryPath = Path.Combine(RootDirectory, "registry.json");
        PackagesDirectory = Path.Combine(RootDirectory, "packages");
        InstalledDirectory = Path.Combine(RootDirectory, "installed");
        DataDirectory = Path.Combine(RootDirectory, "data");
        RunsDirectory = Path.Combine(RootDirectory, "runs");
        StagingDirectory = Path.Combine(RootDirectory, ".staging");
        LogsDirectory = Path.Combine(
            Directory.GetParent(RootDirectory)?.FullName ?? RootDirectory,
            "plugin-logs");
        SafeModeMarkerPath = Path.Combine(RootDirectory, "session.marker.json");
        RevocationCachePath = Path.Combine(RootDirectory, "market-revocations.json");
    }

    public string RootDirectory { get; }
    public string RegistryPath { get; }
    public string PackagesDirectory { get; }
    public string InstalledDirectory { get; }
    public string DataDirectory { get; }
    public string RunsDirectory { get; }
    public string StagingDirectory { get; }
    public string LogsDirectory { get; }
    public string SafeModeMarkerPath { get; }
    public string RevocationCachePath { get; }

    public static PluginStoragePaths CreateDefault() => new(Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "PasswordDetective",
        "plugins"));

    public string InstalledVersionDirectory(string pluginId, string version)
    {
        ValidateSegment(pluginId, nameof(pluginId), allowComposite: true);
        ValidateSegment(version, nameof(version), allowComposite: false);
        return Path.Combine(InstalledDirectory, pluginId, version);
    }

    public string PluginDataDirectory(string pluginId)
    {
        ValidateSegment(pluginId, nameof(pluginId), allowComposite: true);
        return Path.Combine(DataDirectory, pluginId);
    }

    public string CreateRunDirectory(string pluginId)
    {
        ValidateSegment(pluginId, nameof(pluginId), allowComposite: true);
        var path = Path.Combine(RunsDirectory, pluginId, Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(path);
        return path;
    }

    public string PackageCachePath(string packageSha256)
    {
        if (packageSha256.Length != 64 || packageSha256.Any(character => !Uri.IsHexDigit(character)))
        {
            throw new ArgumentException("Package SHA-256 is invalid.", nameof(packageSha256));
        }

        return Path.Combine(PackagesDirectory, $"{packageSha256.ToLowerInvariant()}.pdpkg");
    }

    public string PluginLogPath(string pluginId)
    {
        ValidateSegment(pluginId, nameof(pluginId), allowComposite: true);
        return Path.Combine(LogsDirectory, $"{pluginId}.log");
    }

    public void EnsureDirectories()
    {
        Directory.CreateDirectory(RootDirectory);
        Directory.CreateDirectory(PackagesDirectory);
        Directory.CreateDirectory(InstalledDirectory);
        Directory.CreateDirectory(DataDirectory);
        Directory.CreateDirectory(RunsDirectory);
        Directory.CreateDirectory(StagingDirectory);
        Directory.CreateDirectory(LogsDirectory);
    }

    private static void ValidateSegment(string value, string parameterName, bool allowComposite)
    {
        if (string.IsNullOrWhiteSpace(value)
            || value.Length > 255
            || !SegmentPattern.IsMatch(value)
            || !allowComposite && value.Count(character => character == '.') != 2)
        {
            throw new ArgumentException("Plugin storage path segment is invalid.", parameterName);
        }
    }
}
