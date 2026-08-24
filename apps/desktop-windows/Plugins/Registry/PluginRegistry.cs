using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using PasswordDetective.Desktop.Plugins.Storage;

namespace PasswordDetective.Desktop.Plugins.Registry;

public sealed class PluginRegistry
{
    private const int SchemaVersion = 1;
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        WriteIndented = true,
    };

    private readonly PluginStoragePaths _paths;
    private readonly SemaphoreSlim _lock = new(1, 1);

    public PluginRegistry(PluginStoragePaths paths) => _paths = paths;

    public async Task<IReadOnlyList<InstalledPlugin>> GetAllAsync(
        CancellationToken cancellationToken = default)
    {
        await _lock.WaitAsync(cancellationToken);
        try
        {
            return (await LoadCoreAsync(cancellationToken)).Plugins
                .OrderBy(plugin => plugin.DisplayName, StringComparer.CurrentCulture)
                .ToArray();
        }
        finally
        {
            _lock.Release();
        }
    }

    public async Task<InstalledPlugin?> GetAsync(
        string pluginId,
        CancellationToken cancellationToken = default)
    {
        await _lock.WaitAsync(cancellationToken);
        try
        {
            return (await LoadCoreAsync(cancellationToken)).Plugins
                .SingleOrDefault(plugin => plugin.PluginId == pluginId);
        }
        finally
        {
            _lock.Release();
        }
    }

    public Task UpsertAsync(InstalledPlugin plugin, CancellationToken cancellationToken = default) =>
        MutateAsync(
            plugins =>
            {
                var index = plugins.FindIndex(item => item.PluginId == plugin.PluginId);
                if (index < 0)
                {
                    plugins.Add(Validate(plugin));
                }
                else
                {
                    plugins[index] = Validate(plugin);
                }
            },
            cancellationToken);

    public Task UpdateAsync(
        string pluginId,
        Func<InstalledPlugin, InstalledPlugin> update,
        CancellationToken cancellationToken = default) =>
        MutateAsync(
            plugins =>
            {
                var index = plugins.FindIndex(item => item.PluginId == pluginId);
                if (index < 0)
                {
                    throw new PluginRegistryException("插件未安装。");
                }

                plugins[index] = Validate(update(plugins[index]));
            },
            cancellationToken);

    public Task RemoveAsync(string pluginId, CancellationToken cancellationToken = default) =>
        MutateAsync(
            plugins => plugins.RemoveAll(plugin => plugin.PluginId == pluginId),
            cancellationToken);

    private async Task MutateAsync(
        Action<List<InstalledPlugin>> mutate,
        CancellationToken cancellationToken)
    {
        await _lock.WaitAsync(cancellationToken);
        try
        {
            var document = await LoadCoreAsync(cancellationToken);
            var plugins = document.Plugins.ToList();
            mutate(plugins);
            await SaveCoreAsync(
                new PluginRegistryDocument(SchemaVersion, plugins),
                cancellationToken);
        }
        finally
        {
            _lock.Release();
        }
    }

    private async Task<PluginRegistryDocument> LoadCoreAsync(CancellationToken cancellationToken)
    {
        if (!File.Exists(_paths.RegistryPath))
        {
            return new PluginRegistryDocument(SchemaVersion, []);
        }

        try
        {
            await using var stream = new FileStream(
                _paths.RegistryPath,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                bufferSize: 4096,
                FileOptions.Asynchronous | FileOptions.SequentialScan);
            var document = await JsonSerializer.DeserializeAsync<PluginRegistryDocument>(
                stream,
                JsonOptions,
                cancellationToken);
            if (document is null
                || document.SchemaVersion != SchemaVersion
                || document.Plugins.Select(plugin => plugin.PluginId).Distinct(StringComparer.Ordinal).Count()
                != document.Plugins.Count)
            {
                throw new PluginRegistryException("插件注册表版本或内容无效。");
            }

            return document with { Plugins = document.Plugins.Select(Validate).ToArray() };
        }
        catch (PluginRegistryException)
        {
            throw;
        }
        catch (Exception exception) when (exception is JsonException or IOException)
        {
            throw new PluginRegistryException("无法读取插件注册表，未执行自动重置。", exception);
        }
    }

    private async Task SaveCoreAsync(
        PluginRegistryDocument document,
        CancellationToken cancellationToken)
    {
        _paths.EnsureDirectories();
        var temporaryPath = Path.Combine(
            _paths.RootDirectory,
            $"registry.{Guid.NewGuid():N}.tmp");
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
                await JsonSerializer.SerializeAsync(stream, document, JsonOptions, cancellationToken);
                await stream.FlushAsync(cancellationToken);
                stream.Flush(flushToDisk: true);
            }

            if (File.Exists(_paths.RegistryPath))
            {
                File.Replace(temporaryPath, _paths.RegistryPath, destinationBackupFileName: null);
            }
            else
            {
                File.Move(temporaryPath, _paths.RegistryPath);
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            throw new PluginRegistryException("无法原子写入插件注册表。", exception);
        }
        finally
        {
            if (File.Exists(temporaryPath))
            {
                File.Delete(temporaryPath);
            }
        }
    }

    private static InstalledPlugin Validate(InstalledPlugin plugin)
    {
        if (plugin.Source != PluginSource.LocalUnreviewed
            || plugin.Versions is null
            || !plugin.Versions.TryGetValue(plugin.CurrentVersion, out var currentVersion)
            || currentVersion?.Manifest is null
            || plugin.PluginId != currentVersion.Manifest.PluginId
            || plugin.Versions.Any(pair => pair.Value?.Manifest is null
                                           || pair.Key != pair.Value.Version
                                           || pair.Value.Manifest.PluginId != plugin.PluginId)
            || plugin.RollbackVersion is not null && !plugin.Versions.ContainsKey(plugin.RollbackVersion)
            || plugin.ConsecutiveFailures is < 0 or > 3
            || plugin.GrantedCapabilities is null
            || plugin.RuntimeStatus is not ("ready" or "running" or "failed" or "disabled"))
        {
            throw new PluginRegistryException("插件注册表条目无效或来源不是本地未审核。");
        }

        return plugin with
        {
            Source = PluginSource.LocalUnreviewed,
            GrantedCapabilities = plugin.GrantedCapabilities
                .Distinct(StringComparer.Ordinal)
                .Order(StringComparer.Ordinal)
                .ToArray(),
        };
    }
}
