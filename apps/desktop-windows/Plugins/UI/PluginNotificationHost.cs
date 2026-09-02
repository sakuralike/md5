using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace PasswordDetective.Desktop.Plugins.UI;

public sealed record PluginNotification(
    string Title,
    string Message,
    string Severity,
    int DurationSeconds);

public interface IPluginNotificationHost
{
    Task<JsonElement> ShowAsync(
        string pluginId,
        PluginNotification notification,
        CancellationToken cancellationToken = default);
}

public sealed class WpfPluginNotificationHost : IPluginNotificationHost
{
    public async Task<JsonElement> ShowAsync(
        string pluginId,
        PluginNotification notification,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var application = Application.Current
            ?? throw new InvalidOperationException("WPF application is not initialized.");
        var notificationId = Guid.NewGuid().ToString("N");
        await application.Dispatcher.InvokeAsync(() =>
        {
            var window = new Window
            {
                Title = notification.Title,
                Width = 360,
                MinWidth = 320,
                SizeToContent = SizeToContent.Height,
                WindowStyle = WindowStyle.ToolWindow,
                ResizeMode = ResizeMode.NoResize,
                ShowInTaskbar = false,
                Topmost = true,
                WindowStartupLocation = WindowStartupLocation.CenterOwner,
                Content = new Border
                {
                    Padding = new Thickness(16),
                    BorderThickness = new Thickness(2),
                    BorderBrush = BrushFor(notification.Severity),
                    Child = new StackPanel
                    {
                        Children =
                        {
                            new TextBlock
                            {
                                Text = notification.Title,
                                FontWeight = FontWeights.SemiBold,
                                Margin = new Thickness(0, 0, 0, 8),
                            },
                            new TextBlock
                            {
                                Text = notification.Message,
                                TextWrapping = TextWrapping.Wrap,
                            },
                        },
                    },
                },
            };
            if (application.MainWindow is { IsLoaded: true } owner)
            {
                window.Owner = owner;
            }

            window.Show();
            _ = CloseLaterAsync(window, notification.DurationSeconds);
        }).Task.ConfigureAwait(false);

        return JsonSerializer.SerializeToElement(new
        {
            shown = true,
            notification_id = notificationId,
            plugin_id = pluginId,
            severity = notification.Severity,
        });
    }

    private static async Task CloseLaterAsync(Window window, int durationSeconds)
    {
        await Task.Delay(TimeSpan.FromSeconds(durationSeconds));
        await window.Dispatcher.InvokeAsync(() =>
        {
            if (window.IsVisible)
            {
                window.Close();
            }
        });
    }

    private static Brush BrushFor(string severity) => severity switch
    {
        "success" => Brushes.SeaGreen,
        "warning" => Brushes.DarkOrange,
        "error" => Brushes.Firebrick,
        _ => Brushes.SteelBlue,
    };
}
