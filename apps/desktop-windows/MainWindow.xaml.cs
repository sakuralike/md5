using System.Windows;
using System.Windows.Input;
using PasswordDetective.Desktop.Services;
using PasswordDetective.Desktop.ViewModels;

namespace PasswordDetective.Desktop;

public partial class MainWindow : Window
{
    private readonly MainWindowViewModel _viewModel;

    public MainWindow()
    {
        InitializeComponent();
        _viewModel = new MainWindowViewModel(
            new FileFingerprintService(),
            new ArchiveVerificationService(),
            new InstallationIdentityService(),
            new DesktopApiClient(),
            new ProtectedSessionStore(),
            new ExternalUriLauncher());
        DataContext = _viewModel;
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
}
