namespace PasswordDetective.Desktop.Plugins.Windows;

internal interface ISandboxedProcessFactory
{
    WindowsSandboxedProcess Start(PluginProcessStartOptions options);
}

internal sealed class WindowsSandboxedProcessFactory(
    IWindowsPluginIsolationPolicy isolationPolicy) : ISandboxedProcessFactory
{
    public WindowsSandboxedProcess Start(PluginProcessStartOptions options) =>
        WindowsSandboxedProcess.Start(options, isolationPolicy);
}
