using System.Text.Json;
using PasswordDetective.Desktop.Plugins.Installation;
using PasswordDetective.Desktop.Plugins.Registry;
using PasswordDetective.Desktop.Plugins.Safety;
using PasswordDetective.Desktop.Plugins.Storage;

namespace PasswordDetective.Desktop.Plugins.Runtime;

public sealed class PluginRuntimeService
{
    public const int FailureDisableThreshold = 3;

    private readonly PluginRegistry _registry;
    private readonly IPluginExecutionService _execution;
    private readonly PluginSafeMode _safeMode;
    private readonly PluginLogStore _logs;
    private readonly PluginInstaller? _installer;

    public PluginRuntimeService(
        PluginRegistry registry,
        IPluginExecutionService execution,
        PluginSafeMode safeMode,
        PluginLogStore logs,
        PluginInstaller? installer = null)
    {
        _registry = registry;
        _execution = execution;
        _safeMode = safeMode;
        _logs = logs;
        _installer = installer;
    }

    public async Task<JsonElement> ExecuteAsync(
        string pluginId,
        string command,
        JsonElement input,
        CancellationToken cancellationToken = default)
    {
        var plugin = await GetRunnableAsync(pluginId, cancellationToken);
        await MarkRunningAsync(plugin, cancellationToken);
        try
        {
            var result = await _execution.ExecuteAsync(plugin, command, input, cancellationToken);
            await RecordSuccessAsync(pluginId, cancellationToken);
            return result;
        }
        catch (Exception exception)
        {
            await RecordFailureAsync(pluginId, exception, CancellationToken.None);
            throw;
        }
    }

    public async Task CheckHealthAsync(
        string pluginId,
        CancellationToken cancellationToken = default)
    {
        var plugin = await GetRunnableAsync(pluginId, cancellationToken);
        await MarkRunningAsync(plugin, cancellationToken);
        try
        {
            await _execution.CheckHealthAsync(plugin, cancellationToken);
            await RecordSuccessAsync(pluginId, cancellationToken);
        }
        catch (Exception exception)
        {
            await RecordFailureAsync(pluginId, exception, CancellationToken.None);
            throw;
        }
    }

    public Task SetEnabledAsync(
        string pluginId,
        bool enabled,
        CancellationToken cancellationToken = default) =>
        _registry.UpdateAsync(
            pluginId,
            plugin => plugin with
            {
                Enabled = enabled,
                RuntimeStatus = enabled ? "ready" : "disabled",
                UpdatedAt = DateTimeOffset.UtcNow,
                LastError = enabled ? null : plugin.LastError,
            },
            cancellationToken);

    private async Task<InstalledPlugin> GetRunnableAsync(
        string pluginId,
        CancellationToken cancellationToken)
    {
        if (_safeMode.IsActive)
        {
            throw new InvalidOperationException("桌面端处于插件安全模式，第三方插件已停止运行。");
        }

        var plugin = await _registry.GetAsync(pluginId, cancellationToken)
            ?? throw new InvalidOperationException("插件未安装。");
        if (!plugin.Enabled)
        {
            throw new InvalidOperationException("插件已停用。");
        }

        return plugin;
    }

    private Task MarkRunningAsync(InstalledPlugin plugin, CancellationToken cancellationToken) =>
        _registry.UpdateAsync(
            plugin.PluginId,
            current => current with
            {
                RuntimeStatus = "running",
                LastStartedAt = DateTimeOffset.UtcNow,
                UpdatedAt = DateTimeOffset.UtcNow,
            },
            cancellationToken);

    private Task RecordSuccessAsync(string pluginId, CancellationToken cancellationToken) =>
        _registry.UpdateAsync(
            pluginId,
            plugin => plugin with
            {
                ConsecutiveFailures = 0,
                RuntimeStatus = "ready",
                LastError = null,
                UpdatedAt = DateTimeOffset.UtcNow,
            },
            cancellationToken);

    private async Task RecordFailureAsync(
        string pluginId,
        Exception exception,
        CancellationToken cancellationToken)
    {
        var safeMessage = exception is TimeoutException
            ? "插件运行超时。"
            : "插件运行失败，详细信息已写入本地日志。";
        await _logs.AppendAsync(
            pluginId,
            "error",
            $"{exception.GetType().Name}: plugin operation failed.",
            cancellationToken);
        await _registry.UpdateAsync(
            pluginId,
            plugin =>
            {
                var failures = Math.Min(FailureDisableThreshold, plugin.ConsecutiveFailures + 1);
                return plugin with
                {
                    ConsecutiveFailures = failures,
                    Enabled = true,
                    RuntimeStatus = "failed",
                    LastError = safeMessage,
                    UpdatedAt = DateTimeOffset.UtcNow,
                };
            },
            cancellationToken);

        var failedPlugin = await _registry.GetAsync(pluginId, cancellationToken);
        if (failedPlugin is null || failedPlugin.ConsecutiveFailures < FailureDisableThreshold)
        {
            return;
        }

        if (_installer is not null && failedPlugin.CanRollback)
        {
            try
            {
                var rolledBack = await _installer.RollbackAsync(pluginId, cancellationToken);
                await _logs.AppendAsync(
                    pluginId,
                    "warning",
                    $"连续失败达到 {FailureDisableThreshold} 次，已自动回退到 {rolledBack.CurrentVersion}。",
                    cancellationToken);
                return;
            }
            catch (Exception rollbackException)
            {
                await _logs.AppendAsync(
                    pluginId,
                    "error",
                    $"自动回退失败：{rollbackException.GetType().Name}。插件已停用。",
                    cancellationToken);
            }
        }

        await _registry.UpdateAsync(
            pluginId,
            plugin => plugin with
            {
                Enabled = false,
                RuntimeStatus = "disabled",
                LastError = _installer is not null && plugin.CanRollback
                    ? "插件运行失败，自动回退失败，插件已停用。"
                    : safeMessage,
                UpdatedAt = DateTimeOffset.UtcNow,
            },
            cancellationToken);
    }
}
