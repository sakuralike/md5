using System.Text.Json;
using System.Windows;
using System.Windows.Controls;

namespace PasswordDetective.Desktop.Plugins.UI;

public sealed record PluginPanelDescriptor(
    string PanelId,
    string Title,
    double Width,
    double Height,
    IReadOnlyList<PluginPanelControl> Controls);

public sealed record PluginPanelControl(
    string Id,
    string Type,
    string Label,
    string? Value,
    bool? Checked);

public interface IPluginPanelHost
{
    Task<JsonElement> ShowAsync(
        string pluginId,
        PluginPanelDescriptor descriptor,
        CancellationToken cancellationToken = default);
}

public sealed class WpfPluginPanelHost : IPluginPanelHost
{
    public async Task<JsonElement> ShowAsync(
        string pluginId,
        PluginPanelDescriptor descriptor,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var application = Application.Current
            ?? throw new InvalidOperationException("WPF application is not initialized.");
        return await application.Dispatcher.InvokeAsync(() =>
        {
            var panel = new StackPanel
            {
                Margin = new Thickness(16),
            };
            foreach (var control in descriptor.Controls)
            {
                panel.Children.Add(CreateControl(control));
            }

            var window = new Window
            {
                Title = descriptor.Title,
                Width = descriptor.Width,
                Height = descriptor.Height,
                MinWidth = 320,
                MinHeight = 240,
                WindowStartupLocation = WindowStartupLocation.CenterOwner,
                Content = new ScrollViewer
                {
                    VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                    Content = panel,
                },
            };
            if (application.MainWindow is { IsLoaded: true } owner
                && !ReferenceEquals(owner, window))
            {
                window.Owner = owner;
            }

            window.Show();
            return JsonSerializer.SerializeToElement(new
            {
                shown = true,
                plugin_id = pluginId,
                panel_id = descriptor.PanelId,
                control_count = descriptor.Controls.Count,
                process_owned = true,
            });
        }).Task.ConfigureAwait(false);
    }

    private static FrameworkElement CreateControl(PluginPanelControl control) =>
        control.Type switch
        {
            "text" or "label" => new TextBlock
            {
                Text = control.Label,
                TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(0, 0, 0, 8),
            },
            "input" => new TextBox
            {
                Text = control.Value ?? string.Empty,
                ToolTip = control.Label,
                Margin = new Thickness(0, 0, 0, 8),
                MinWidth = 240,
            },
            "checkbox" => new CheckBox
            {
                Content = control.Label,
                IsChecked = control.Checked ?? false,
                Margin = new Thickness(0, 0, 0, 8),
            },
            "button" => new Button
            {
                Content = control.Label,
                Padding = new Thickness(12, 6, 12, 6),
                Margin = new Thickness(0, 0, 0, 8),
            },
            _ => throw new InvalidOperationException("Unsupported plugin panel control type."),
        };
}
