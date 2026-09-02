using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;

namespace PasswordDetective.Desktop.Plugins.Windows;

/// <summary>
/// JSON-RPC client for the standalone Pdpp Sandbox Core process.
/// </summary>
internal sealed class SandboxCoreClient : IAsyncDisposable
{
    private const int MaxMessageBytes = 1024 * 1024;
    private readonly Process _process;
    private readonly StreamWriter _input;
    private readonly StreamReader _output;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private long _nextId;
    private int _disposed;

    private SandboxCoreClient(Process process)
    {
        _process = process;
        _input = new StreamWriter(
            process.StandardInput.BaseStream,
            new UTF8Encoding(false),
            4096,
            leaveOpen: true)
        {
            AutoFlush = true,
            NewLine = "\n",
        };
        _output = new StreamReader(
            process.StandardOutput.BaseStream,
            new UTF8Encoding(false, true),
            detectEncodingFromByteOrderMarks: false,
            bufferSize: 4096,
            leaveOpen: true);
    }

    public int ProcessId => _process.Id;
    public string IntegrityLevel => "low";
    public bool HasExited => _process.HasExited;
    public int? ExitCode => _process.HasExited ? _process.ExitCode : null;

    public static SandboxCoreClient Start(string? executablePath = null)
    {
        if (!OperatingSystem.IsWindows())
        {
            throw new PlatformNotSupportedException("Pdpp Sandbox Core requires Windows.");
        }

        var path = ResolveExecutable(executablePath);
        var process = Process.Start(new ProcessStartInfo
        {
            FileName = path,
            WorkingDirectory = Path.GetDirectoryName(path)!,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        }) ?? throw new InvalidOperationException("Unable to start Pdpp Sandbox Core.");
        return new SandboxCoreClient(process);
    }

    public async Task<JsonDocument> InvokeAsync(
        string method,
        object parameters,
        TimeSpan timeout,
        CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
        if (string.IsNullOrWhiteSpace(method) || method.Length > 128)
        {
            throw new ArgumentException("Sandbox method is invalid.", nameof(method));
        }

        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var id = Interlocked.Increment(ref _nextId).ToString(
                System.Globalization.CultureInfo.InvariantCulture);
            var request = JsonSerializer.Serialize(new
            {
                jsonrpc = "2.0",
                id,
                method,
                @params = parameters,
            });
            if (Encoding.UTF8.GetByteCount(request) > MaxMessageBytes)
            {
                throw new InvalidOperationException("Sandbox request exceeds the 1 MiB limit.");
            }

            using var timeoutCancellation = new CancellationTokenSource(timeout);
            using var linked = CancellationTokenSource.CreateLinkedTokenSource(
                cancellationToken,
                timeoutCancellation.Token);
            await _input.WriteLineAsync(request.AsMemory(), linked.Token).ConfigureAwait(false);
            var line = await ReadBoundedLineAsync(linked.Token).ConfigureAwait(false)
                ?? throw new EndOfStreamException("Pdpp Sandbox Core exited unexpectedly.");
            if (Encoding.UTF8.GetByteCount(line) > MaxMessageBytes)
            {
                throw new InvalidDataException("Sandbox response exceeds the 1 MiB limit.");
            }

            var document = JsonDocument.Parse(line, new JsonDocumentOptions { MaxDepth = 32 });
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || !root.TryGetProperty("jsonrpc", out var jsonrpc)
                || jsonrpc.GetString() != "2.0"
                || !root.TryGetProperty("id", out var responseId)
                || responseId.GetString() != id)
            {
                document.Dispose();
                throw new InvalidDataException("Sandbox response envelope is invalid.");
            }

            if (root.TryGetProperty("error", out var error))
            {
                var code = error.TryGetProperty("code", out var codeValue)
                    ? codeValue.GetInt32()
                    : -32000;
                var message = error.TryGetProperty("message", out var messageValue)
                    ? messageValue.GetString() ?? "Sandbox request failed."
                    : "Sandbox request failed.";
                document.Dispose();
                throw new SandboxCoreException(code, message);
            }

            return document;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (Volatile.Read(ref _disposed) != 0)
        {
            return;
        }

        try
        {
            if (!_process.HasExited)
            {
                try
                {
                    await InvokeAsync("shutdown", new { }, TimeSpan.FromSeconds(2));
                }
                catch
                {
                    // Process cleanup below is authoritative.
                }
            }
        }
        finally
        {
            Interlocked.Exchange(ref _disposed, 1);
            _input.Dispose();
            _output.Dispose();
            if (!_process.HasExited)
            {
                _process.Kill(entireProcessTree: true);
            }
            await _process.WaitForExitAsync().ConfigureAwait(false);
            _process.Dispose();
            _gate.Dispose();
        }
    }

    private static string ResolveExecutable(string? executablePath)
    {
        var configured = executablePath
            ?? Environment.GetEnvironmentVariable("PDPP_SANDBOX_CORE_PATH");
        var path = string.IsNullOrWhiteSpace(configured)
            ? Path.Combine(AppContext.BaseDirectory, "pdpp-sandbox-core.exe")
            : configured;
        if (!Path.IsPathFullyQualified(path) || !File.Exists(path))
        {
            throw new FileNotFoundException("Pdpp Sandbox Core executable was not found.", path);
        }

        return Path.GetFullPath(path);
    }

    private async Task<string?> ReadBoundedLineAsync(CancellationToken cancellationToken)
    {
        var builder = new StringBuilder(capacity: 4096);
        var character = new char[1];
        while (true)
        {
            var read = await _output.ReadAsync(character.AsMemory(), cancellationToken)
                .ConfigureAwait(false);
            if (read == 0)
            {
                return builder.Length == 0 ? null : builder.ToString();
            }

            if (character[0] == '\n')
            {
                return builder.ToString();
            }

            if (character[0] == '\r')
            {
                continue;
            }

            if (builder.Length >= MaxMessageBytes)
            {
                throw new InvalidDataException("Sandbox response exceeds the 1 MiB limit.");
            }

            builder.Append(character[0]);
        }
    }
}

internal sealed class SandboxCoreException(int code, string message) : Exception(message)
{
    public int Code { get; } = code;
}

/// <summary>
/// Host.Sandbox boundary used by Host.UI. The channel intentionally owns only
/// plugin-scoped data and never receives the UI session store.
/// </summary>
internal sealed class HostSandboxProcess : IAsyncDisposable
{
    private readonly SandboxCoreClient _core;

    private HostSandboxProcess(SandboxCoreClient core) => _core = core;

    public int ProcessId => _core.ProcessId;
    public string IntegrityLevel => _core.IntegrityLevel;

    public static HostSandboxProcess Start(string? corePath = null) =>
        new(SandboxCoreClient.Start(corePath));

    public Task<JsonDocument> InvokeAsync(
        string method,
        object parameters,
        TimeSpan timeout,
        CancellationToken cancellationToken = default) =>
        _core.InvokeAsync(method, parameters, timeout, cancellationToken);

    public ValueTask DisposeAsync() => _core.DisposeAsync();
}

internal sealed class RustSandboxedProcess : ISandboxedProcess
{
    private readonly SandboxCoreClient _core;
    private readonly string _profileSid;
    private readonly string _jobHandle;
    private readonly NamedPipeServerStream _standardInputPipe;
    private readonly NamedPipeServerStream _standardOutputPipe;
    private readonly NamedPipeServerStream _standardErrorPipe;
    private int _disposed;

    private RustSandboxedProcess(
        SandboxCoreClient core,
        string profileSid,
        string jobHandle,
        NamedPipeServerStream standardInputPipe,
        NamedPipeServerStream standardOutputPipe,
        NamedPipeServerStream standardErrorPipe,
        bool isAppContainer,
        int processId)
    {
        _core = core;
        _profileSid = profileSid;
        _jobHandle = jobHandle;
        _standardInputPipe = standardInputPipe;
        _standardOutputPipe = standardOutputPipe;
        _standardErrorPipe = standardErrorPipe;
        IsAppContainer = isAppContainer;
        ProcessId = processId;
        StandardInput = standardInputPipe;
        StandardOutput = standardOutputPipe;
        StandardError = standardErrorPipe;
    }

    public int ProcessId { get; }
    public bool IsAppContainer { get; }
    public bool HasExited => _core.HasExited;
    public int? ExitCode => _core.ExitCode;
    public Stream StandardInput { get; }
    public Stream StandardOutput { get; }
    public Stream StandardError { get; }

    public static async Task<RustSandboxedProcess> StartAsync(
        PluginProcessStartOptions options,
        CancellationToken cancellationToken = default,
        bool verifyIsolationPolicies = true)
    {
        options.Validate();
        if (!OperatingSystem.IsWindows())
        {
            throw new PlatformNotSupportedException("Rust plugin sandbox requires Windows.");
        }

        var core = SandboxCoreClient.Start();
        NamedPipeServerStream? input = null;
        NamedPipeServerStream? output = null;
        NamedPipeServerStream? error = null;
        try
        {
            var workspaceRoot = Directory.GetParent(options.WorkingDirectory)?.FullName
                ?? options.WorkingDirectory;
            using var sandbox = await core.InvokeAsync(
                "sandbox.create",
                new
                {
                    plugin_id = options.PluginId,
                    workspace_root = workspaceRoot,
                    limits = new
                    {
                        memory_mb = Math.Max(32, checked((int)(options.MemoryLimitBytes / (1024 * 1024)))),
                        cpu_percent = options.CpuRatePercent,
                        command_timeout_seconds = 300,
                    },
                },
                TimeSpan.FromSeconds(15),
                cancellationToken).ConfigureAwait(false);
            var sandboxResult = sandbox.RootElement.GetProperty("result");
            var profileSid = sandboxResult.GetProperty("profile_sid").GetString()
                ?? throw new InvalidDataException("Rust sandbox did not return an AppContainer SID.");
            using var networkPolicy = verifyIsolationPolicies
                ? await core.InvokeAsync(
                "net.block_outbound",
                new { plugin_id = options.PluginId, appcontainer_sid = profileSid, action = "verify" },
                TimeSpan.FromSeconds(10),
                cancellationToken).ConfigureAwait(false)
                : null;
            using var registryPolicy = verifyIsolationPolicies
                ? await core.InvokeAsync(
                "reg.deny_write",
                new { plugin_id = options.PluginId, appcontainer_sid = profileSid, action = "verify" },
                TimeSpan.FromSeconds(10),
                cancellationToken).ConfigureAwait(false)
                : null;
            if (verifyIsolationPolicies)
            {
                if (networkPolicy is null
                    || registryPolicy is null
                    || !networkPolicy.RootElement.GetProperty("result").GetProperty("configured").GetBoolean()
                    || !registryPolicy.RootElement.GetProperty("result").GetProperty("configured").GetBoolean())
                {
                    throw new InvalidOperationException("Rust sandbox isolation policies are not configured.");
                }
            }

            var prefix = $"pdpp-{Environment.ProcessId}-{Guid.NewGuid():N}";
            input = CreatePipe($"{prefix}-stdin", PipeDirection.Out);
            output = CreatePipe($"{prefix}-stdout", PipeDirection.In);
            error = CreatePipe($"{prefix}-stderr", PipeDirection.In);
            using var spawned = await core.InvokeAsync(
                "process.spawn",
                new
                {
                    profile_sid = profileSid,
                    entrypoint = options.ExecutablePath,
                    working_directory = options.WorkingDirectory,
                    arguments = options.Arguments,
                    stdio_pipe_names = new
                    {
                        stdin = $"\\\\.\\pipe\\{prefix}-stdin",
                        stdout = $"\\\\.\\pipe\\{prefix}-stdout",
                        stderr = $"\\\\.\\pipe\\{prefix}-stderr",
                    },
                },
                TimeSpan.FromSeconds(15),
                cancellationToken).ConfigureAwait(false);
            var spawnResult = spawned.RootElement.GetProperty("result");
            var jobHandle = spawnResult.GetProperty("job_handle").GetString()
                ?? throw new InvalidDataException("Rust sandbox did not return a Job handle.");
            var processId = spawnResult.GetProperty("pid").GetInt32();
            var isAppContainer = spawnResult.GetProperty("is_appcontainer").GetBoolean();
            if (!isAppContainer)
            {
                throw new InvalidOperationException("Rust sandbox process did not enter AppContainer.");
            }

            await ConnectAsync(input, output, error, cancellationToken).ConfigureAwait(false);
            var result = new RustSandboxedProcess(
                core,
                profileSid,
                jobHandle,
                input,
                output,
                error,
                isAppContainer,
                processId);
            input = null;
            output = null;
            error = null;
            return result;
        }
        catch
        {
            input?.Dispose();
            output?.Dispose();
            error?.Dispose();
            await core.DisposeAsync().ConfigureAwait(false);
            throw;
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0)
        {
            return;
        }

        try
        {
            try
            {
                await _core.InvokeAsync(
                    "process.terminate",
                    new { job_handle = _jobHandle },
                    TimeSpan.FromSeconds(5)).ConfigureAwait(false);
            }
            catch (SandboxCoreException)
            {
            }

            try
            {
                await _core.InvokeAsync(
                    "sandbox.destroy",
                    new { profile_sid = _profileSid },
                    TimeSpan.FromSeconds(5)).ConfigureAwait(false);
            }
            catch (SandboxCoreException)
            {
            }
        }
        finally
        {
            _standardInputPipe.Dispose();
            _standardOutputPipe.Dispose();
            _standardErrorPipe.Dispose();
            await _core.DisposeAsync().ConfigureAwait(false);
        }
    }

    private static NamedPipeServerStream CreatePipe(string name, PipeDirection direction) =>
        new(
            name,
            direction,
            1,
            PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous | PipeOptions.WriteThrough,
            64 * 1024,
            64 * 1024);

    private static async Task ConnectAsync(
        NamedPipeServerStream input,
        NamedPipeServerStream output,
        NamedPipeServerStream error,
        CancellationToken cancellationToken)
    {
        await Task.WhenAll(
            input.WaitForConnectionAsync(cancellationToken),
            output.WaitForConnectionAsync(cancellationToken),
            error.WaitForConnectionAsync(cancellationToken)).ConfigureAwait(false);
    }
}
