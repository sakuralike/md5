using System.Collections.ObjectModel;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.CompilerServices;
using System.Text.Json;
using PasswordDetective.Desktop.Infrastructure;
using PasswordDetective.Desktop.Plugins.Installation;
using PasswordDetective.Desktop.Plugins.Market;
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
    private readonly PluginLogStore _logs;
    private readonly IPluginDialogService _dialogs;
    private readonly PasswordDetective.Desktop.Services.DesktopApiClient _marketApi;
    private readonly PluginRevocationCache _revocationCache;
    private readonly string _serverBaseUrl;
    private PluginPackageInspection? _selectedPackage;
    private InstalledPlugin? _selectedInstalledPlugin;
    private PluginCommandManifest? _selectedCommand;
    private PluginCommandForm? _commandForm;
    private string _selectedPackagePath = string.Empty;
    private string _status = "请选择本地 .pdpkg 插件包。";
    private string _commandResult = "尚未执行插件命令。";
    private bool _isBusy;
    private MarketPluginCatalogItem? _selectedMarketPlugin;
    private MarketPluginDetail? _selectedMarketDetail;
    private string _marketQuery = string.Empty;
    private readonly HashSet<string> _revokedMarketVersions = new(StringComparer.Ordinal);
    private readonly HashSet<string> _revokedMarketPlugins = new(StringComparer.Ordinal);
    private readonly HashSet<string> _revokedMarketSigningKeys = new(StringComparer.Ordinal);
    private PluginRevocationCacheSnapshot? _revocationSnapshot;
    private bool _offlineMarketBlocked;

    private static readonly TimeSpan RevocationRefreshInterval = TimeSpan.FromHours(6);
    private static readonly TimeSpan RevocationCacheTtl = TimeSpan.FromDays(7);

    public PluginMarketplaceViewModel(
        PluginStoragePaths paths,
        PluginInstaller installer,
        PluginPermissionPolicy permissionPolicy,
        PluginRegistry registry,
        PluginRuntimeService runtime,
        PluginSafeMode safeMode,
        IPluginDialogService dialogs,
        string? serverBaseUrl = null,
        PluginLogStore? logs = null)
    {
        _paths = paths;
        _installer = installer;
        _permissionPolicy = permissionPolicy;
        _registry = registry;
        _runtime = runtime;
        _safeMode = safeMode;
        _logs = logs ?? new PluginLogStore(paths);
        _dialogs = dialogs;
        _marketApi = new PasswordDetective.Desktop.Services.DesktopApiClient();
        _revocationCache = new PluginRevocationCache(paths);
        _serverBaseUrl = serverBaseUrl ?? string.Empty;
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
        LoadMarketCommand = new AsyncRelayCommand(LoadMarketAsync, () => !IsBusy && !string.IsNullOrWhiteSpace(_serverBaseUrl));
        LoadMarketDetailCommand = new AsyncRelayCommand(LoadMarketDetailAsync, () => !IsBusy && SelectedMarketPlugin is not null);
        InstallMarketCommand = new AsyncRelayCommand(InstallMarketAsync, () => !IsBusy && SelectedMarketDetail is not null);
    }

    public ObservableCollection<InstalledPlugin> InstalledPlugins { get; } = [];
    public ObservableCollection<PluginCommandManifest> AvailableCommands { get; } = [];
    public ObservableCollection<MarketPluginCatalogItem> MarketPlugins { get; } = [];

    public MarketPluginCatalogItem? SelectedMarketPlugin
    {
        get => _selectedMarketPlugin;
        set
        {
            if (SetField(ref _selectedMarketPlugin, value))
            {
                SelectedMarketDetail = null;
                NotifyCommands();
            }
        }
    }

    public MarketPluginDetail? SelectedMarketDetail
    {
        get => _selectedMarketDetail;
        private set => SetField(ref _selectedMarketDetail, value);
    }

    public string MarketQuery
    {
        get => _marketQuery;
        set => SetField(ref _marketQuery, value);
    }

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
    public string MarketOfflineStatus => _offlineMarketBlocked
        ? "撤销列表缓存已过期；高风险平台插件已停用，其他平台插件处于离线风险状态。"
        : "平台撤销列表缓存有效。";
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
    public AsyncRelayCommand LoadMarketCommand { get; }
    public AsyncRelayCommand LoadMarketDetailCommand { get; }
    public AsyncRelayCommand InstallMarketCommand { get; }
    public AsyncRelayCommand ToggleEnabledCommand { get; }
    public AsyncRelayCommand HealthCheckCommand { get; }
    public AsyncRelayCommand ExecuteCommand { get; }
    public AsyncRelayCommand RollbackCommand { get; }
    public AsyncRelayCommand UninstallCommand { get; }
    public RelayCommand LeaveSafeModeCommand { get; }

    public event PropertyChangedEventHandler? PropertyChanged;

    private async Task LoadMarketAsync()
    {
        BeginOperation("正在验证平台撤销列表并读取在线插件市场…");
        try
        {
            var revocations = await _marketApi.GetPluginRevocationsAsync(_serverBaseUrl);
            foreach (var revocation in revocations.Items)
            {
                PlatformSignatureVerifier.Verify(revocation);
            }
            await _revocationCache.SaveAsync(revocations, RevocationCacheTtl);
            _revocationSnapshot = await _revocationCache.LoadAsync();
            PopulateRevocationSets(revocations.Items);
            await ApplyRevocationPolicyAsync(_revocationSnapshot);

            var catalog = await _marketApi.GetPluginCatalogAsync(_serverBaseUrl, MarketQuery);
            MarketPlugins.Clear();
            foreach (var item in catalog.Items)
            {
                MarketPlugins.Add(item);
            }
            SelectedMarketPlugin = MarketPlugins.FirstOrDefault();
            Status = $"在线市场已加载 {MarketPlugins.Count} 个平台审核插件。";
        }
        catch (Exception exception)
        {
            _revocationSnapshot = await _revocationCache.LoadAsync();
            if (_revocationSnapshot is not null)
            {
                PopulateRevocationSets(_revocationSnapshot.Items);
            }
            await ApplyRevocationPolicyAsync(_revocationSnapshot);
            Status = UserMessage("读取在线插件市场失败", exception);
        }
        finally
        {
            EndOperation();
        }
    }

    private async Task LoadMarketDetailAsync()
    {
        if (SelectedMarketPlugin is null)
        {
            return;
        }

        BeginOperation("正在验证插件详情与平台签章…");
        try
        {
            var detail = await _marketApi.GetPluginDetailAsync(_serverBaseUrl, SelectedMarketPlugin.Slug);
            var version = detail.Versions.FirstOrDefault();
            if (version is null)
            {
                throw new InvalidOperationException("在线插件没有可安装版本。");
            }
            if (_revokedMarketPlugins.Contains(detail.Slug)
                || _revokedMarketVersions.Contains($"{detail.Slug}@{version.Semver}")
                || _revokedMarketSigningKeys.Contains(version.SigningKeyFingerprint))
            {
                throw new PluginPackageException("该平台插件版本已撤销，不能安装。");
            }
            PlatformSignatureVerifier.Verify(version);
            SelectedMarketDetail = detail;
            Status = $"已验证 {detail.Name} {version.Semver} 的平台签章。";
        }
        catch (Exception exception)
        {
            SelectedMarketDetail = null;
            Status = UserMessage("读取在线插件详情失败", exception);
        }
        finally
        {
            EndOperation();
        }
    }

    private async Task InstallMarketAsync()
    {
        var detail = SelectedMarketDetail;
        var version = detail?.Versions.FirstOrDefault();
        if (detail is null || version is null)
        {
            return;
        }

        var temporaryPath = Path.Combine(
            _paths.StagingDirectory,
            $"market-{detail.Slug}-{version.Semver}-{Guid.NewGuid():N}.pdpkg");
        var failureStage = "preflight";
        var architecture = "windows-x64";
        BeginOperation("正在下载、验签并隔离安装平台插件…");
        try
        {
            if (_revocationSnapshot is null || _revocationSnapshot.IsExpired(DateTimeOffset.UtcNow))
            {
                throw new PluginPackageException("平台撤销列表缓存已过期，请联网刷新后再安装。");
            }

            var existingMarket = await _registry.GetAsync(detail.Slug);
            var marketEventKind = existingMarket is not null
                && !string.Equals(existingMarket.CurrentVersion, version.Semver, StringComparison.Ordinal)
                ? "upgraded"
                : "installed";
            PlatformSignatureVerifier.Verify(version);
            if (_revokedMarketPlugins.Contains(detail.Slug)
                || _revokedMarketVersions.Contains($"{detail.Slug}@{version.Semver}")
                || _revokedMarketSigningKeys.Contains(version.SigningKeyFingerprint))
            {
                throw new PluginPackageException("该平台插件版本已撤销，不能安装。");
            }
            var artifact = version.Artifacts.FirstOrDefault(item => item.Architecture == architecture)
                ?? throw new InvalidOperationException("在线插件不包含当前架构制品。");
            architecture = artifact.Architecture;
            failureStage = "download_ticket";
            var ticket = await _marketApi.IssuePluginDownloadTicketAsync(
                _serverBaseUrl,
                detail.Slug,
                version.Semver,
                architecture);
            _paths.EnsureDirectories();
            failureStage = "artifact_download";
            await _marketApi.DownloadPluginArtifactAsync(
                ticket.DownloadUrl,
                temporaryPath,
                ticket.ArtifactSha256,
                ticket.ArtifactSizeBytes);
            failureStage = "package_inspection";
            var inspection = await _installer.InspectAsync(temporaryPath);
            var permission = _permissionPolicy.EvaluateMarket(
                inspection.Manifest,
                inspection.Manifest.Capabilities.Required
                    .Concat(inspection.Manifest.Capabilities.Optional)
                    .Where(PluginPermissionPolicy.MarketSupportedCapabilities.Contains));
            if (permission.DeniedRequired.Count > 0)
            {
                throw new PluginInstallException(
                    $"平台插件必需权限不受本机策略支持：{string.Join("、", permission.DeniedRequired)}。");
            }
            var existingVersion = existingMarket?.Versions.TryGetValue(
                existingMarket.CurrentVersion,
                out var installedVersion) == true
                ? installedVersion
                : null;
            var previousCapabilities = existingVersion is null
                ? []
                : existingVersion.Manifest.Capabilities.Required
                    .Concat(existingVersion.Manifest.Capabilities.Optional)
                    .ToArray();
            var addedCapabilities = inspection.Manifest.Capabilities.Required
                .Concat(inspection.Manifest.Capabilities.Optional)
                .Except(previousCapabilities, StringComparer.Ordinal)
                .ToArray();
            var signingKeyChanged = existingVersion is not null
                && !string.Equals(
                    existingMarket?.PublisherKeyFingerprint,
                    inspection.PublisherKeyFingerprint,
                    StringComparison.OrdinalIgnoreCase);
            var majorVersionChanged = existingVersion is not null
                && int.TryParse(existingVersion.Version.Split('.')[0], out var oldMajor)
                && int.TryParse(version.Semver.Split('.')[0], out var newMajor)
                && oldMajor != newMajor;
            if (!_dialogs.ConfirmMarketInstall(
                    detail,
                    version,
                    permission,
                    addedCapabilities,
                    signingKeyChanged,
                    majorVersionChanged))
            {
                Status = "已取消安装平台插件。";
                return;
            }
            failureStage = "package_install";
            var result = await _installer.InstallMarketAsync(
                temporaryPath,
                version,
                permission.Granted);
            await RefreshInstalledAsync(result.Plugin.PluginId);
            try
            {
                await RecordInstallEventBestEffortAsync(
                    detail.Slug,
                    version.Semver,
                    artifact.Architecture,
                    marketEventKind,
                    "success",
                    PluginSource.MarketReviewed);
            }
            catch
            {
                // 安装事件是隐私最小化遥测，失败不能回滚已验证的本地安装。
            }
            Status = $"已安装平台审核插件 {result.Plugin.DisplayName} {result.Plugin.CurrentVersion}。";
        }
        catch (Exception exception)
        {
            try
            {
                var errorCode = exception is PasswordDetective.Desktop.Services.DesktopApiException apiException
                    ? $"{apiException.Code}/{apiException.StatusCode}"
                    : $"{exception.GetType().Name}/{exception.HResult}";
                await _logs.AppendAsync(
                    detail.Slug,
                    "error",
                    $"market_install_failed version={version.Semver} stage={failureStage} "
                    + $"code={errorCode} message={exception.Message}");
            }
            catch (Exception)
            {
            }
            await RecordInstallEventBestEffortAsync(
                detail.Slug,
                version.Semver,
                architecture,
                "download_failed",
                "failure",
                PluginSource.MarketReviewed);
            Status = UserMessage("平台插件安装失败", exception);
        }
        finally
        {
            TryDeleteFile(temporaryPath);
            EndOperation();
        }
    }

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
            await RecordInstallEventBestEffortAsync(
                result.Plugin.PluginId,
                result.Plugin.CurrentVersion,
                result.Inspection.Architecture,
                "installed",
                "success",
                PluginSource.LocalUnreviewed);
            Status = $"已安装 {result.Plugin.DisplayName} {result.Plugin.CurrentVersion}，状态：未审核。";
        }
        catch (Exception exception)
        {
            await RecordInstallEventBestEffortAsync(
                SelectedPackage.Manifest.PluginId,
                SelectedPackage.Manifest.Version,
                SelectedPackage.Architecture,
                "download_failed",
                "failure",
                PluginSource.LocalUnreviewed);
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
            _revocationSnapshot = await _revocationCache.LoadAsync();
            if (_revocationSnapshot is not null)
            {
                PopulateRevocationSets(_revocationSnapshot.Items);
            }
            if (!string.IsNullOrWhiteSpace(_serverBaseUrl)
                && (_revocationSnapshot is null
                    || _revocationSnapshot.FetchedAt + RevocationRefreshInterval <= DateTimeOffset.UtcNow))
            {
                try
                {
                    var revocations = await _marketApi.GetPluginRevocationsAsync(_serverBaseUrl);
                    foreach (var revocation in revocations.Items)
                    {
                        PlatformSignatureVerifier.Verify(revocation);
                    }
                    await _revocationCache.SaveAsync(revocations, RevocationCacheTtl);
                    _revocationSnapshot = await _revocationCache.LoadAsync();
                    PopulateRevocationSets(revocations.Items);
                }
                catch
                {
                    // A cached signed list remains usable until its maximum stale time.
                }
            }
            await ApplyRevocationPolicyAsync(_revocationSnapshot);
            await RefreshInstalledAsync(SelectedInstalledPlugin?.PluginId);
            Status = $"已加载 {InstalledPlugins.Count} 个本地插件。{MarketOfflineStatus}";
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
        var pluginVersion = SelectedInstalledPlugin.CurrentVersion;
        var pluginSource = SelectedInstalledPlugin.Source;
        if (enable && !await IsMarketPluginRunnableAsync(SelectedInstalledPlugin))
        {
            Status = "平台插件因撤销或离线安全策略不能启用。";
            return;
        }
        BeginOperation(enable ? "正在启用插件…" : "正在停用插件…");
        try
        {
            await _runtime.SetEnabledAsync(pluginId, enable);
            await RefreshInstalledAsync(pluginId);
            await RecordInstallEventBestEffortAsync(
                pluginId,
                pluginVersion,
                "windows-x64",
                enable ? "enabled" : "disabled",
                "success",
                pluginSource);
            Status = enable ? "插件已启用，仍为未审核。" : "插件已停用。";
        }
        catch (Exception exception)
        {
            await RecordInstallEventBestEffortAsync(
                pluginId,
                pluginVersion,
                "windows-x64",
                enable ? "enabled" : "disabled",
                "failure",
                pluginSource);
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
        if (!await IsMarketPluginRunnableAsync(SelectedInstalledPlugin))
        {
            Status = "平台插件因撤销或离线安全策略不能运行。";
            return;
        }
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
        if (!await IsMarketPluginRunnableAsync(SelectedInstalledPlugin))
        {
            Status = "平台插件因撤销或离线安全策略不能运行。";
            return;
        }
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
            await RecordInstallEventBestEffortAsync(
                pluginId,
                plugin.CurrentVersion,
                GetInstalledArchitecture(plugin),
                "rolled_back",
                "success",
                plugin.Source);
            Status = $"已回退到 {plugin.CurrentVersion}，状态仍为未审核。";
        }
        catch (Exception exception)
        {
            await RecordInstallEventBestEffortAsync(
                pluginId,
                SelectedInstalledPlugin?.CurrentVersion ?? "0.0.0",
                "windows-x64",
                "rolled_back",
                "failure",
                SelectedInstalledPlugin?.Source ?? PluginSource.LocalUnreviewed);
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
        var pluginVersion = SelectedInstalledPlugin.CurrentVersion;
        var pluginSource = SelectedInstalledPlugin.Source;
        var pluginArchitecture = GetInstalledArchitecture(SelectedInstalledPlugin);
        BeginOperation("正在卸载插件及其私有数据…");
        try
        {
            await _installer.UninstallAsync(pluginId);
            await RefreshInstalledAsync(null);
            await RecordInstallEventBestEffortAsync(
                pluginId,
                pluginVersion,
                pluginArchitecture,
                "uninstalled",
                "success",
                pluginSource);
            Status = "插件已卸载。";
        }
        catch (Exception exception)
        {
            await RecordInstallEventBestEffortAsync(
                pluginId,
                pluginVersion,
                pluginArchitecture,
                "uninstalled",
                "failure",
                pluginSource);
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

    private async Task RecordInstallEventBestEffortAsync(
        string pluginSlug,
        string semver,
        string architecture,
        string kind,
        string result,
        string source)
    {
        if (string.IsNullOrWhiteSpace(_serverBaseUrl))
        {
            return;
        }

        try
        {
            await _marketApi.RecordPluginInstallEventAsync(
                _serverBaseUrl,
                new PasswordDetective.Desktop.Services.PluginInstallEventRequest(
                    Guid.NewGuid().ToString("N"),
                    pluginSlug,
                    semver,
                    architecture,
                    source,
                    kind,
                    result,
                    PluginPackageVerifier.HostVersion));
        }
        catch
        {
            // Telemetry failure must not change a verified local state transition.
        }
    }

    private static string GetInstalledArchitecture(InstalledPlugin plugin)
    {
        if (!plugin.Versions.TryGetValue(plugin.CurrentVersion, out var version))
        {
            return "windows-x64";
        }

        return RuntimeInformation.ProcessArchitecture == Architecture.Arm64
            && version.Manifest.Runtime.Entrypoints.ContainsKey("windows-arm64")
            ? "windows-arm64"
            : "windows-x64";
    }

    private void PopulateRevocationSets(IEnumerable<MarketPluginRevocation> revocations)
    {
        _revokedMarketVersions.Clear();
        _revokedMarketPlugins.Clear();
        _revokedMarketSigningKeys.Clear();
        var now = DateTimeOffset.UtcNow;
        foreach (var revocation in revocations.Where(item => item.EffectiveAt <= now))
        {
            if (revocation.Scope == "plugin" && revocation.PluginSlug is not null)
            {
                _revokedMarketPlugins.Add(revocation.PluginSlug);
            }
            else if (revocation.Scope == "signing_key" && revocation.SigningKeyFingerprint is not null)
            {
                _revokedMarketSigningKeys.Add(revocation.SigningKeyFingerprint);
            }
            else if (revocation.Scope == "version"
                && revocation.PluginSlug is not null
                && revocation.Semver is not null)
            {
                _revokedMarketVersions.Add($"{revocation.PluginSlug}@{revocation.Semver}");
            }
        }
    }

    private async Task ApplyRevocationPolicyAsync(PluginRevocationCacheSnapshot? snapshot)
    {
        var now = DateTimeOffset.UtcNow;
        _offlineMarketBlocked = snapshot is null || snapshot.IsExpired(now);
        var installed = await _registry.GetAllAsync();
        foreach (var plugin in installed.Where(item => item.Source == PluginSource.MarketReviewed))
        {
            var explicitlyRevoked = snapshot?.Revokes(plugin, now) == true;
            var highRiskStale = snapshot?.IsExpired(now) == true
                && plugin.RiskTier is "high" or "critical";
            if (snapshot is not null && !explicitlyRevoked && !highRiskStale)
            {
                continue;
            }
            var blockedMessage = snapshot is null
                ? "撤销列表缓存缺失，平台插件已停用。"
                : highRiskStale
                ? "撤销列表缓存超过最大离线时长，高风险平台插件已停用。"
                : "平台撤销列表已标记当前插件版本，插件已停用。";
            if (!plugin.Enabled && plugin.RuntimeStatus == "disabled"
                && plugin.LastError == blockedMessage)
            {
                continue;
            }

            await _registry.UpdateAsync(
                plugin.PluginId,
                current => current with
                {
                    Enabled = false,
                    RuntimeStatus = "disabled",
                    LastError = blockedMessage,
                    UpdatedAt = DateTimeOffset.UtcNow,
                });
        }
        OnPropertyChanged(nameof(MarketOfflineStatus));
    }

    private async Task<bool> IsMarketPluginRunnableAsync(InstalledPlugin plugin)
    {
        if (plugin.Source != PluginSource.MarketReviewed)
        {
            return true;
        }

        var snapshot = await _revocationCache.LoadAsync();
        if (snapshot is null)
        {
            return false;
        }

        var now = DateTimeOffset.UtcNow;
        return !snapshot.Revokes(plugin, now)
            && (!snapshot.IsExpired(now) || plugin.RiskTier is not ("high" or "critical"));
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
        LoadMarketCommand.NotifyCanExecuteChanged();
        LoadMarketDetailCommand.NotifyCanExecuteChanged();
        InstallMarketCommand.NotifyCanExecuteChanged();
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

    private static void TryDeleteFile(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch (IOException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
    }

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
