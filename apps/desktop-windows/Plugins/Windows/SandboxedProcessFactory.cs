using System.IO;

namespace PasswordDetective.Desktop.Plugins.Windows;

internal interface ISandboxedProcessFactory
{
    ISandboxedProcess Start(PluginProcessStartOptions options);
}

internal interface ISandboxedProcess : IAsyncDisposable
{
    int ProcessId { get; }
    bool IsAppContainer { get; }
    bool HasExited { get; }
    int? ExitCode { get; }
    Stream StandardInput { get; }
    Stream StandardOutput { get; }
    Stream StandardError { get; }
}

internal sealed class WindowsSandboxedProcessFactory(
    IWindowsPluginIsolationPolicy isolationPolicy) : ISandboxedProcessFactory
{
    public ISandboxedProcess Start(PluginProcessStartOptions options) =>
        WindowsSandboxedProcess.Start(options, isolationPolicy);
}
