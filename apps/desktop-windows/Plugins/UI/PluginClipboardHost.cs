using System.Text.Json;
using System.Windows;

namespace PasswordDetective.Desktop.Plugins.UI;

public interface IPluginClipboardHost
{
    Task<JsonElement> ReadAsync(CancellationToken cancellationToken = default);
    Task<JsonElement> WriteAsync(string text, CancellationToken cancellationToken = default);
}

public sealed class WpfPluginClipboardHost : IPluginClipboardHost
{
    private const int MaximumTextLength = 64 * 1024;

    public async Task<JsonElement> ReadAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var application = Application.Current
            ?? throw new InvalidOperationException("WPF application is not initialized.");
        return await application.Dispatcher.InvokeAsync(() =>
        {
            var available = Clipboard.ContainsText();
            var text = available ? Clipboard.GetText() : string.Empty;
            var truncated = text.Length > MaximumTextLength;
            if (truncated)
            {
                text = text[..MaximumTextLength];
            }

            return JsonSerializer.SerializeToElement(new
            {
                available,
                text,
                truncated,
            });
        }).Task.ConfigureAwait(false);
    }

    public async Task<JsonElement> WriteAsync(
        string text,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (text.Length > MaximumTextLength)
        {
            throw new ArgumentOutOfRangeException(nameof(text));
        }

        var application = Application.Current
            ?? throw new InvalidOperationException("WPF application is not initialized.");
        await application.Dispatcher.InvokeAsync(() => Clipboard.SetText(text)).Task.ConfigureAwait(false);
        return JsonSerializer.SerializeToElement(new { written = true, length = text.Length });
    }
}
