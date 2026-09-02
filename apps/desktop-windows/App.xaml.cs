using System.IO;
using System.Runtime.InteropServices;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;
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

    private async void Application_OnStartup(object sender, StartupEventArgs e)
    {
        if (e.Args.Contains("--host-sandbox", StringComparer.Ordinal))
        {
            try
            {
                await RunHostSandboxAsync(e.Args);
                Shutdown(0);
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.ToString());
                Shutdown(1);
            }

            return;
        }

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

    private static async Task RunHostSandboxAsync(IReadOnlyList<string> arguments)
    {
        var request = ReadArgument(arguments, "--request");
        var controlName = ReadArgument(arguments, "--control");
        var verifyPolicies = !arguments.Contains("--skip-policy", StringComparer.Ordinal);
        var options = JsonSerializer.Deserialize<PasswordDetective.Desktop.Plugins.PluginProcessStartOptions>(
            Convert.FromBase64String(request),
            new JsonSerializerOptions(JsonSerializerDefaults.Web))
            ?? throw new InvalidOperationException("Host.Sandbox 启动参数无效。");

        await using var process = await PasswordDetective.Desktop.Plugins.Windows.RustSandboxedProcess.StartAsync(
            options,
            CancellationToken.None,
            verifyPolicies);
        using var control = new NamedPipeClientStream(
            ".",
            controlName,
            PipeDirection.Out,
            PipeOptions.Asynchronous);
        await control.ConnectAsync(10_000);
        PasswordDetective.Desktop.Plugins.Windows.WindowsIntegrityLevel.LowerCurrentProcessToLow();
        await using (var writer = new StreamWriter(control, new UTF8Encoding(false), 4096, leaveOpen: true)
        {
            AutoFlush = true,
            NewLine = "\n",
        })
        {
            await writer.WriteLineAsync(JsonSerializer.Serialize(new
            {
                pid = process.ProcessId,
                is_appcontainer = process.IsAppContainer,
                integrity_level = PasswordDetective.Desktop.Plugins.Windows.WindowsIntegrityLevel.GetCurrent(),
            }));
        }

        var input = Console.OpenStandardInput();
        var output = Console.OpenStandardOutput();
        var error = Console.OpenStandardError();
        var inputTask = input.CopyToAsync(process.StandardInput);
        var outputTask = process.StandardOutput.CopyToAsync(output);
        var errorTask = process.StandardError.CopyToAsync(error);
        await inputTask;
        await process.DisposeAsync();
        await Task.WhenAll(outputTask, errorTask);
    }

    private static string ReadArgument(IReadOnlyList<string> arguments, string name)
    {
        var index = -1;
        for (var candidate = 0; candidate < arguments.Count; candidate++)
        {
            if (string.Equals(arguments[candidate], name, StringComparison.Ordinal))
            {
                index = candidate;
                break;
            }
        }
        if (index < 0 || index + 1 >= arguments.Count || string.IsNullOrWhiteSpace(arguments[index + 1]))
        {
            throw new InvalidOperationException($"Host.Sandbox 参数缺少 {name}。");
        }

        return arguments[index + 1];
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
