using System.IO;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Threading;
using PasswordDetective.Desktop.Plugins.Safety;
using PasswordDetective.Desktop.Plugins.Storage;

namespace PasswordDetective.Desktop;

public partial class App : Application
{
    private const uint NativeMessageBoxError = 0x00000010;
    private static int _failureReported;
    private PluginSafeMode? _pluginSafeMode;
    private bool _pluginSessionFaulted;

    public App()
    {
        DispatcherUnhandledException += OnDispatcherUnhandledException;
        AppDomain.CurrentDomain.UnhandledException += OnUnhandledException;
    }

    private void Application_OnStartup(object sender, StartupEventArgs e)
    {
        try
        {
            EnsureWindowsDirectoryEnvironment();
            var pluginPaths = PluginStoragePaths.CreateDefault();
            _pluginSafeMode = new PluginSafeMode(pluginPaths);
            _pluginSafeMode.BeginSession();
            var window = new MainWindow(pluginPaths, _pluginSafeMode);
            MainWindow = window;
            window.Show();
        }
        catch (Exception exception)
        {
            _pluginSessionFaulted = true;
            ReportStartupFailure(exception);
            Shutdown(1);
        }
    }

    protected override void OnExit(ExitEventArgs e)
    {
        if (!_pluginSessionFaulted)
        {
            _pluginSafeMode?.MarkCleanExit();
        }
        base.OnExit(e);
    }

    private static void EnsureWindowsDirectoryEnvironment()
    {
        if (!string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("windir")))
        {
            return;
        }

        var windowsDirectory = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
        if (string.IsNullOrWhiteSpace(windowsDirectory))
        {
            windowsDirectory = Directory.GetParent(Environment.SystemDirectory)?.FullName;
        }

        if (string.IsNullOrWhiteSpace(windowsDirectory) || !Directory.Exists(windowsDirectory))
        {
            throw new DirectoryNotFoundException("无法定位 Windows 系统目录，桌面端无法初始化字体资源。");
        }

        Environment.SetEnvironmentVariable(
            "windir",
            windowsDirectory,
            EnvironmentVariableTarget.Process);
    }

    private void OnDispatcherUnhandledException(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        _pluginSessionFaulted = true;
        e.Handled = true;
        ReportStartupFailure(e.Exception);
        Shutdown(1);
    }

    private void OnUnhandledException(object sender, UnhandledExceptionEventArgs e)
    {
        _pluginSessionFaulted = true;
        if (e.ExceptionObject is Exception exception)
        {
            ReportStartupFailure(exception);
        }
    }

    private static void ReportStartupFailure(Exception exception)
    {
        if (Interlocked.Exchange(ref _failureReported, 1) != 0)
        {
            return;
        }

        var logDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "PasswordDetective",
            "logs");
        var logPath = Path.Combine(logDirectory, "desktop-startup.log");
        try
        {
            Directory.CreateDirectory(logDirectory);
            File.AppendAllText(
                logPath,
                $"[{DateTimeOffset.Now:O}] 桌面端启动失败{Environment.NewLine}{exception}{Environment.NewLine}{Environment.NewLine}");
        }
        catch
        {
            // Logging must never hide the original startup failure.
        }

        try
        {
            NativeMessageBox(
                IntPtr.Zero,
                $"密码侦探社桌面端启动失败。\n\n详细错误已写入：\n{logPath}",
                "密码侦探社",
                NativeMessageBoxError);
        }
        catch
        {
            // Native message box is best-effort only.
        }
    }

    [DllImport("user32.dll", EntryPoint = "MessageBoxW", CharSet = CharSet.Unicode)]
    private static extern int NativeMessageBox(
        IntPtr hWnd,
        string text,
        string caption,
        uint type);
}
