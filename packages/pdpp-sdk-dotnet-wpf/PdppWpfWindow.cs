using System.Windows;
using System.Threading;
using System.Windows.Threading;
using PasswordDetective.Pdpp;

namespace PasswordDetective.Pdpp.Wpf;

public sealed record PdppWpfWindowOptions(
    string WindowId,
    string Title,
    double Width = 640,
    double Height = 480,
    bool Modal = true);

public static class PdppWpfWindow
{
    public static async Task ShowAsync(
        PdppHostClient host,
        PdppWpfWindowOptions options,
        Func<Window> createWindow,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(createWindow);
        await host.RequestWindowAsync(
            options.WindowId,
            options.Title,
            options.Width,
            options.Height,
            options.Modal,
            cancellationToken);

        var completion = new TaskCompletionSource<object?>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        var thread = new Thread(() =>
        {
            try
            {
                var application = Application.Current ?? new Application();
                var dispatcher = application.Dispatcher;
                var window = createWindow();
                window.Title = options.Title;
                window.Width = options.Width;
                window.Height = options.Height;
                window.WindowStartupLocation = WindowStartupLocation.CenterScreen;
                window.Closed += (_, _) =>
                {
                    completion.TrySetResult(null);
                    dispatcher.BeginInvokeShutdown(DispatcherPriority.Background);
                };
                if (options.Modal)
                {
                    window.ShowDialog();
                }
                else
                {
                    window.Show();
                    Dispatcher.Run();
                }
            }
            catch (Exception exception)
            {
                completion.TrySetException(exception);
            }
        })
        {
            IsBackground = true,
            Name = $"PDPP-WPF-{options.WindowId}",
        };
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        using var registration = cancellationToken.Register(() => completion.TrySetCanceled(cancellationToken));
        await completion.Task.ConfigureAwait(false);
    }
}
