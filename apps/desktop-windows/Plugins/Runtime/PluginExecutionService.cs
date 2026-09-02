using System.IO;
using System.Text.Json;
using System.Text.RegularExpressions;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Protocol;
using PasswordDetective.Desktop.Plugins.Registry;
using PasswordDetective.Desktop.Plugins.Storage;
using PasswordDetective.Desktop.Plugins.Theme;
using PasswordDetective.Desktop.Plugins.Windows;
using PasswordDetective.Desktop.Plugins.UI;

namespace PasswordDetective.Desktop.Plugins.Runtime;

public interface IPluginInstallValidator
{
    Task ValidateAsync(
        PluginPackageInspection inspection,
        string installedDirectory,
        IReadOnlyList<string> grantedCapabilities,
        CancellationToken cancellationToken = default);
}

public interface IPluginUpgradeValidator : IPluginInstallValidator
{
    Task<PluginMigrationExecutionResult> MigrateAsync(
        PluginPackageInspection inspection,
        string installedDirectory,
        string fromVersion,
        IReadOnlyList<string> grantedCapabilities,
        CancellationToken cancellationToken = default) => Task.FromResult(
            new PluginMigrationExecutionResult("not_required", []));
}

public sealed record PluginMigrationStepExecution(
    string StepId,
    string Status,
    int AttemptCount);

public sealed record PluginMigrationExecutionResult(
    string Status,
    IReadOnlyList<PluginMigrationStepExecution> Steps);

public sealed class PluginMigrationException(
    string message,
    IReadOnlyList<PluginMigrationStepExecution> steps) : PdppProtocolException(message)
{
    public IReadOnlyList<PluginMigrationStepExecution> Steps { get; } = steps;
}

public interface IPluginExecutionService : IPluginUpgradeValidator
{
    Task<JsonElement> ExecuteAsync(
        InstalledPlugin plugin,
        string command,
        JsonElement input,
        CancellationToken cancellationToken = default);

    Task CheckHealthAsync(
        InstalledPlugin plugin,
        CancellationToken cancellationToken = default);
}

public sealed class PluginExecutionService : IPluginExecutionService
{
    private static readonly Regex MigrationStepIdPattern = new(
        "^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private readonly PluginStoragePaths _paths;
    private readonly PluginLogStore _logs;
    private readonly PluginPrivateStorage _privateStorage;
    private readonly IPluginApiBroker? _apiBroker;
    private readonly IPluginThemeService? _themeService;
    private readonly IPluginPanelHost? _panelHost;
    private readonly IPluginNotificationHost? _notificationHost;
    private readonly IWindowsPluginIsolationPolicy _isolationPolicy;

    public PluginExecutionService(
        PluginStoragePaths paths,
        PluginLogStore logs,
        IPluginApiBroker? apiBroker = null,
        IPluginThemeService? themeService = null,
        IPluginPanelHost? panelHost = null,
        IPluginNotificationHost? notificationHost = null)
        : this(
            paths,
            logs,
            apiBroker,
            themeService,
            RequiredWindowsPluginIsolationPolicy.Instance,
            panelHost,
            notificationHost)
    {
    }

    internal PluginExecutionService(
        PluginStoragePaths paths,
        PluginLogStore logs,
        IPluginApiBroker? apiBroker,
        IPluginThemeService? themeService,
        IWindowsPluginIsolationPolicy isolationPolicy,
        IPluginPanelHost? panelHost = null,
        IPluginNotificationHost? notificationHost = null)
    {
        _paths = paths;
        _logs = logs;
        _privateStorage = new PluginPrivateStorage(paths);
        _apiBroker = apiBroker;
        _themeService = themeService;
        _panelHost = panelHost;
        _notificationHost = notificationHost;
        _isolationPolicy = isolationPolicy;
    }

    public async Task ValidateAsync(
        PluginPackageInspection inspection,
        string installedDirectory,
        IReadOnlyList<string> grantedCapabilities,
        CancellationToken cancellationToken = default)
    {
        await using var session = await StartHostAsync(
            inspection.Manifest,
            inspection.EntryPointPath,
            installedDirectory,
            grantedCapabilities,
            cancellationToken);
        var host = session.Host;
        await host.InitializeAsync(
            PluginPackageVerifier.HostVersion,
            grantedCapabilities,
            TimeSpan.FromSeconds(15),
            cancellationToken);
        var health = await host.InvokeAsync<object, PdppHealthResult>(
            PdppProtocol.HealthCheckMethod,
            new { },
            TimeSpan.FromSeconds(10),
            cancellationToken);
        if (!string.Equals(health.Status, "healthy", StringComparison.Ordinal))
        {
            throw new PdppProtocolException("插件安装健康检查未返回 healthy。");
        }
    }

    public async Task<JsonElement> ExecuteAsync(
        InstalledPlugin plugin,
        string command,
        JsonElement input,
        CancellationToken cancellationToken = default)
    {
        if (!plugin.Versions.TryGetValue(plugin.CurrentVersion, out var version))
        {
            throw new InvalidOperationException("插件当前版本不存在。");
        }

        var commandManifest = version.Manifest.Commands.SingleOrDefault(item => item.Id == command);
        if (commandManifest is null)
        {
            throw new InvalidOperationException("插件命令未在已签名清单中声明。");
        }

        var installedDirectory = _paths.InstalledVersionDirectory(plugin.PluginId, version.Version);
        using var broker = new PluginHostBroker(
            plugin.PluginId,
            plugin.CurrentVersion,
            plugin.GrantedCapabilities,
            _privateStorage,
            _apiBroker,
            _themeService,
            installedDirectory,
            _panelHost,
            _notificationHost);
        var preparedInput = broker.PrepareCommandInput(
            commandManifest,
            installedDirectory,
            input);
        await using var session = await StartHostAsync(
            version.Manifest,
            version.EntryPointPath,
            installedDirectory,
            plugin.GrantedCapabilities,
            cancellationToken,
            broker);
        var host = session.Host;
        try
        {
            await host.InitializeAsync(
                PluginPackageVerifier.HostVersion,
                plugin.GrantedCapabilities,
                TimeSpan.FromSeconds(15),
                cancellationToken);
            return await host.InvokeAsync<PdppCommandParams, JsonElement>(
                PdppProtocol.ExecuteCommandMethod,
                new PdppCommandParams(command, preparedInput),
                TimeSpan.FromSeconds(version.Manifest.Limits.CommandTimeoutSeconds),
                cancellationToken);
        }
        finally
        {
            await host.DisposeAsync();
            if (!string.IsNullOrWhiteSpace(host.StandardError))
            {
                await _logs.AppendAsync(
                    plugin.PluginId,
                    "stderr",
                    $"Plugin emitted {host.StandardError.Length} characters to stderr.",
                    CancellationToken.None);
            }
        }
    }

    public async Task<PluginMigrationExecutionResult> MigrateAsync(
        PluginPackageInspection inspection,
        string installedDirectory,
        string fromVersion,
        IReadOnlyList<string> grantedCapabilities,
        CancellationToken cancellationToken = default)
    {
        await using var session = await StartHostAsync(
            inspection.Manifest,
            inspection.EntryPointPath,
            installedDirectory,
            grantedCapabilities,
            cancellationToken);
        var host = session.Host;
        await host.InitializeAsync(
            PluginPackageVerifier.HostVersion,
            grantedCapabilities,
            TimeSpan.FromSeconds(15),
            cancellationToken);
        var result = await host.InvokeAsync<PdppMigrateParams, PdppMigrateResult>(
            PdppProtocol.MigrateMethod,
            new PdppMigrateParams(fromVersion, inspection.Manifest.Version),
            TimeSpan.FromSeconds(inspection.Manifest.Limits.CommandTimeoutSeconds),
            cancellationToken);
        var steps = (result.Steps ?? [])
            .Select(step => new PluginMigrationStepExecution(
                step.StepId,
                step.Status,
                step.AttemptCount))
            .ToArray();
        ValidateMigrationResult(inspection.Manifest, result.Status, steps);
        if (result.Status == "failed")
        {
            throw new PluginMigrationException("插件数据迁移返回失败状态。", steps);
        }
        return new PluginMigrationExecutionResult(result.Status, steps);
    }

    private static void ValidateMigrationResult(
        PluginManifest manifest,
        string status,
        IReadOnlyList<PluginMigrationStepExecution> steps)
    {
        if (status is not ("migrated" or "not_required" or "failed")
            || steps.Count > 64
            || steps.Select(step => step.StepId).Distinct(StringComparer.Ordinal).Count()
            != steps.Count
            || steps.Any(step => string.IsNullOrWhiteSpace(step.StepId)
                                 || step.StepId.Length > 128
                                 || !MigrationStepIdPattern.IsMatch(step.StepId)
                                 || step.Status is not ("completed" or "skipped" or "failed")
                                 || step.AttemptCount is < 1 or > 10))
        {
            throw new PdppProtocolException("插件数据迁移返回了无效的分步证据。");
        }
        if (status == "not_required" && steps.Count != 0
            || status == "migrated" && steps.Any(step => step.Status == "failed")
            || status == "failed" && !steps.Any(step => step.Status == "failed")
            || manifest.Migration?.Required == true && status == "not_required"
            || manifest.Migration?.Required == true && steps.Count == 0)
        {
            throw new PdppProtocolException("插件数据迁移状态与分步证据不一致。");
        }
    }

    public async Task CheckHealthAsync(
        InstalledPlugin plugin,
        CancellationToken cancellationToken = default)
    {
        if (!plugin.Versions.TryGetValue(plugin.CurrentVersion, out var version))
        {
            throw new InvalidOperationException("插件当前版本不存在。");
        }

        var inspection = new PluginPackageInspection(
            string.Empty,
            version.PackageSha256,
            version.Manifest,
            version.EntryPointPath,
            string.Empty,
            plugin.PublisherKeyFingerprint,
            [],
            0);
        await ValidateAsync(
            inspection,
            _paths.InstalledVersionDirectory(plugin.PluginId, version.Version),
            plugin.GrantedCapabilities,
            cancellationToken);
    }

    private async Task<PluginRunSession> StartHostAsync(
        PluginManifest manifest,
        string entryPointPath,
        string installedDirectory,
        IReadOnlyList<string> grantedCapabilities,
        CancellationToken cancellationToken,
        IPdppHostRequestHandler? hostRequestHandler = null)
    {
        var executablePath = ResolveContainedPath(installedDirectory, entryPointPath);
        if (!File.Exists(executablePath))
        {
            throw new FileNotFoundException("插件入口点不存在。", executablePath);
        }

        var runDirectory = _paths.CreateRunDirectory(manifest.PluginId);
        var writableDirectories = new List<string>();
        if (grantedCapabilities.Contains("storage:private", StringComparer.Ordinal))
        {
            var dataDirectory = _paths.PluginDataDirectory(manifest.PluginId);
            Directory.CreateDirectory(dataDirectory);
            writableDirectories.Add(dataDirectory);
        }

        var options = new PluginProcessStartOptions
        {
            PluginId = manifest.PluginId,
            ExecutablePath = executablePath,
            WorkingDirectory = runDirectory,
            Arguments = ["--pdpp", "--manifest", Path.Combine(installedDirectory, PluginPackageVerifier.ManifestPath)],
            MemoryLimitBytes = manifest.Limits.MemoryMb * 1024L * 1024,
            ActiveProcessLimit = 1,
            CpuRatePercent = manifest.Limits.CpuPercent,
            ReadOnlyDirectories = [installedDirectory],
            WritableDirectories = writableDirectories,
        };
        try
        {
            var backend = Environment.GetEnvironmentVariable("PDPP_SANDBOX_BACKEND");
            var host = string.Equals(backend, "rust-host", StringComparison.OrdinalIgnoreCase)
                ? await PluginProcessHost.StartWithHostSandboxAsync(
                    options,
                    cancellationToken,
                    hostRequestHandler)
                : string.Equals(backend, "rust", StringComparison.OrdinalIgnoreCase)
                    ? await PluginProcessHost.StartWithRustSandboxAsync(
                        options,
                        cancellationToken,
                        hostRequestHandler)
                    : await PluginProcessHost.StartWithIsolationPolicyAsync(
                        options,
                        _isolationPolicy,
                        cancellationToken,
                        hostRequestHandler);
            return new PluginRunSession(host, runDirectory);
        }
        catch
        {
            TryDeleteDirectory(runDirectory);
            throw;
        }
    }

    private static string ResolveContainedPath(string root, string relativePath)
    {
        var fullRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar)
            + Path.DirectorySeparatorChar;
        var fullPath = Path.GetFullPath(Path.Combine(root, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        if (!fullPath.StartsWith(fullRoot, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("插件入口点逃逸安装目录。");
        }

        return fullPath;
    }

    private static void TryDeleteDirectory(string path)
    {
        try
        {
            if (Directory.Exists(path))
            {
                Directory.Delete(path, recursive: true);
            }
        }
        catch (IOException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
    }

    private sealed class PluginRunSession(
        PluginProcessHost host,
        string runDirectory) : IAsyncDisposable
    {
        public PluginProcessHost Host { get; } = host;

        public async ValueTask DisposeAsync()
        {
            try
            {
                await Host.DisposeAsync();
            }
            finally
            {
                TryDeleteDirectory(runDirectory);
            }
        }
    }
}
