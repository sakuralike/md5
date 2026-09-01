using System.Diagnostics;
using System.IO;
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
