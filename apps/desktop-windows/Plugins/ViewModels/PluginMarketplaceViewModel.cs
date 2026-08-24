using System.Collections.ObjectModel;
using System.ComponentModel;
using System.IO;
using System.Runtime.CompilerServices;
using System.Text.Json;
using PasswordDetective.Desktop.Infrastructure;
using PasswordDetective.Desktop.Plugins.Installation;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Permissions;
using PasswordDetective.Desktop.Plugins.Registry;
using PasswordDetective.Desktop.Plugins.Runtime;
using PasswordDetective.Desktop.Plugins.Safety;
using PasswordDetective.Desktop.Plugins.Storage;
using PasswordDetective.Desktop.Plugins.UI;

namespace PasswordDetective.Desktop.Plugins.ViewModels;

public sealed class PluginMarketplaceViewModel : INotifyPropertyChanged
{
    private static readonly JsonSerializerOptions ResultJsonOptions = new()
    {
        WriteIndented = true,
    };

    private readonly PluginStoragePaths _paths;
    private readonly PluginInstaller _installer;
    private readonly PluginPermissionPolicy _permissionPolicy;
    private readonly PluginRegistry _registry;
    private readonly PluginRuntimeService _runtime;
    private readonly PluginSafeMode _safeMode;
    private readonly IPluginDialogService _dialogs;
    private PluginPackageInspection? _selectedPackage;
    private InstalledPlugin? _selectedInstalledPlugin;
    private PluginCommandManifest? _selectedCommand;
    private PluginCommandForm? _commandForm;
    private string _selectedPackagePath = string.Empty;
    private string _status = "请选择本地 .pdpkg 插件包。";
    private string _commandResult = "尚未执行插件命令。";
    private bool _isBusy;

    public PluginMarketplaceViewModel(
        PluginStoragePaths paths,
        PluginInstaller installer,
        PluginPermissionPolicy permissionPolicy,
        PluginRegistry registry,
        PluginRuntimeService runtime,
        PluginSafeMode safeMode,
        IPluginDialogService dialogs)
    {
        _paths = paths;
        _installer = installer;
        _permissionPolicy = permissionPolicy;
        _registry = registry;
        _runtime = runtime;
        _safeMode = safeMode;
        _dialogs = dialogs;
        InitializeCommand = new AsyncRelayCommand(RefreshAsync, () => !IsBusy);
        BrowsePackageCommand = new AsyncRelayCommand(BrowsePackageAsync, () => !IsBusy);
        InstallPackageCommand = new AsyncRelayCommand(InstallPackageAsync, () => !IsBusy && SelectedPackage is not null);
        RefreshCommand = new AsyncRelayCommand(RefreshAsync, () => !IsBusy);
        ToggleEnabledCommand = new AsyncRelayCommand(ToggleEnabledAsync, () => !IsBusy && SelectedInstalledPlugin is not null);
        HealthCheckCommand = new AsyncRelayCommand(HealthCheckAsync, CanRunSelectedPlugin);
        ExecuteCommand = new AsyncRelayCommand(ExecuteSelectedCommandAsync, CanExecuteSelectedCommand);
        RollbackCommand = new AsyncRelayCommand(RollbackAsync, () => !IsBusy && SelectedInstalledPlugin?.CanRollback == true);
        UninstallCommand = new AsyncRelayCommand(UninstallAsync, () => !IsBusy && SelectedInstalledPlugin is not null);
        LeaveSafeModeCommand = new RelayCommand(LeaveSafeMode, () => _safeMode.IsActive && !IsBusy);
    }

    public ObservableCollection<InstalledPlugin> InstalledPlugins { get; } = [];
    public ObservableCollection<PluginCommandManifest> AvailableCommands { get; } = [];

    public PluginPackageInspection? SelectedPackage
    {
        get => _selectedPackage;
        private set
        {
            if (!SetField(ref _selectedPackage, value))
            {
                return;
            }

            OnPropertyChanged(nameof(HasSelectedPackage));
            OnPropertyChanged(nameof(PackageRequiredCapabilities));
            OnPropertyChanged(nameof(PackageOptionalCapabilities));
            OnPropertyChanged(nameof(PackageFileSummary));
            NotifyCommands();
        }
    }

    public InstalledPlugin? SelectedInstalledPlugin
    {
        get => _selectedInstalledPlugin;
        set
        {
            if (!SetField(ref _selectedInstalledPlugin, value))
            {
                return;
            }

            LoadCommands();
            OnPropertyChanged(nameof(HasSelectedInstalledPlugin));
            OnPropertyChanged(nameof(SelectedPluginState));
            NotifyCommands();
        }
    }

    public PluginCommandManifest? SelectedCommand
    {
        get => _selectedCommand;
        set
        {
            if (!SetField(ref _selectedCommand, value))
            {
                return;
            }

            LoadCommandForm();
            NotifyCommands();
        }
    }

    public PluginCommandForm? CommandForm
    {
        get => _commandForm;
        private set
        {
            if (SetField(ref _commandForm, value))
            {
                OnPropertyChanged(nameof(HasCommandForm));
                NotifyCommands();
            }
        }
    }

    public string SelectedPackagePath
    {
        get => _selectedPackagePath;
        private set => SetField(ref _selectedPackagePath, value);
    }

    public string Status
    {
        get => _status;
        private set => SetField(ref _status, value);
    }

    public string CommandResult
    {
        get => _commandResult;
        private set => SetField(ref _commandResult, value);
    }

    public bool IsBusy
    {
        get => _isBusy;
        private set
        {
            if (SetField(ref _isBusy, value))
            {
                NotifyCommands();
            }
        }
    }

    public bool IsSafeMode => _safeMode.IsActive;
    public bool HasSelectedPackage => SelectedPackage is not null;
    public bool HasSelectedInstalledPlugin => SelectedInstalledPlugin is not null;
    public bool HasCommandForm => CommandForm is not null;
    public string ReviewLabel => PluginSource.LocalUnreviewedLabel;
    public string SafeModeStatus => IsSafeMode
        ? "检测到上次桌面会话未正常退出，插件安全模式已启用。"
        : "插件运行隔离已启用。";
    public string PackageRequiredCapabilities => FormatCapabilities(
        SelectedPackage?.Manifest.Capabilities.Required);
    public string PackageOptionalCapabilities => FormatCapabilities(
        SelectedPackage?.Manifest.Capabilities.Optional);
    public string PackageFileSummary => SelectedPackage is null
        ? "尚未选择插件包"
        : $"{SelectedPackage.Files.Count} 个文件，展开后 {SelectedPackage.ExpandedSizeBytes:N0} 字节";
    public string SelectedPluginState => SelectedInstalledPlugin is null
        ? "请选择已安装插件"
        : $"{SelectedInstalledPlugin.RuntimeStatus} / {(SelectedInstalledPlugin.Enabled ? "已启用" : "已停用")}";

    public AsyncRelayCommand InitializeCommand { get; }
    public AsyncRelayCommand BrowsePackageCommand { get; }
    public AsyncRelayCommand InstallPackageCommand { get; }
    public AsyncRelayCommand RefreshCommand { get; }
    public AsyncRelayCommand ToggleEnabledCommand { get; }
    public AsyncRelayCommand HealthCheckCommand { get; }
    public AsyncRelayCommand ExecuteCommand { get; }
    public AsyncRelayCommand RollbackCommand { get; }
    public AsyncRelayCommand UninstallCommand { get; }
    public RelayCommand LeaveSafeModeCommand { get; }

    public event PropertyChangedEventHandler? PropertyChanged;

    private async Task BrowsePackageAsync()
    {
        var path = _dialogs.SelectPackage();
        if (string.IsNullOrWhiteSpace(path))
        {
            return;
        }

        BeginOperation("正在检查本地插件包结构、摘要和开发者签名…");
        try
        {
            SelectedPackage = await _installer.InspectAsync(path);
            SelectedPackagePath = path;
            var permission = EvaluateSelectedPackage();
            Status = permission.DeniedRequired.Count == 0
                ? "插件包检查通过。此本地插件未经平台审核。"
                : $"插件包签名有效，但本地策略拒绝必需权限：{string.Join("、", permission.DeniedRequired)}。";
        }
        catch (Exception exception)
        {
            SelectedPackage = null;
            SelectedPackagePath = path;
            Status = UserMessage("插件包检查失败", exception);
        }
        finally
        {
            EndOperation();
        }
    }

    private async Task InstallPackageAsync()
    {
        if (SelectedPackage is null)
        {
            return;
        }

        var permission = EvaluateSelectedPackage();
        if (permission.DeniedRequired.Count > 0)
        {
            Status = $"无法安装：必需权限被拒绝：{string.Join("、", permission.DeniedRequired)}。";
            return;
        }

        if (!_dialogs.ConfirmInstall(SelectedPackage, permission))
        {
            Status = "已取消安装本地插件。";
            return;
        }

        BeginOperation("正在原子安装并执行隔离健康检查…");
        try
        {
            var result = await _installer.InstallLocalAsync(
                SelectedPackage.PackagePath,
                permission.Granted);
            await RefreshInstalledAsync(result.Plugin.PluginId);
            Status = $"已安装 {result.Plugin.DisplayName} {result.Plugin.CurrentVersion}，状态：未审核。";
        }
        catch (Exception exception)
        {
            Status = UserMessage("插件安装失败", exception);
        }
        finally
        {
            EndOperation();
        }
    }

    private async Task RefreshAsync()
    {
        BeginOperation("正在读取本地插件注册表…");
        try
        {
            await RefreshInstalledAsync(SelectedInstalledPlugin?.PluginId);
            Status = $"已加载 {InstalledPlugins.Count} 个本地插件。";
        }
        catch (Exception exception)
        {
            Status = UserMessage("读取插件注册表失败", exception);
        }
        finally
        {
            EndOperation();
        }
    }

    private async Task ToggleEnabledAsync()
    {
        if (SelectedInstalledPlugin is null)
        {
            return;
        }

        var pluginId = SelectedInstalledPlugin.PluginId;
        var enable = !SelectedInstalledPlugin.Enabled;
        BeginOperation(enable ? "正在启用插件…" : "正在停用插件…");
        try
        {
            await _runtime.SetEnabledAsync(pluginId, enable);
            await RefreshInstalledAsync(pluginId);
            Status = enable ? "插件已启用，仍为未审核。" : "插件已停用。";
        }
        catch (Exception exception)
        {
            Status = UserMessage("更新插件状态失败", exception);
        }
        finally
        {
            EndOperation();
        }
    }

    private async Task HealthCheckAsync()
    {
        if (SelectedInstalledPlugin is null)
        {
            return;
        }

        var pluginId = SelectedInstalledPlugin.PluginId;
        BeginOperation("正在 AppContainer 中执行插件健康检查…");
        try
        {
            await _runtime.CheckHealthAsync(pluginId);
            await RefreshInstalledAsync(pluginId);
            Status = "插件健康检查通过，状态仍为未审核。";
        }
        catch (Exception exception)
        {
            await RefreshInstalledAsync(pluginId);
            Status = UserMessage("插件健康检查失败", exception);
        }
        finally
        {
            EndOperation();
        }
    }

    private async Task ExecuteSelectedCommandAsync()
    {
        if (SelectedInstalledPlugin is null || SelectedCommand is null || CommandForm is null)
        {
            return;
        }

        var pluginId = SelectedInstalledPlugin.PluginId;
        BeginOperation($"正在执行 {SelectedCommand.Title}…");
        try
        {
            var input = CommandForm.BuildInput();
            var result = await _runtime.ExecuteAsync(pluginId, SelectedCommand.Id, input);
            CommandResult = JsonSerializer.Serialize(result, ResultJsonOptions);
            await RefreshInstalledAsync(pluginId);
            Status = "插件命令执行完成。插件状态：未审核。";
        }
        catch (Exception exception)
        {
            await RefreshInstalledAsync(pluginId);
            Status = UserMessage("插件命令执行失败", exception);
        }
        finally
        {
            EndOperation();
        }
    }

    private async Task RollbackAsync()
    {
        if (SelectedInstalledPlugin is null)
        {
            return;
        }

        var pluginId = SelectedInstalledPlugin.PluginId;
        BeginOperation("正在验证并回退插件版本…");
        try
        {
            var plugin = await _installer.RollbackAsync(pluginId);
            await RefreshInstalledAsync(pluginId);
            Status = $"已回退到 {plugin.CurrentVersion}，状态仍为未审核。";
        }
        catch (Exception exception)
        {
            Status = UserMessage("插件回退失败", exception);
        }
        finally
        {
            EndOperation();
        }
    }

    private async Task UninstallAsync()
    {
        if (SelectedInstalledPlugin is null
            || !_dialogs.ConfirmUninstall(SelectedInstalledPlugin))
        {
            return;
        }

        var pluginId = SelectedInstalledPlugin.PluginId;
        BeginOperation("正在卸载插件及其私有数据…");
        try
        {
            await _installer.UninstallAsync(pluginId);
            await RefreshInstalledAsync(null);
            Status = "插件已卸载。";
        }
        catch (Exception exception)
        {
            Status = UserMessage("插件卸载失败", exception);
        }
        finally
        {
            EndOperation();
        }
    }

    private void LeaveSafeMode()
    {
        _safeMode.LeaveSafeModeForCurrentSession();
        OnPropertyChanged(nameof(IsSafeMode));
        OnPropertyChanged(nameof(SafeModeStatus));
        Status = "已退出本次会话的插件安全模式，插件不会自动启动。";
        NotifyCommands();
    }

    private async Task RefreshInstalledAsync(string? selectedPluginId)
    {
        var plugins = await _registry.GetAllAsync();
        InstalledPlugins.Clear();
        foreach (var plugin in plugins)
        {
            InstalledPlugins.Add(plugin);
        }

        SelectedInstalledPlugin = selectedPluginId is null
            ? null
            : InstalledPlugins.SingleOrDefault(plugin => plugin.PluginId == selectedPluginId);
    }

    private void LoadCommands()
    {
        AvailableCommands.Clear();
        CommandForm = null;
        _selectedCommand = null;
        OnPropertyChanged(nameof(SelectedCommand));
        if (SelectedInstalledPlugin is null
            || !SelectedInstalledPlugin.Versions.TryGetValue(
                SelectedInstalledPlugin.CurrentVersion,
                out var version))
        {
            return;
        }

        foreach (var command in version.Manifest.Commands)
        {
            AvailableCommands.Add(command);
        }

        SelectedCommand = AvailableCommands.FirstOrDefault();
    }

    private void LoadCommandForm()
    {
        CommandForm = null;
        if (SelectedInstalledPlugin is null
            || SelectedCommand is null
            || !SelectedInstalledPlugin.Versions.TryGetValue(
                SelectedInstalledPlugin.CurrentVersion,
                out var version))
        {
            return;
        }

        try
        {
            var installedDirectory = _paths.InstalledVersionDirectory(
                SelectedInstalledPlugin.PluginId,
                version.Version);
            var schemaPath = ResolveContainedPath(installedDirectory, SelectedCommand.InputSchema);
            CommandForm = PluginCommandForm.Load(schemaPath, _dialogs.SelectPath);
        }
        catch (Exception exception)
        {
            Status = UserMessage("加载插件命令表单失败", exception);
        }
    }

    private PluginPermissionDecision EvaluateSelectedPackage()
    {
        var manifest = SelectedPackage?.Manifest
            ?? throw new InvalidOperationException("尚未选择插件包。");
        var grantedByUserConfirmation = manifest.Capabilities.Required
            .Concat(manifest.Capabilities.Optional)
            .Where(PluginPermissionPolicy.LocallySupportedCapabilities.Contains);
        return _permissionPolicy.Evaluate(manifest, grantedByUserConfirmation);
    }

    private bool CanRunSelectedPlugin() =>
        !IsBusy
        && !_safeMode.IsActive
        && SelectedInstalledPlugin?.Enabled == true;

    private bool CanExecuteSelectedCommand() =>
        CanRunSelectedPlugin() && SelectedCommand is not null && CommandForm is not null;

    private void BeginOperation(string status)
    {
        IsBusy = true;
        Status = status;
    }

    private void EndOperation() => IsBusy = false;

    private void NotifyCommands()
    {
        InitializeCommand.NotifyCanExecuteChanged();
        BrowsePackageCommand.NotifyCanExecuteChanged();
        InstallPackageCommand.NotifyCanExecuteChanged();
        RefreshCommand.NotifyCanExecuteChanged();
        ToggleEnabledCommand.NotifyCanExecuteChanged();
        HealthCheckCommand.NotifyCanExecuteChanged();
        ExecuteCommand.NotifyCanExecuteChanged();
        RollbackCommand.NotifyCanExecuteChanged();
        UninstallCommand.NotifyCanExecuteChanged();
        LeaveSafeModeCommand.NotifyCanExecuteChanged();
    }

    private static string ResolveContainedPath(string root, string relativePath)
    {
        var normalized = PluginPackageVerifier.NormalizeManifestPath(relativePath, "命令输入 Schema");
        var fullRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar)
            + Path.DirectorySeparatorChar;
        var fullPath = Path.GetFullPath(Path.Combine(root, normalized.Replace('/', Path.DirectorySeparatorChar)));
        if (!fullPath.StartsWith(fullRoot, StringComparison.OrdinalIgnoreCase))
        {
            throw new PluginPackageException("命令输入 Schema 逃逸安装目录。");
        }

        return fullPath;
    }

    private static string FormatCapabilities(IReadOnlyList<string>? capabilities) =>
        capabilities is null || capabilities.Count == 0
            ? "无"
            : string.Join("、", capabilities);

    private static string UserMessage(string prefix, Exception exception) => exception switch
    {
        PluginPackageException or PluginInstallException or PluginRegistryException
            or InvalidOperationException => $"{prefix}：{exception.Message}",
        _ => $"{prefix}，请查看本地插件日志。",
    };

    private bool SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
        {
            return false;
        }

        field = value;
        OnPropertyChanged(propertyName);
        return true;
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
}
