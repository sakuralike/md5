using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text.Json;
using PasswordDetective.Desktop.Plugins;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Protocol;
using PasswordDetective.Desktop.Plugins.Runtime;
using PasswordDetective.Desktop.Plugins.Storage;
using PasswordDetective.Desktop.Plugins.Theme;
using PasswordDetective.Desktop.Plugins.Windows;

namespace PasswordDetective.Desktop.Tests;

public sealed class PluginProcessHostTests : IDisposable
{
    private readonly string _workingDirectory = Path.Combine(
        Path.GetTempPath(),
        "password-detective-plugin-host",
        Guid.NewGuid().ToString("N"));

    public PluginProcessHostTests() => Directory.CreateDirectory(_workingDirectory);

    [Fact]
    public async Task PackagedSandboxCoreStartsAndServesBoundedRpc()
    {
        await using var sandbox = HostSandboxProcess.Start();
        using var response = await sandbox.InvokeAsync(
            "env.sanitize",
            new { host_secret_keys = new[] { "APP_SECRET_KEY" } },
            TimeSpan.FromSeconds(5));

        Assert.True(sandbox.ProcessId > 0);
        Assert.Equal("ok", response.RootElement.GetProperty("result").GetProperty("status").GetString());
        Assert.False(response.RootElement
            .GetProperty("result")
            .GetProperty("environment")
            .TryGetProperty("APP_SECRET_KEY", out _));
    }

    [Fact]
    public async Task HostCompletesInitializeHealthAndEchoContract()
    {
        await using var host = await StartHostAsync(memoryLimitBytes: 256L * 1024 * 1024);

        Assert.True(host.IsAppContainer);

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
    public async Task HostRejectsPluginWhenExplicitIsolationPoliciesAreMissing()
    {
        var options = new PluginProcessStartOptions
        {
            PluginId = $"synthetic.explicit-isolation{Guid.NewGuid():N}",
            ExecutablePath = FindSyntheticPlugin(),
            WorkingDirectory = _workingDirectory,
            MemoryLimitBytes = 256L * 1024 * 1024,
            ActiveProcessLimit = 1,
            DeleteAppContainerProfileOnDispose = true,
        };

        await Assert.ThrowsAsync<PluginExplicitIsolationException>(
            () => PluginProcessHost.StartAsync(options));
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
            await using var host = await PluginProcessHost.StartWithIsolationPolicyAsync(
                options,
                NoOpWindowsPluginIsolationPolicy.Instance);
            await host.InitializeAsync("0.1.0", [], TimeSpan.FromSeconds(5));

            var result = await ExecuteAsync<SyntheticProbeResult>(host, "probe", new
            {
                file_path = secretPath,
                host = IPAddress.Loopback.ToString(),
                port,
            });
            var registry = await ExecuteAsync<SyntheticRegistryResult>(host, "registry-write", null);

            Assert.True(host.IsAppContainer);
            Assert.False(result.FileRead);
            Assert.False(result.NetworkConnected);
            Assert.False(registry.RegistryWrite);
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

    [Fact]
    public async Task PluginReadsOnlyOpaqueGrantedFileThroughHostCallback()
    {
        var privateFile = Path.Combine(_workingDirectory, "selected.txt");
        await File.WriteAllTextAsync(privateFile, "synthetic broker content");
        var installedDirectory = Path.Combine(_workingDirectory, "installed");
        var schemaDirectory = Path.Combine(installedDirectory, "schemas");
        Directory.CreateDirectory(schemaDirectory);
        await File.WriteAllTextAsync(
            Path.Combine(schemaDirectory, "read.schema.json"),
            """{"type":"object","properties":{"file":{"type":"string","format":"file"}}}""");
        var paths = new PluginStoragePaths(Path.Combine(_workingDirectory, "broker-storage"));
        using var broker = new PluginHostBroker(
            "synthetic.csharp",
            "1.0.0",
            ["file:read:selected", "storage:private"],
            new PluginPrivateStorage(paths));
        var input = broker.PrepareCommandInput(
            new PluginCommandManifest("host-file-read", "读取文件", "schemas/read.schema.json"),
            installedDirectory,
            JsonSerializer.SerializeToElement(new { file = privateFile }));
        var fileDescriptor = input.GetProperty("file");
        Assert.False(fileDescriptor.TryGetProperty("path", out _));
        Assert.False(input.GetRawText().Contains(privateFile, StringComparison.OrdinalIgnoreCase));
        var digest = await broker.HandleAsync(
            PdppProtocol.HostFileDigestMethod,
            JsonSerializer.SerializeToElement(new
            {
                file_ref = fileDescriptor.GetProperty("file_ref").GetString(),
                algorithm = "sha256",
            }));
        Assert.Equal(
            Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(
                System.Text.Encoding.UTF8.GetBytes("synthetic broker content"))),
            digest.GetProperty("digest").GetString());

        var options = new PluginProcessStartOptions
        {
            PluginId = "synthetic.csharp",
            ExecutablePath = FindSyntheticPlugin(),
            WorkingDirectory = _workingDirectory,
            MemoryLimitBytes = 256L * 1024 * 1024,
            ActiveProcessLimit = 1,
        };
        await using var host = await PluginProcessHost.StartWithIsolationPolicyAsync(
            options,
            NoOpWindowsPluginIsolationPolicy.Instance,
            default,
            broker);
        await host.InitializeAsync("0.1.0", ["file:read:selected"], TimeSpan.FromSeconds(5));

        var result = await ExecuteAsync<SyntheticFileReadResult>(
            host,
            "host-file-read",
            input);

        Assert.Equal("synthetic broker content", result.Content);
        Assert.Equal("csharp", result.Language);
    }

    [Fact]
    public async Task HostBrokerEnforcesPrivateStorageCapability()
    {
        var paths = new PluginStoragePaths(Path.Combine(_workingDirectory, "private-storage-broker"));
        var storage = new PluginPrivateStorage(paths);
        using var allowed = new PluginHostBroker(
            "synthetic.csharp",
            "1.0.0",
            ["storage:private"],
            storage);
        using var denied = new PluginHostBroker(
            "synthetic.denied",
            "1.0.0",
            [],
            storage);

        var stored = await allowed.HandleAsync(
            "host/storage/set",
            JsonSerializer.SerializeToElement(new
            {
                key = "settings.current",
                value = new { enabled = true },
            }));
        var loaded = await allowed.HandleAsync(
            "host/storage/get",
            JsonSerializer.SerializeToElement(new { key = "settings.current" }));

        Assert.True(stored.GetProperty("stored").GetBoolean());
        Assert.True(loaded.GetProperty("found").GetBoolean());
        Assert.True(loaded.GetProperty("value").GetProperty("enabled").GetBoolean());
        var removed = await allowed.HandleAsync(
            PdppProtocol.HostStorageRemoveMethod,
            JsonSerializer.SerializeToElement(new { key = "settings.current" }));
        var missing = await allowed.HandleAsync(
            "host/storage/get",
            JsonSerializer.SerializeToElement(new { key = "settings.current" }));
        Assert.True(removed.GetProperty("removed").GetBoolean());
        Assert.False(missing.GetProperty("found").GetBoolean());
        var exception = await Assert.ThrowsAsync<PdppHostRequestException>(
            () => denied.HandleAsync(
                "host/storage/get",
                JsonSerializer.SerializeToElement(new { key = "settings.current" })));
        Assert.Equal(-32001, exception.Code);
    }

    [Fact]
    public async Task HostBrokerDelegatesPlatformApiWithoutReturningHostCredentials()
    {
        var paths = new PluginStoragePaths(Path.Combine(_workingDirectory, "api-broker-storage"));
        var api = new RecordingPluginApiBroker();
        using var allowed = new PluginHostBroker(
            "synthetic.market",
            "1.0.0",
            ["api:profile:read"],
            new PluginPrivateStorage(paths),
            api);
        using var denied = new PluginHostBroker(
            "synthetic.denied",
            "1.0.0",
            [],
            new PluginPrivateStorage(paths),
            api);

        var result = await allowed.HandleAsync(
            "host/api/profile/read",
            JsonSerializer.SerializeToElement(new { }));

        Assert.True(result.GetProperty("authorized").GetBoolean());
        Assert.Equal("synthetic.market", api.PluginSlug);
        Assert.Equal("api:profile:read", api.Capability);
        Assert.DoesNotContain("token", result.GetRawText(), StringComparison.OrdinalIgnoreCase);
        await Assert.ThrowsAsync<PdppHostRequestException>(
            () => denied.HandleAsync(
                "host/api/profile/read",
                JsonSerializer.SerializeToElement(new { })));
    }

    [Fact]
    public async Task HostBrokerAllowsOnlyGrantedPluginToApplyStructuredTheme()
    {
        var paths = new PluginStoragePaths(Path.Combine(_workingDirectory, "theme-broker-storage"));
        var theme = new RecordingThemeService();
        using var allowed = new PluginHostBroker(
            "official.theme",
            "1.0.0",
            ["ui:theme"],
            new PluginPrivateStorage(paths),
            themeService: theme);
        using var denied = new PluginHostBroker(
            "synthetic.denied",
            "1.0.0",
            [],
            new PluginPrivateStorage(paths),
            themeService: theme);

        var result = await allowed.HandleAsync(
            PdppProtocol.HostUiThemeApplyMethod,
            JsonSerializer.SerializeToElement(new { preset = "forest", background_opacity = 0.7 }));

        Assert.True(result.GetProperty("applied").GetBoolean());
        Assert.Equal("official.theme", theme.PluginId);
        Assert.Equal("forest", theme.Parameters.GetProperty("preset").GetString());
        var exception = await Assert.ThrowsAsync<PdppHostRequestException>(() => denied.HandleAsync(
            PdppProtocol.HostUiThemeApplyMethod,
            JsonSerializer.SerializeToElement(new { preset = "dark" })));
        Assert.Equal(-32001, exception.Code);
    }

    [Fact]
    public async Task HostBrokerAuthorizesIsolatedPluginOwnedWindowOnlyWithCapability()
    {
        var paths = new PluginStoragePaths(Path.Combine(_workingDirectory, "window-broker-storage"));
        using var allowed = new PluginHostBroker(
            "official.window",
            "1.0.0",
            ["ui:window"],
            new PluginPrivateStorage(paths));
        using var denied = new PluginHostBroker(
            "synthetic.denied",
            "1.0.0",
            [],
            new PluginPrivateStorage(paths));

        var result = await allowed.HandleAsync(
            PdppProtocol.HostUiWindowOpenMethod,
            JsonSerializer.SerializeToElement(new
            {
                window_id = "inspector",
                title = "合成窗口",
                width = 640,
                height = 480,
                modal = true,
            }));

        Assert.True(result.GetProperty("opened").GetBoolean());
        Assert.True(result.GetProperty("process_owned").GetBoolean());
        Assert.Equal("inspector", result.GetProperty("window_id").GetString());
        await Assert.ThrowsAsync<PdppHostRequestException>(() => denied.HandleAsync(
            PdppProtocol.HostUiWindowOpenMethod,
            JsonSerializer.SerializeToElement(new
            {
                window_id = "denied",
                title = "合成窗口",
                width = 640,
                height = 480,
            })));
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
        };
        return PluginProcessHost.StartWithIsolationPolicyAsync(
            options,
            NoOpWindowsPluginIsolationPolicy.Instance);
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
    private sealed record SyntheticFileReadResult(string Content, string Language);
    private sealed record SyntheticRegistryResult(bool RegistryWrite, string Language);

    private sealed class RecordingPluginApiBroker : IPluginApiBroker
    {
        public string PluginSlug { get; private set; } = string.Empty;
        public string Capability { get; private set; } = string.Empty;

        public Task<JsonElement> CallAsync(
            string pluginSlug,
            string pluginVersion,
            string capability,
            JsonElement parameters,
            CancellationToken cancellationToken = default)
        {
            PluginSlug = pluginSlug;
            Capability = capability;
            return Task.FromResult(JsonSerializer.SerializeToElement(new { authorized = true }));
        }
    }

    private sealed class RecordingThemeService : IPluginThemeService
    {
        public string PluginId { get; private set; } = string.Empty;
        public JsonElement Parameters { get; private set; }

        public string ImportBackground(string pluginId, string sourcePath) => "a".PadRight(32, 'a');

        public Task<JsonElement> ApplyAsync(
            string pluginId,
            JsonElement parameters,
            string? installedDirectory = null,
            CancellationToken cancellationToken = default)
        {
            PluginId = pluginId;
            Parameters = parameters.Clone();
            return Task.FromResult(JsonSerializer.SerializeToElement(new { applied = true }));
        }

        public Task ApplyPersistedAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
    }
}
