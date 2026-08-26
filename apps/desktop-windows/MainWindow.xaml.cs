using System.IO;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using PasswordDetective.Desktop.Plugins.Installation;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Permissions;
using PasswordDetective.Desktop.Plugins.Registry;
using PasswordDetective.Desktop.Plugins.Runtime;
using PasswordDetective.Desktop.Plugins.Safety;
using PasswordDetective.Desktop.Plugins.Storage;
using PasswordDetective.Desktop.Plugins.Theme;
using PasswordDetective.Desktop.Plugins.UI;
using PasswordDetective.Desktop.Plugins.ViewModels;
using PasswordDetective.Desktop.Services;
using PasswordDetective.Desktop.ViewModels;

namespace PasswordDetective.Desktop;

public partial class MainWindow : Window
{
    private readonly MainWindowViewModel _viewModel;
    private readonly PluginStoragePaths _pluginPaths;
    private readonly PluginSafeMode _pluginSafeMode;
    private readonly PluginThemeService _pluginThemeService;
    private PluginMarketplaceWindow? _pluginMarketplaceWindow;

    public MainWindow(PluginStoragePaths pluginPaths, PluginSafeMode pluginSafeMode)
    {
        InitializeComponent();
        _pluginPaths = pluginPaths;
        _pluginSafeMode = pluginSafeMode;
        _pluginThemeService = new PluginThemeService(_pluginPaths.RootDirectory, ApplyThemeAsync);
        _viewModel = new MainWindowViewModel(
            new FileFingerprintService(),
            new ArchiveVerificationService(),
            new InstallationIdentityService(),
            new DesktopApiClient(),
            new ProtectedSessionStore(),
            new ExternalUriLauncher());
        DataContext = _viewModel;
        Loaded += async (_, _) => await _pluginThemeService.ApplyPersistedAsync();
    }

    private void OpenPluginMarketplace_OnClick(object sender, RoutedEventArgs eventArgs)
    {
        if (_pluginMarketplaceWindow is { IsLoaded: true })
        {
            if (_pluginMarketplaceWindow.WindowState == WindowState.Minimized)
            {
                _pluginMarketplaceWindow.WindowState = WindowState.Normal;
            }

            _pluginMarketplaceWindow.Activate();
            return;
        }

        var registry = new PluginRegistry(_pluginPaths);
        var permissionPolicy = new PluginPermissionPolicy();
        var logs = new PluginLogStore(_pluginPaths);
        var brokerApiClient = new DesktopApiClient();
        var pluginApiBroker = new PluginApiBroker(
            brokerApiClient,
            new InstallationIdentityService(),
            async cancellationToken =>
            {
                var session = await _viewModel.GetSessionForPluginBrokerAsync(cancellationToken);
                return new PluginBrokerSession(
                    session.ServerBaseUrl,
                    session.AccessToken,
                    session.AccountId);
            });
        var execution = new PluginExecutionService(
            _pluginPaths,
            logs,
            pluginApiBroker,
            _pluginThemeService);
        var installer = new PluginInstaller(
            _pluginPaths,
            new PluginPackageVerifier(),
            permissionPolicy,
            registry,
            execution);
        var runtime = new PluginRuntimeService(
            registry,
            execution,
            _pluginSafeMode,
            logs);
        var viewModel = new PluginMarketplaceViewModel(
            _pluginPaths,
            installer,
            permissionPolicy,
            registry,
            runtime,
            _pluginSafeMode,
            new PluginDialogService(),
            _viewModel.ServerBaseUrl);
        _pluginMarketplaceWindow = new PluginMarketplaceWindow(viewModel)
        {
            Owner = this,
        };
        _pluginMarketplaceWindow.Closed += (_, _) => _pluginMarketplaceWindow = null;
        _pluginMarketplaceWindow.Show();
    }

    private void CandidatePasswordBox_OnPasswordChanged(object sender, RoutedEventArgs eventArgs) =>
        _viewModel.SetCandidatePassword(CandidatePasswordBox.Password);

    private void LoginPasswordBox_OnPasswordChanged(object sender, RoutedEventArgs eventArgs) =>
        _viewModel.SetLoginPassword(LoginPasswordBox.Password);

    private void Window_OnDragOver(object sender, DragEventArgs eventArgs) =>
        eventArgs.Effects = eventArgs.Data.GetDataPresent(DataFormats.FileDrop)
            ? DragDropEffects.Copy
            : DragDropEffects.None;

    private void Window_OnDrop(object sender, DragEventArgs eventArgs)
    {
        if (eventArgs.Data.GetData(DataFormats.FileDrop) is string[] files && files.Length > 0)
        {
            _viewModel.AcceptFile(files[0]);
        }
    }

    private Task ApplyThemeAsync(PluginThemeSettings settings, CancellationToken cancellationToken)
    {
        return Dispatcher.InvokeAsync(() =>
        {
            var background = new SolidColorBrush(settings.Preset switch
            {
                "dark" => Color.FromRgb(38, 45, 52),
                "forest" => Color.FromRgb(38, 81, 61),
                "contrast" => Color.FromRgb(0, 0, 0),
                _ => Color.FromRgb(240, 240, 240),
            });
            Background = background;
            if (string.IsNullOrWhiteSpace(settings.BackgroundFileName))
            {
                MainLayout.Background = null;
                return;
            }

            var path = Path.Combine(_pluginPaths.RootDirectory, "theme-backgrounds", settings.BackgroundFileName);
            if (!File.Exists(path))
            {
                MainLayout.Background = null;
                return;
            }

            var image = new BitmapImage();
            image.BeginInit();
            image.CacheOption = BitmapCacheOption.OnLoad;
            image.UriSource = new System.Uri(path, System.UriKind.Absolute);
            image.EndInit();
            image.Freeze();
            MainLayout.Background = new ImageBrush(image)
            {
                Stretch = Stretch.UniformToFill,
                Opacity = settings.BackgroundOpacity,
            };
        }, System.Windows.Threading.DispatcherPriority.Normal, cancellationToken).Task;
    }
}
