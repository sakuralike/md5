using System.Windows;
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
            new ProtectedSessionStore());
        DataContext = _viewModel;
    }

    private void CandidatePasswordBox_OnPasswordChanged(object sender, RoutedEventArgs eventArgs) =>
        _viewModel.SetCandidatePassword(CandidatePasswordBox.Password);

    private void LoginPasswordBox_OnPasswordChanged(object sender, RoutedEventArgs eventArgs) =>
        _viewModel.SetLoginPassword(LoginPasswordBox.Password);
}
