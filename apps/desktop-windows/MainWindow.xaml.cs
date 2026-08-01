using System.Windows;
using PasswordDetective.Desktop.Services;
using PasswordDetective.Desktop.ViewModels;

namespace PasswordDetective.Desktop;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        DataContext = new MainWindowViewModel(new FileFingerprintService());
    }
}
