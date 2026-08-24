using System.IO;
using System.Text;

namespace PasswordDetective.Desktop.Plugins.Storage;

public sealed class PluginLogStore
{
    public const long MaximumLogBytes = 1024 * 1024;
    public const int MaximumEntryCharacters = 8192;

    private readonly PluginStoragePaths _paths;
    private readonly SemaphoreSlim _lock = new(1, 1);

    public PluginLogStore(PluginStoragePaths paths) => _paths = paths;

    public async Task AppendAsync(
        string pluginId,
        string level,
        string message,
        CancellationToken cancellationToken = default)
    {
        var safeLevel = new string(level
            .Where(character => char.IsAsciiLetterOrDigit(character))
            .Take(16)
            .ToArray());
        var safeMessage = new string(message
            .Replace('\r', ' ')
            .Replace('\n', ' ')
            .Where(character => !char.IsControl(character))
            .Take(MaximumEntryCharacters)
            .ToArray());
        var line = $"[{DateTimeOffset.UtcNow:O}] [{safeLevel}] {safeMessage}{Environment.NewLine}";
        var bytes = Encoding.UTF8.GetBytes(line);

        await _lock.WaitAsync(cancellationToken);
        try
        {
            _paths.EnsureDirectories();
            var path = _paths.PluginLogPath(pluginId);
            if (File.Exists(path) && new FileInfo(path).Length + bytes.Length > MaximumLogBytes)
            {
                File.Move(path, $"{path}.previous", overwrite: true);
            }

            await using var stream = new FileStream(
                path,
                FileMode.Append,
                FileAccess.Write,
                FileShare.Read,
                bufferSize: 4096,
                FileOptions.Asynchronous | FileOptions.WriteThrough);
            await stream.WriteAsync(bytes, cancellationToken);
            await stream.FlushAsync(cancellationToken);
        }
        finally
        {
            _lock.Release();
        }
    }
}
