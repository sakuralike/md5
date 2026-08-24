using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace PasswordDetective.Desktop.Plugins.Storage;

public sealed class PluginPrivateStorage
{
    public const long DefaultQuotaBytes = 100L * 1024 * 1024;
    public const int MaximumValueBytes = 1024 * 1024;

    private static readonly Regex KeyPattern = new(
        "^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private readonly PluginStoragePaths _paths;
    private readonly long _quotaBytes;
    private readonly SemaphoreSlim _lock = new(1, 1);

    public PluginPrivateStorage(PluginStoragePaths paths, long quotaBytes = DefaultQuotaBytes)
    {
        if (quotaBytes is < MaximumValueBytes or > 1024L * 1024 * 1024)
        {
            throw new ArgumentOutOfRangeException(nameof(quotaBytes));
        }

        _paths = paths;
        _quotaBytes = quotaBytes;
    }

    public async Task<JsonElement?> GetAsync(
        string pluginId,
        string key,
        CancellationToken cancellationToken = default)
    {
        ValidateKey(key);
        var path = ValuePath(pluginId, key);
        if (!File.Exists(path))
        {
            return null;
        }

        await using var stream = new FileStream(
            path,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            bufferSize: 4096,
            FileOptions.Asynchronous | FileOptions.SequentialScan);
        using var document = await JsonDocument.ParseAsync(
            stream,
            new JsonDocumentOptions { MaxDepth = 32 },
            cancellationToken);
        return document.RootElement.Clone();
    }

    public async Task SetAsync(
        string pluginId,
        string key,
        JsonElement value,
        CancellationToken cancellationToken = default)
    {
        ValidateKey(key);
        var bytes = JsonSerializer.SerializeToUtf8Bytes(value);
        if (bytes.Length > MaximumValueBytes)
        {
            throw new InvalidOperationException("插件私有存储单值超过 1 MiB 限制。");
        }

        await _lock.WaitAsync(cancellationToken);
        try
        {
            var directory = Path.Combine(_paths.PluginDataDirectory(pluginId), "storage");
            Directory.CreateDirectory(directory);
            var path = ValuePath(pluginId, key);
            var currentLength = File.Exists(path) ? new FileInfo(path).Length : 0;
            var used = Directory.EnumerateFiles(directory, "*.json", SearchOption.TopDirectoryOnly)
                .Sum(file => new FileInfo(file).Length);
            if (used - currentLength + bytes.Length > _quotaBytes)
            {
                throw new InvalidOperationException("插件私有存储已达到配额上限。");
            }

            var temporaryPath = Path.Combine(directory, $"{Guid.NewGuid():N}.tmp");
            try
            {
                await using (var stream = new FileStream(
                                 temporaryPath,
                                 FileMode.CreateNew,
                                 FileAccess.Write,
                                 FileShare.None,
                                 bufferSize: 4096,
                                 FileOptions.Asynchronous | FileOptions.WriteThrough))
                {
                    await stream.WriteAsync(bytes, cancellationToken);
                    await stream.FlushAsync(cancellationToken);
                    stream.Flush(flushToDisk: true);
                }

                if (File.Exists(path))
                {
                    File.Replace(temporaryPath, path, destinationBackupFileName: null);
                }
                else
                {
                    File.Move(temporaryPath, path);
                }
            }
            finally
            {
                if (File.Exists(temporaryPath))
                {
                    File.Delete(temporaryPath);
                }
            }
        }
        finally
        {
            _lock.Release();
        }
    }

    public bool Remove(string pluginId, string key)
    {
        ValidateKey(key);
        var path = ValuePath(pluginId, key);
        if (!File.Exists(path))
        {
            return false;
        }

        File.Delete(path);
        return true;
    }

    private string ValuePath(string pluginId, string key)
    {
        var digest = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(key)));
        return Path.Combine(_paths.PluginDataDirectory(pluginId), "storage", $"{digest}.json");
    }

    private static void ValidateKey(string key)
    {
        if (!KeyPattern.IsMatch(key))
        {
            throw new ArgumentException("Plugin storage key is invalid.", nameof(key));
        }
    }
}
