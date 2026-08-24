using System.Windows;
using System.ComponentModel;
using PasswordDetective.Desktop.Plugins.ViewModels;

namespace PasswordDetective.Desktop;

public partial class PluginMarketplaceWindow : Window
{
    private readonly PluginMarketplaceViewModel _viewModel;

    public PluginMarketplaceWindow(PluginMarketplaceViewModel viewModel)
    {
        InitializeComponent();
        _viewModel = viewModel;
        DataContext = viewModel;
        Loaded += OnLoaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs eventArgs)
    {
        Loaded -= OnLoaded;
        if (_viewModel.InitializeCommand.CanExecute(null))
        {
            _viewModel.InitializeCommand.Execute(null);
        }
    }

    private void Window_OnClosing(object? sender, CancelEventArgs eventArgs)
    {
        if (_viewModel.IsBusy)
        {
            eventArgs.Cancel = true;
        }
    }
}
