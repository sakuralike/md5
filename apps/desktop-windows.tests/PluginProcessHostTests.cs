using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text.Json;
using PasswordDetective.Desktop.Plugins;
using PasswordDetective.Desktop.Plugins.Protocol;

namespace PasswordDetective.Desktop.Tests;

public sealed class PluginProcessHostTests : IDisposable
{
    private readonly string _workingDirectory = Path.Combine(
        Path.GetTempPath(),
        "password-detective-plugin-host",
        Guid.NewGuid().ToString("N"));

    public PluginProcessHostTests() => Directory.CreateDirectory(_workingDirectory);

    [Fact]
    public async Task HostCompletesInitializeHealthAndEchoContract()
    {
        await using var host = await StartHostAsync(memoryLimitBytes: 256L * 1024 * 1024);

        var initialized = await host.InitializeAsync("0.1.0", ["command.echo"], TimeSpan.FromSeconds(5));
        var health = await host.InvokeAsync<object, PdppHealthResult>(
            PdppProtocol.HealthCheckMethod,
            new { },
            TimeSpan.FromSeconds(5));
        var echo = await ExecuteAsync<SyntheticEchoResult>(host, "echo", "synthetic-message");

        Assert.Equal(PdppProtocol.ProtocolVersion, initialized.ProtocolVersion);
        Assert.Equal("synthetic.csharp", initialized.PluginId);
        Assert.Equal("healthy", health.Status);
        Assert.Equal("synthetic-message", echo.Output);
        Assert.Equal("csharp", echo.Language);
    }

    [Fact]
    public async Task TimeoutTerminatesUnresponsivePluginWithoutTerminatingHostProcess()
    {
        await using var host = await StartHostAsync(memoryLimitBytes: 256L * 1024 * 1024);
        await host.InitializeAsync("0.1.0", [], TimeSpan.FromSeconds(5));
        var currentProcessId = Environment.ProcessId;

        await Assert.ThrowsAsync<TimeoutException>(
            () => ExecuteAsync<JsonElement>(host, "hang", null, TimeSpan.FromMilliseconds(250)));

        await WaitUntilAsync(() => host.HasExited, TimeSpan.FromSeconds(5));
        Assert.Equal(currentProcessId, Environment.ProcessId);
        Assert.False(Process.GetCurrentProcess().HasExited);
    }

    [Fact]
    public async Task CallerCancellationTerminatesUnresponsivePlugin()
    {
        await using var host = await StartHostAsync(memoryLimitBytes: 256L * 1024 * 1024);
        await host.InitializeAsync("0.1.0", [], TimeSpan.FromSeconds(5));
        using var cancellation = new CancellationTokenSource(TimeSpan.FromMilliseconds(250));

        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => ExecuteAsync<JsonElement>(
                host,
                "hang",
                null,
                TimeSpan.FromSeconds(10),
                cancellation.Token));

        await WaitUntilAsync(() => host.HasExited, TimeSpan.FromSeconds(5));
    }

    [Fact]
    public async Task ClosingHostKillsPluginProcessTree()
    {
        var host = await StartHostAsync(memoryLimitBytes: 256L * 1024 * 1024);
        await host.InitializeAsync("0.1.0", [], TimeSpan.FromSeconds(5));
        var result = await ExecuteAsync<SyntheticChildResult>(host, "spawn-child", null);
        Assert.True(IsRunning(result.ChildPid));

        await host.DisposeAsync();

        await WaitUntilAsync(() => !IsRunning(result.ChildPid), TimeSpan.FromSeconds(5));
        Assert.False(IsRunning(result.ChildPid));
    }

    [Fact]
    public async Task JobMemoryLimitTerminatesAllocatingPlugin()
    {
        await using var host = await StartHostAsync(memoryLimitBytes: 128L * 1024 * 1024);
        await host.InitializeAsync("0.1.0", [], TimeSpan.FromSeconds(5));

        await Assert.ThrowsAnyAsync<Exception>(
            () => ExecuteAsync<JsonElement>(host, "allocate", null, TimeSpan.FromSeconds(10)));

        await WaitUntilAsync(() => host.HasExited, TimeSpan.FromSeconds(5));
    }

    [Fact]
    public async Task PluginCrashReturnsBoundedDiagnosticAndLeavesHostAlive()
    {
        await using var host = await StartHostAsync(memoryLimitBytes: 256L * 1024 * 1024);
        await host.InitializeAsync("0.1.0", [], TimeSpan.FromSeconds(5));

        var exception = await Assert.ThrowsAsync<PdppProcessExitedException>(
            () => ExecuteAsync<JsonElement>(host, "crash", null));

        Assert.Equal(23, exception.ExitCode);
        Assert.Contains("synthetic crash", exception.StandardError);
        Assert.False(Process.GetCurrentProcess().HasExited);
    }

    [Fact]
    public async Task AppContainerBlocksUnauthorizedFileAndNetworkAccess()
    {
        var secretDirectory = Path.Combine(
            Path.GetTempPath(),
            "password-detective-plugin-secret",
            Guid.NewGuid().ToString("N"));
        CreatePrivateDirectory(secretDirectory);
        var secretPath = Path.Combine(secretDirectory, "synthetic-secret.txt");
        await File.WriteAllTextAsync(secretPath, "synthetic-private-value");
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;

        try
        {
            var options = new PluginProcessStartOptions
            {
                PluginId = $"synthetic.appcontainer{Guid.NewGuid():N}",
                ExecutablePath = FindSyntheticPlugin(),
                WorkingDirectory = _workingDirectory,
                MemoryLimitBytes = 256L * 1024 * 1024,
                ActiveProcessLimit = 1,
                DeleteAppContainerProfileOnDispose = true,
            };
            await using var host = await PluginProcessHost.StartAsync(options);
            await host.InitializeAsync("0.1.0", [], TimeSpan.FromSeconds(5));

            var result = await ExecuteAsync<SyntheticProbeResult>(host, "probe", new
            {
                file_path = secretPath,
                host = IPAddress.Loopback.ToString(),
                port,
            });

            Assert.True(host.IsAppContainer);
            Assert.False(result.FileRead);
            Assert.False(result.NetworkConnected);
        }
        finally
        {
            listener.Stop();
            Directory.Delete(secretDirectory, recursive: true);
        }
    }

    [Fact]
    public async Task PluginEnvironmentDoesNotInheritParentSecrets()
    {
        const string secretName = "PDPP_SYNTHETIC_PARENT_SECRET";
        var previous = Environment.GetEnvironmentVariable(secretName);
        Environment.SetEnvironmentVariable(secretName, "synthetic-secret-value");
        try
        {
            await using var host = await StartHostAsync(memoryLimitBytes: 256L * 1024 * 1024);
            await host.InitializeAsync("0.1.0", [], TimeSpan.FromSeconds(5));

            var result = await ExecuteAsync<SyntheticEnvironmentResult>(host, "environment", secretName);

            Assert.False(result.Present);
        }
        finally
        {
            Environment.SetEnvironmentVariable(secretName, previous);
        }
    }

    [Fact]
    public async Task OversizedResponseTerminatesPlugin()
    {
        await using var host = await StartHostAsync(
            memoryLimitBytes: 256L * 1024 * 1024,
            maximumMessageBytes: 4096);
        await host.InitializeAsync("0.1.0", [], TimeSpan.FromSeconds(5));

        var exception = await Assert.ThrowsAsync<PdppProtocolException>(
            () => ExecuteAsync<JsonElement>(host, "oversized-output", null));

        Assert.Contains("message limit", exception.Message);
        Assert.True(host.HasExited);
    }

    [Fact]
    public async Task MalformedEnvelopeTerminatesPluginWithProtocolError()
    {
        await using var host = await StartHostAsync(memoryLimitBytes: 256L * 1024 * 1024);
        await host.InitializeAsync("0.1.0", [], TimeSpan.FromSeconds(5));

        var exception = await Assert.ThrowsAsync<PdppProtocolException>(
            () => ExecuteAsync<JsonElement>(host, "malformed-envelope", null));

        Assert.Contains("JSON-RPC envelope", exception.Message);
        Assert.True(host.HasExited);
    }

    [Fact]
    public async Task DisposeCancelsActiveRequestAndIsIdempotent()
    {
        var host = await StartHostAsync(memoryLimitBytes: 256L * 1024 * 1024);
        await host.InitializeAsync("0.1.0", [], TimeSpan.FromSeconds(5));
        var request = ExecuteAsync<JsonElement>(host, "hang", null, TimeSpan.FromSeconds(30));
        await Task.Delay(100);

        await host.DisposeAsync();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => request);
        await host.DisposeAsync();
        Assert.True(host.HasExited);
    }

    public void Dispose()
    {
        if (Directory.Exists(_workingDirectory))
        {
            Directory.Delete(_workingDirectory, recursive: true);
        }
    }

    private Task<PluginProcessHost> StartHostAsync(
        long memoryLimitBytes,
        int maximumMessageBytes = PdppProtocol.DefaultMaximumMessageBytes)
    {
        var options = new PluginProcessStartOptions
        {
            PluginId = "synthetic.csharp",
            ExecutablePath = FindSyntheticPlugin(),
            WorkingDirectory = _workingDirectory,
            MemoryLimitBytes = memoryLimitBytes,
            ActiveProcessLimit = 4,
            MaximumMessageBytes = maximumMessageBytes,
        }.WithoutAppContainerForTests();
        return PluginProcessHost.StartAsync(options);
    }

    private static void CreatePrivateDirectory(string path)
    {
        Directory.CreateDirectory(path);
        var currentUser = WindowsIdentity.GetCurrent().User
            ?? throw new InvalidOperationException("The current Windows user SID is unavailable.");
        var security = new DirectorySecurity();
        security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);
        security.AddAccessRule(new FileSystemAccessRule(
            currentUser,
            FileSystemRights.FullControl,
            InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
            PropagationFlags.None,
            AccessControlType.Allow));
        new DirectoryInfo(path).SetAccessControl(security);
    }

    private static Task<TResult> ExecuteAsync<TResult>(
        PluginProcessHost host,
        string command,
        object? input,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        return host.InvokeAsync<PdppCommandParams, TResult>(
            PdppProtocol.ExecuteCommandMethod,
            new PdppCommandParams(command, JsonSerializer.SerializeToElement(input)),
            timeout ?? TimeSpan.FromSeconds(5),
            cancellationToken);
    }

    private static string FindSyntheticPlugin()
    {
        var root = FindRepositoryRoot();
        foreach (var configuration in new[] { "Release", "Debug" })
        {
            var path = Path.Combine(
                root,
                "tests",
                "fixtures",
                "pdpp",
                "csharp",
                "bin",
                configuration,
                "net10.0",
                "pdpp-synthetic-plugin.exe");
            if (File.Exists(path))
            {
                return path;
            }
        }

        throw new FileNotFoundException("The C# PDPP synthetic plugin was not built.");
    }

    private static string FindRepositoryRoot()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(directory.FullName, ".git"))
                || Directory.Exists(Path.Combine(directory.FullName, ".git")))
            {
                return directory.FullName;
            }

            directory = directory.Parent;
        }

        throw new DirectoryNotFoundException("Repository root was not found.");
    }

    private static bool IsRunning(int processId)
    {
        try
        {
            using var process = Process.GetProcessById(processId);
            return !process.HasExited;
        }
        catch (ArgumentException)
        {
            return false;
        }
    }

    private static async Task WaitUntilAsync(Func<bool> predicate, TimeSpan timeout)
    {
        var deadline = DateTimeOffset.UtcNow + timeout;
        while (!predicate() && DateTimeOffset.UtcNow < deadline)
        {
            await Task.Delay(50);
        }
    }

    private sealed record SyntheticEchoResult(string Output, string Language);
    private sealed record SyntheticChildResult(int ChildPid, string Language);
    private sealed record SyntheticProbeResult(bool FileRead, bool NetworkConnected, string Language);
    private sealed record SyntheticEnvironmentResult(bool Present, string Language);
}
