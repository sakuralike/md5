using System.Collections.ObjectModel;
using System.ComponentModel;
using System.IO;
using System.Net.Http;
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
    private readonly Func<CancellationToken, Task<string?>>? _accessTokenProvider;
    private readonly PasswordDetective.Desktop.Services.IInstallationIdentityService? _identityService;
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
    private PluginUpdateCandidate? _selectedPluginUpdate;
    private string _marketQuery = string.Empty;
    private string _pluginUpdateSummary = "尚未检查插件更新。";
    private readonly HashSet<string> _revokedMarketVersions = new(StringComparer.Ordinal);
    private readonly HashSet<string> _revokedMarketPlugins = new(StringComparer.Ordinal);
    private readonly HashSet<string> _revokedMarketSigningKeys = new(StringComparer.Ordinal);
    private PluginRevocationCacheSnapshot? _revocationSnapshot;
    private bool _offlineMarketBlocked;
    private bool _isCanaryMode;

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
        PluginLogStore? logs = null,
        PasswordDetective.Desktop.Services.DesktopApiClient? marketApi = null,
        Func<CancellationToken, Task<string?>>? accessTokenProvider = null,
        PasswordDetective.Desktop.Services.IInstallationIdentityService? identityService = null)
    {
        _paths = paths;
        _installer = installer;
        _permissionPolicy = permissionPolicy;
        _registry = registry;
        _runtime = runtime;
        _safeMode = safeMode;
        _logs = logs ?? new PluginLogStore(paths);
        _dialogs = dialogs;
        _marketApi = marketApi ?? new PasswordDetective.Desktop.Services.DesktopApiClient();
        _revocationCache = new PluginRevocationCache(paths);
        _serverBaseUrl = serverBaseUrl ?? string.Empty;
        _accessTokenProvider = accessTokenProvider;
        _identityService = identityService;
        InitializeCommand = new AsyncRelayCommand(InitializeAsync, () => !IsBusy);
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
        LoadCanaryMarketCommand = new AsyncRelayCommand(
            LoadCanaryMarketAsync,
            () => !IsBusy && !string.IsNullOrWhiteSpace(_serverBaseUrl));
        LoadMarketDetailCommand = new AsyncRelayCommand(LoadMarketDetailAsync, () => !IsBusy && SelectedMarketPlugin is not null);
        InstallMarketCommand = new AsyncRelayCommand(InstallMarketAsync, () => !IsBusy && SelectedMarketDetail is not null);
        CheckPluginUpdatesCommand = new AsyncRelayCommand(
            CheckPluginUpdatesAsync,
            () => !IsBusy && !string.IsNullOrWhiteSpace(_serverBaseUrl));
        UpgradeSelectedPluginCommand = new AsyncRelayCommand(
            UpgradeSelectedPluginAsync,
            () => !IsBusy && SelectedPluginUpdate is not null);
    }

    public ObservableCollection<InstalledPlugin> InstalledPlugins { get; } = [];
    public ObservableCollection<PluginCommandManifest> AvailableCommands { get; } = [];
    public ObservableCollection<MarketPluginCatalogItem> MarketPlugins { get; } = [];
    public ObservableCollection<PluginUpdateCandidate> PluginUpdates { get; } = [];

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

    public PluginUpdateCandidate? SelectedPluginUpdate
    {
        get => _selectedPluginUpdate;
        set
        {
            if (SetField(ref _selectedPluginUpdate, value))
            {
                NotifyCommands();
            }
        }
    }

    public string MarketQuery
    {
        get => _marketQuery;
        set => SetField(ref _marketQuery, value);
    }

    public string PluginUpdateSummary
    {
        get => _pluginUpdateSummary;
        private set => SetField(ref _pluginUpdateSummary, value);
    }

    public bool IsCanaryMode
    {
        get => _isCanaryMode;
        private set
        {
            if (SetField(ref _isCanaryMode, value))
            {
                OnPropertyChanged(nameof(MarketChannelLabel));
            }
        }
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
    public string MarketChannelLabel => IsCanaryMode
        ? "内部 Canary 通道（管理员账号）"
        : "公开 stable 通道";

    public AsyncRelayCommand InitializeCommand { get; }
    public AsyncRelayCommand BrowsePackageCommand { get; }
    public AsyncRelayCommand InstallPackageCommand { get; }
    public AsyncRelayCommand RefreshCommand { get; }
    public AsyncRelayCommand LoadMarketCommand { get; }
    public AsyncRelayCommand LoadCanaryMarketCommand { get; }
    public AsyncRelayCommand LoadMarketDetailCommand { get; }
    public AsyncRelayCommand InstallMarketCommand { get; }
    public AsyncRelayCommand CheckPluginUpdatesCommand { get; }
    public AsyncRelayCommand UpgradeSelectedPluginCommand { get; }
    public AsyncRelayCommand ToggleEnabledCommand { get; }
    public AsyncRelayCommand HealthCheckCommand { get; }
    public AsyncRelayCommand ExecuteCommand { get; }
    public AsyncRelayCommand RollbackCommand { get; }
    public AsyncRelayCommand UninstallCommand { get; }
    public RelayCommand LeaveSafeModeCommand { get; }

    public event PropertyChangedEventHandler? PropertyChanged;

    private async Task InitializeAsync()
    {
        await RefreshAsync();
        if (!string.IsNullOrWhiteSpace(_serverBaseUrl))
        {
            await CheckPluginUpdatesAsync();
        }
    }

    internal async Task CheckPluginUpdatesAsync()
    {
        if (string.IsNullOrWhiteSpace(_serverBaseUrl))
        {
            PluginUpdateSummary = "未配置插件市场地址。";
            return;
        }

        BeginOperation("正在检查已安装插件的 stable 更新…");
        try
        {
            const int pageSize = 100;
            var page = 1;
            var catalogItems = new List<MarketPluginCatalogItem>();
            MarketPluginCatalogResponse catalog;
            do
            {
                catalog = await _marketApi.GetPluginCatalogAsync(
                    _serverBaseUrl,
                    page: page,
                    pageSize: pageSize);
                catalogItems.AddRange(catalog.Items);
                page++;
            } while (catalogItems.Count < catalog.Total && catalog.Items.Count > 0);

            var installed = await _registry.GetAllAsync();
            var updates = FindPluginUpdates(
                installed,
                catalogItems,
                _revokedMarketPlugins,
                _revokedMarketVersions).ToArray();
            var accessToken = await TryGetAccessTokenAsync();
            if (!string.IsNullOrWhiteSpace(accessToken) && _identityService is not null)
            {
                try
                {
                    var identity = await _identityService.GetOrCreateAsync();
                    var retries = await _marketApi.GetPluginMigrationRetriesAsync(
                        _serverBaseUrl,
                        accessToken,
                        identity.InstallationId);
                    var retryAttempts = retries.Items.ToDictionary(
                        item => $"{item.PluginSlug}@{item.Semver}",
                        item => item.Attempt,
                        StringComparer.Ordinal);
                    updates = updates.Select(update => retryAttempts.TryGetValue(
                            $"{update.PluginSlug}@{update.TargetVersion}",
                            out var attempt)
                        ? update with
                        {
                            State = "failed",
                            LastError = $"服务器已安排第 {attempt + 1} 次迁移重试。",
                        }
                        : update).ToArray();
                }
                catch
                {
                    // Retry scheduling is advisory; catalog updates remain usable when it is unavailable.
                }
            }
            PluginUpdates.Clear();
            foreach (var update in updates)
            {
                PluginUpdates.Add(update);
            }
            SelectedPluginUpdate = PluginUpdates.FirstOrDefault();
            UpdatePluginUpdateSummary();
            Status = PluginUpdates.Count == 0
                ? "已检查插件更新，当前没有可用的 stable 更新。"
                : $"已发现 {PluginUpdates.Count} 个插件更新，可选择后执行升级。";
        }
        catch (Exception exception)
        {
            PluginUpdateSummary = "插件更新检查失败。";
            Status = UserMessage("检查插件更新失败", exception);
        }
        finally
        {
            EndOperation();
        }
    }

    private async Task UpgradeSelectedPluginAsync()
    {
        var candidate = SelectedPluginUpdate;
        if (candidate is null)
        {
            return;
        }

        var installed = await _registry.GetAsync(candidate.PluginSlug);
        if (installed is null
            || !string.Equals(installed.CurrentVersion, candidate.CurrentVersion, StringComparison.Ordinal))
        {
            await CheckPluginUpdatesAsync();
            Status = "本地插件版本已变化，请重新选择升级项。";
            return;
        }

        SelectedMarketPlugin = candidate.CatalogItem;
        await LoadMarketDetailAsync();
        var target = SelectedMarketDetail is null
            ? null
            : PluginSemver.LatestOrDefault(SelectedMarketDetail.Versions);
        if (target is null
            || !string.Equals(target.Semver, candidate.TargetVersion, StringComparison.Ordinal))
        {
            MarkUpdateFailure(candidate, "市场版本已变化，请重新检查插件更新。");
            return;
        }

        await InstallMarketAsync();
        var updated = await _registry.GetAsync(candidate.PluginSlug);
        if (updated is not null
            && string.Equals(updated.CurrentVersion, candidate.TargetVersion, StringComparison.Ordinal))
        {
            PluginUpdates.Remove(candidate);
            SelectedPluginUpdate = PluginUpdates.FirstOrDefault();
            UpdatePluginUpdateSummary();
            Status = $"{candidate.Name} 已升级到 {candidate.TargetVersion}。";
        }
        else if (!Status.StartsWith("已取消", StringComparison.Ordinal))
        {
            MarkUpdateFailure(candidate, Status);
        }
    }

    internal static IReadOnlyList<PluginUpdateCandidate> FindPluginUpdates(
        IEnumerable<InstalledPlugin> installedPlugins,
        IEnumerable<MarketPluginCatalogItem> catalogItems,
        IReadOnlySet<string>? revokedPlugins = null,
        IReadOnlySet<string>? revokedVersions = null)
    {
        var catalog = catalogItems
            .GroupBy(item => item.Slug, StringComparer.Ordinal)
            .ToDictionary(
                group => group.Key,
                group => group.OrderByDescending(
                        item => PluginSemver.Parse(item.LatestVersion),
                        Comparer<(int Major, int Minor, int Patch)>.Create(PluginSemver.Compare))
                    .First(),
                StringComparer.Ordinal);
        return installedPlugins
            .Where(plugin => plugin.Source == PluginSource.MarketReviewed)
            .Where(plugin => catalog.ContainsKey(plugin.PluginId))
            .Select(plugin => new { Plugin = plugin, Catalog = catalog[plugin.PluginId] })
            .Where(item => revokedPlugins?.Contains(item.Plugin.PluginId) != true)
            .Where(item => revokedVersions?.Contains(
                $"{item.Plugin.PluginId}@{item.Catalog.LatestVersion}") != true)
            .Where(item => PluginSemver.Compare(
                PluginSemver.Parse(item.Catalog.LatestVersion),
                PluginSemver.Parse(item.Plugin.CurrentVersion)) > 0)
            .Select(item => new PluginUpdateCandidate(item.Catalog, item.Plugin.CurrentVersion))
            .OrderBy(item => item.Name, StringComparer.CurrentCulture)
            .ToArray();
    }

    private void MarkUpdateFailure(PluginUpdateCandidate candidate, string message)
    {
        var index = PluginUpdates.IndexOf(candidate);
        if (index < 0)
        {
            return;
        }
        var failed = candidate with { State = "failed", LastError = message };
        PluginUpdates[index] = failed;
        SelectedPluginUpdate = failed;
        PluginUpdateSummary = $"有 {PluginUpdates.Count} 个可用更新，其中升级失败项可重试。";
        Status = message;
    }

    private void UpdatePluginUpdateSummary()
    {
        PluginUpdateSummary = PluginUpdates.Count == 0
            ? "当前没有可用的 stable 更新。"
            : $"有 {PluginUpdates.Count} 个 stable 更新可用。";
    }

    private void RemovePluginUpdate(string pluginSlug, string? targetVersion = null)
    {
        var candidate = PluginUpdates.FirstOrDefault(item =>
            item.PluginSlug == pluginSlug
            && (targetVersion is null || item.TargetVersion == targetVersion));
        if (candidate is null)
        {
            return;
        }
        PluginUpdates.Remove(candidate);
        SelectedPluginUpdate = PluginUpdates.FirstOrDefault();
        UpdatePluginUpdateSummary();
    }

    private async Task LoadMarketAsync()
    {
        IsCanaryMode = false;
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

    private async Task LoadCanaryMarketAsync()
    {
        var accessToken = await TryGetAccessTokenAsync();
        if (string.IsNullOrWhiteSpace(accessToken))
        {
            Status = "加载 Canary 市场需要已登录的管理员账号。";
            return;
        }

        IsCanaryMode = true;
        BeginOperation("正在验证管理员权限并读取内部 Canary 市场…");
        try
        {
            var catalog = await _marketApi.GetCanaryPluginCatalogAsync(
                _serverBaseUrl,
                accessToken,
                MarketQuery);
            MarketPlugins.Clear();
            foreach (var item in catalog.Items)
            {
                MarketPlugins.Add(item);
            }
            SelectedMarketPlugin = MarketPlugins.FirstOrDefault();
            Status = $"内部 Canary 市场已加载 {MarketPlugins.Count} 个受控插件。";
        }
        catch (Exception exception)
        {
            MarketPlugins.Clear();
            SelectedMarketPlugin = null;
            Status = UserMessage("读取 Canary 市场失败", exception);
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
            var detail = IsCanaryMode
                ? await _marketApi.GetCanaryPluginDetailAsync(
                    _serverBaseUrl,
                    await TryGetAccessTokenAsync()
                        ?? throw new InvalidOperationException("加载 Canary 详情需要管理员登录。"),
                    SelectedMarketPlugin.Slug)
                : await _marketApi.GetPluginDetailAsync(
                    _serverBaseUrl,
                    SelectedMarketPlugin.Slug);
            var version = PluginSemver.LatestOrDefault(detail.Versions);
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
        var version = detail is null ? null : PluginSemver.LatestOrDefault(detail.Versions);
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
            var canaryAccessToken = IsCanaryMode
                ? await TryGetAccessTokenAsync()
                    ?? throw new InvalidOperationException("下载 Canary 插件需要管理员登录。")
                : null;
            var canaryIdentity = IsCanaryMode
                ? await (_identityService
                    ?? throw new InvalidOperationException("Canary 下载缺少安装实例身份。"))
                    .GetOrCreateAsync()
                : null;
            var canaryTicketSignature = canaryIdentity is null
                ? null
                : await _identityService!.SignAsync(
                    PasswordDetective.Desktop.Services.PluginCanaryCanonicalizer.BuildTicketRequest(
                        version.VersionId,
                        architecture,
                        canaryIdentity.InstallationId));
            _paths.EnsureDirectories();
            for (var attempt = 1; attempt <= 3; attempt++)
            {
                TryDeleteFile(temporaryPath);
                try
                {
                    failureStage = "download_ticket";
                    var ticket = IsCanaryMode
                        ? await _marketApi.IssueCanaryPluginDownloadTicketAsync(
                            _serverBaseUrl,
                            canaryAccessToken!,
                            version.VersionId,
                            architecture,
                            canaryIdentity!.InstallationId,
                            canaryTicketSignature!)
                        : await _marketApi.IssuePluginDownloadTicketAsync(
                            _serverBaseUrl,
                            detail.Slug,
                            version.Semver,
                            architecture);
                    failureStage = "artifact_download";
                    var canaryDownloadSignature = canaryIdentity is null
                        ? null
                        : await _identityService!.SignAsync(
                            PasswordDetective.Desktop.Services.PluginCanaryCanonicalizer.BuildDownload(
                                ticket.DownloadUrl,
                                canaryIdentity.InstallationId));
                    await _marketApi.DownloadPluginArtifactAsync(
                        ticket.DownloadUrl,
                        temporaryPath,
                        ticket.ArtifactSha256,
                        ticket.ArtifactSizeBytes,
                        accessToken: canaryAccessToken,
                        installationId: canaryIdentity?.InstallationId,
                        canarySignature: canaryDownloadSignature);
                    break;
                }
                catch (Exception exception) when (
                    attempt < 3 && exception is HttpRequestException or IOException)
                {
                    TryDeleteFile(temporaryPath);
                    await Task.Delay(TimeSpan.FromMilliseconds(500 * attempt));
                }
            }
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
                    existingMarket?.CurrentVersion,
                    existingMarket?.RiskTier,
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
            RemovePluginUpdate(detail.Slug, version.Semver);
            try
            {
                await RecordInstallEventBestEffortAsync(
                    detail.Slug,
                    version.Semver,
                    artifact.Architecture,
                    marketEventKind,
                    "success",
                    PluginSource.MarketReviewed,
                    result.Plugin);
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
            var failedPlugin = await _registry.GetAsync(detail.Slug);
            var failedEventKind = failedPlugin?.MigrationRecords?.ContainsKey(version.Semver) == true
                ? "upgraded"
                : "download_failed";
            await RecordInstallEventBestEffortAsync(
                detail.Slug,
                version.Semver,
                architecture,
                failedEventKind,
                "failure",
                PluginSource.MarketReviewed,
                failedPlugin);
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
        BeginOperation("正在卸载插件（保留私有数据）…");
        try
        {
            await _installer.UninstallAsync(pluginId);
            await RefreshInstalledAsync(null);
            RemovePluginUpdate(pluginId);
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
        string source,
        InstalledPlugin? evidencePlugin = null)
    {
        if (string.IsNullOrWhiteSpace(_serverBaseUrl))
        {
            return;
        }

        try
        {
            var accessToken = await TryGetAccessTokenAsync();
            var permissionEvidence = source == PluginSource.MarketReviewed
                                     && evidencePlugin?.PermissionConsents?.TryGetValue(
                                         semver,
                                         out var consent) == true
                ? new PasswordDetective.Desktop.Services.PluginPermissionEvidencePayload(
                    consent.RequestedCapabilities,
                    consent.ApprovedCapabilities,
                    consent.GrantedCapabilities,
                    consent.PublisherKeyFingerprint,
                    consent.RiskTier,
                    consent.ConsentedAt)
                : null;
            var migrationEvidence = source == PluginSource.MarketReviewed
                                    && evidencePlugin?.MigrationRecords?.TryGetValue(
                                        semver,
                                        out var migration) == true
                ? new PasswordDetective.Desktop.Services.PluginMigrationEvidencePayload(
                    migration.FromVersion,
                    migration.ToVersion,
                    migration.Status,
                    migration.StartedAt,
                    migration.CompletedAt,
                    (migration.Steps ?? []).Select(step =>
                        new PasswordDetective.Desktop.Services.PluginMigrationStepEvidencePayload(
                            step.StepId,
                            step.Status,
                            step.AttemptCount)).ToArray(),
                    migration.PackageSha256)
                : null;
            var eventId = Guid.NewGuid().ToString("N");
            var canSignEvidence = !string.IsNullOrWhiteSpace(accessToken)
                                  && _identityService is not null
                                  && (permissionEvidence is not null || migrationEvidence is not null);
            var identity = canSignEvidence
                ? await _identityService!.GetOrCreateAsync(CancellationToken.None)
                : null;
            var unsignedPayload = new PasswordDetective.Desktop.Services.PluginInstallEventRequest(
                eventId,
                pluginSlug,
                semver,
                architecture,
                source,
                kind,
                result,
                PluginPackageVerifier.HostVersion,
                canSignEvidence ? permissionEvidence : null,
                canSignEvidence ? migrationEvidence : null,
                identity?.InstallationId);
            var signature = identity is null
                ? null
                : await _identityService!.SignAsync(
                    PasswordDetective.Desktop.Services.PluginInstallEvidenceCanonicalizer.Build(
                        unsignedPayload),
                    CancellationToken.None);
            await _marketApi.RecordPluginInstallEventAsync(
                _serverBaseUrl,
                unsignedPayload with { EvidenceSignature = signature },
                accessToken);
        }
        catch
        {
            // Telemetry failure must not change a verified local state transition.
        }
    }

    private async Task<string?> TryGetAccessTokenAsync()
    {
        if (_accessTokenProvider is null)
        {
            return null;
        }

        try
        {
            return await _accessTokenProvider(CancellationToken.None);
        }
        catch (InvalidOperationException)
        {
            return null;
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
        LoadCanaryMarketCommand.NotifyCanExecuteChanged();
        LoadMarketDetailCommand.NotifyCanExecuteChanged();
        InstallMarketCommand.NotifyCanExecuteChanged();
        CheckPluginUpdatesCommand.NotifyCanExecuteChanged();
        UpgradeSelectedPluginCommand.NotifyCanExecuteChanged();
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
