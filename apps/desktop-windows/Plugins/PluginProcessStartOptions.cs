using System.Security.Cryptography;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;

namespace PasswordDetective.Desktop.Plugins;

public sealed class PluginProcessStartOptions
{
    private static readonly Regex PluginIdPattern = new(
        "^[a-z0-9]+(?:[._-][a-z0-9]+)+$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);

    public required string PluginId { get; init; }
    public required string ExecutablePath { get; init; }
    public required string WorkingDirectory { get; init; }
    public IReadOnlyList<string> Arguments { get; init; } = [];
    public IReadOnlyDictionary<string, string> Environment { get; init; } =
        new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    public long MemoryLimitBytes { get; init; } = 256L * 1024 * 1024;
    public int ActiveProcessLimit { get; init; } = 4;
    public int MaximumMessageBytes { get; init; } = Protocol.PdppProtocol.DefaultMaximumMessageBytes;
    public int MaximumStandardErrorBytes { get; init; } = 16 * 1024;
    internal bool UseAppContainer { get; init; } = true;
    internal bool DeleteAppContainerProfileOnDispose { get; init; }

    internal string AppContainerProfileName
    {
        get
        {
            var digest = SHA256.HashData(Encoding.UTF8.GetBytes(PluginId));
            return $"PasswordDetective.Plugin.{Convert.ToHexString(digest)[..24]}";
        }
    }

    internal void Validate()
    {
        if (PluginId.Length > 255 || !PluginIdPattern.IsMatch(PluginId))
        {
            throw new ArgumentException("PluginId must be a normalized reverse-domain identifier.", nameof(PluginId));
        }

        if (!Path.IsPathFullyQualified(ExecutablePath) || !File.Exists(ExecutablePath))
        {
            throw new FileNotFoundException("The plugin executable must be an existing absolute path.", ExecutablePath);
        }

        if (!Path.IsPathFullyQualified(WorkingDirectory) || !Directory.Exists(WorkingDirectory))
        {
            throw new DirectoryNotFoundException("The plugin working directory must be an existing absolute path.");
        }

        if (MemoryLimitBytes < 32L * 1024 * 1024)
        {
            throw new ArgumentOutOfRangeException(nameof(MemoryLimitBytes));
        }

        if (ActiveProcessLimit is < 1 or > 16)
        {
            throw new ArgumentOutOfRangeException(nameof(ActiveProcessLimit));
        }

        if (MaximumMessageBytes is < 1024 or > 8 * 1024 * 1024)
        {
            throw new ArgumentOutOfRangeException(nameof(MaximumMessageBytes));
        }

        if (MaximumStandardErrorBytes is < 1024 or > 1024 * 1024)
        {
            throw new ArgumentOutOfRangeException(nameof(MaximumStandardErrorBytes));
        }

        foreach (var (key, value) in Environment)
        {
            if (string.IsNullOrWhiteSpace(key) || key.Contains('=') || key.Contains('\0') || value.Contains('\0'))
            {
                throw new ArgumentException("Plugin environment entries contain invalid characters.", nameof(Environment));
            }
        }

        if (Arguments.Any(argument => argument is null || argument.Contains('\0')))
        {
            throw new ArgumentException("Plugin arguments contain invalid characters.", nameof(Arguments));
        }
    }

    internal PluginProcessStartOptions WithoutAppContainerForTests() => new()
    {
        PluginId = PluginId,
        ExecutablePath = ExecutablePath,
        WorkingDirectory = WorkingDirectory,
        Arguments = Arguments,
        Environment = Environment,
        MemoryLimitBytes = MemoryLimitBytes,
        ActiveProcessLimit = ActiveProcessLimit,
        MaximumMessageBytes = MaximumMessageBytes,
        MaximumStandardErrorBytes = MaximumStandardErrorBytes,
        UseAppContainer = false,
    };
}
