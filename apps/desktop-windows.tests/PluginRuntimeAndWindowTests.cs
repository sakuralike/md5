using System.Runtime.ExceptionServices;
using System.Text.Json;
using System.IO;
using PasswordDetective.Desktop.Plugins.Installation;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Permissions;
using PasswordDetective.Desktop.Plugins.Registry;
using PasswordDetective.Desktop.Plugins.Runtime;
using PasswordDetective.Desktop.Plugins.Safety;
using PasswordDetective.Desktop.Plugins.Storage;
using PasswordDetective.Desktop.Plugins.UI;
using PasswordDetective.Desktop.Plugins.ViewModels;

namespace PasswordDetective.Desktop.Tests;

public sealed class PluginRuntimeAndWindowTests : IDisposable
{
    private readonly string _directory = Path.Combine(
        Path.GetTempPath(),
        "password-detective-runtime-tests",
        Guid.NewGuid().ToString("N"));

    public PluginRuntimeAndWindowTests() => Directory.CreateDirectory(_directory);

    [Fact]
    public async Task ThreeConsecutiveFailuresDisablePlugin()
    {
        var paths = new PluginStoragePaths(Path.Combine(_directory, "plugins"));
        var registry = new PluginRegistry(paths);
        var package = new PluginPackageTestFactory().Create(
            _directory,
            pluginId: "com.synthetic.crash-plugin");
        var fakeExecution = new FailingExecutionService();
        var installer = new PluginInstaller(
            paths,
            new PluginPackageVerifier(),
            new PluginPermissionPolicy(),
            registry,
            fakeExecution);
        var installed = await installer.InstallLocalAsync(
            package,
            ["ui:command", "storage:private"]);
        var safeMode = new PluginSafeMode(paths);
        var runtime = new PluginRuntimeService(
            registry,
            fakeExecution,
            safeMode,
            new PluginLogStore(paths));

        for (var attempt = 0; attempt < 3; attempt++)
        {
            await Assert.ThrowsAsync<InvalidOperationException>(
                () => runtime.CheckHealthAsync(installed.Plugin.PluginId));
        }

        var disabled = await registry.GetAsync(installed.Plugin.PluginId);
        Assert.NotNull(disabled);
        Assert.False(disabled!.Enabled);
        Assert.Equal(3, disabled.ConsecutiveFailures);
        Assert.Equal("disabled", disabled.RuntimeStatus);
    }

    [Fact]
    public void PreviousUncleanMarkerStartsSafeModeAndCanBeLeftForCurrentSession()
    {
        var paths = new PluginStoragePaths(Path.Combine(_directory, "safe-mode"));
        paths.EnsureDirectories();
        File.WriteAllText(
            paths.SafeModeMarkerPath,
            """{"ProcessId":2147483647,"StartedAt":"2026-08-25T00:00:00Z"}""");
        var safeMode = new PluginSafeMode(paths);

        safeMode.BeginSession();

        Assert.True(safeMode.IsActive);
        safeMode.LeaveSafeModeForCurrentSession();
        Assert.False(safeMode.IsActive);
        safeMode.MarkCleanExit();
        Assert.False(File.Exists(paths.SafeModeMarkerPath));
    }

    [Fact]
    public void MarketplaceIsIndependentWindowWithRequiredTabsAndUnreviewedBanner()
    {
        ExceptionDispatchInfo? captured = null;
        var thread = new Thread(() =>
        {
            try
            {
                var paths = new PluginStoragePaths(Path.Combine(_directory, "window"));
                var registry = new PluginRegistry(paths);
                var execution = new SuccessfulExecutionService();
                var safeMode = new PluginSafeMode(paths);
                var permissions = new PluginPermissionPolicy();
                var installer = new PluginInstaller(
                    paths,
                    new PluginPackageVerifier(),
                    permissions,
                    registry,
                    execution);
                var runtime = new PluginRuntimeService(
                    registry,
                    execution,
                    safeMode,
                    new PluginLogStore(paths));
                var viewModel = new PluginMarketplaceViewModel(
                    paths,
                    installer,
                    permissions,
                    registry,
                    runtime,
                    safeMode,
                    new RejectingDialogService());
                var window = new PluginMarketplaceWindow(viewModel);

                Assert.IsAssignableFrom<System.Windows.Window>(window);
                Assert.Equal("密码侦探社 - 插件市场", window.Title);
                Assert.Equal("在线市场", window.OnlineMarketTab.Header);
                Assert.Equal("已安装", window.InstalledPluginsTab.Header);
                Assert.Equal("本地插件", window.LocalPluginsTab.Header);
                Assert.NotNull(window.UnreviewedBanner);
                Assert.Equal(PluginSource.LocalUnreviewedLabel, viewModel.ReviewLabel);
                window.Close();
            }
            catch (Exception exception)
            {
                captured = ExceptionDispatchInfo.Capture(exception);
            }
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        Assert.True(thread.Join(TimeSpan.FromSeconds(15)));
        captured?.Throw();
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory))
        {
            Directory.Delete(_directory, recursive: true);
        }
    }

    private sealed class FailingExecutionService : IPluginExecutionService
    {
        public Task ValidateAsync(
            PluginPackageInspection inspection,
            string installedDirectory,
            IReadOnlyList<string> grantedCapabilities,
            CancellationToken cancellationToken = default) => Task.CompletedTask;

        public Task<JsonElement> ExecuteAsync(
            InstalledPlugin plugin,
            string command,
            JsonElement input,
            CancellationToken cancellationToken = default) =>
            Task.FromException<JsonElement>(new InvalidOperationException("synthetic crash"));

        public Task CheckHealthAsync(
            InstalledPlugin plugin,
            CancellationToken cancellationToken = default) =>
            Task.FromException(new InvalidOperationException("synthetic crash"));
    }

    private sealed class SuccessfulExecutionService : IPluginExecutionService
    {
        public Task ValidateAsync(
            PluginPackageInspection inspection,
            string installedDirectory,
            IReadOnlyList<string> grantedCapabilities,
            CancellationToken cancellationToken = default) => Task.CompletedTask;

        public Task<JsonElement> ExecuteAsync(
            InstalledPlugin plugin,
            string command,
            JsonElement input,
            CancellationToken cancellationToken = default) => Task.FromResult(input);

        public Task CheckHealthAsync(
            InstalledPlugin plugin,
            CancellationToken cancellationToken = default) => Task.CompletedTask;
    }

    private sealed class RejectingDialogService : IPluginDialogService
    {
        public string? SelectPackage() => null;
        public string? SelectPath(PluginCommandFieldKind kind) => null;
        public bool ConfirmInstall(
            PluginPackageInspection inspection,
            PluginPermissionDecision permission) => false;
        public bool ConfirmMarketInstall(
            PasswordDetective.Desktop.Plugins.Market.MarketPluginDetail detail,
            PasswordDetective.Desktop.Plugins.Market.MarketPluginVersion version,
            PluginPermissionDecision permission,
            IReadOnlyList<string> addedCapabilities,
            bool signingKeyChanged,
            bool majorVersionChanged) => false;
        public bool ConfirmUninstall(InstalledPlugin plugin) => false;
    }
}
