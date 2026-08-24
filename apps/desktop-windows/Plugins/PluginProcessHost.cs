using System.IO;
using System.Text;
using System.Text.Json;
using PasswordDetective.Desktop.Plugins.Protocol;
using PasswordDetective.Desktop.Plugins.Windows;

namespace PasswordDetective.Desktop.Plugins;

public sealed class PluginProcessHost : IAsyncDisposable
{
    private readonly WindowsSandboxedProcess _sandboxedProcess;
    private readonly PluginProcessStartOptions _options;
    private readonly IPdppHostRequestHandler? _hostRequestHandler;
    private readonly Stream _output;
    private readonly StreamWriter _input;
    private readonly CancellationTokenSource _lifetime = new();
    private readonly SemaphoreSlim _requestLock = new(1, 1);
    private readonly Task _standardErrorTask;
    private readonly StringBuilder _standardError = new();
    private long _nextRequestId;
    private int _disposeStarted;

    private PluginProcessHost(
        WindowsSandboxedProcess sandboxedProcess,
        PluginProcessStartOptions options,
        IPdppHostRequestHandler? hostRequestHandler)
    {
        _sandboxedProcess = sandboxedProcess;
        _options = options;
        _hostRequestHandler = hostRequestHandler;
        _input = new StreamWriter(
            sandboxedProcess.StandardInput,
            new UTF8Encoding(encoderShouldEmitUTF8Identifier: false),
            bufferSize: 4096,
            leaveOpen: true)
        {
            AutoFlush = true,
            NewLine = "\n",
        };
        _output = sandboxedProcess.StandardOutput;
        _standardErrorTask = CaptureStandardErrorAsync();
    }

    public int ProcessId => _sandboxedProcess.ProcessId;
    public bool IsAppContainer => _sandboxedProcess.IsAppContainer;
    public bool HasExited => _sandboxedProcess.HasExited;
    public string StandardError
    {
        get
        {
            lock (_standardError)
            {
                return _standardError.ToString();
            }
        }
    }

    public static Task<PluginProcessHost> StartAsync(
        PluginProcessStartOptions options,
        CancellationToken cancellationToken = default,
        IPdppHostRequestHandler? hostRequestHandler = null)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var process = WindowsSandboxedProcess.Start(options);
        return Task.FromResult(new PluginProcessHost(process, options, hostRequestHandler));
    }

    public async Task<PdppInitializeResult> InitializeAsync(
        string hostVersion,
        IReadOnlyList<string> grantedCapabilities,
        TimeSpan timeout,
        CancellationToken cancellationToken = default)
    {
        var result = await InvokeAsync<PdppInitializeParams, PdppInitializeResult>(
            PdppProtocol.InitializeMethod,
            new PdppInitializeParams(
                PdppProtocol.ProtocolVersion,
                hostVersion,
                _options.PluginId,
                grantedCapabilities),
            timeout,
            cancellationToken);
        if (!string.Equals(result.ProtocolVersion, PdppProtocol.ProtocolVersion, StringComparison.Ordinal)
            || !string.Equals(result.PluginId, _options.PluginId, StringComparison.Ordinal))
        {
            await TerminateAsync();
            throw new PdppProtocolException("The plugin initialization identity or protocol version is invalid.");
        }

        return result;
    }

    public async Task<TResult> InvokeAsync<TParams, TResult>(
        string method,
        TParams parameters,
        TimeSpan timeout,
        CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposeStarted) != 0, this);
        if (string.IsNullOrWhiteSpace(method))
        {
            throw new ArgumentException("PDPP method is required.", nameof(method));
        }

        if (method is not (PdppProtocol.InitializeMethod
            or PdppProtocol.HealthCheckMethod
            or PdppProtocol.ExecuteCommandMethod
            or PdppProtocol.ShutdownMethod))
        {
            throw new ArgumentException("The PDPP method is not defined by protocol v1.", nameof(method));
        }

        if (timeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(timeout));
        }

        await _requestLock.WaitAsync(cancellationToken);
        try
        {
            ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposeStarted) != 0, this);
            if (_sandboxedProcess.HasExited)
            {
                throw CreateExitedException();
            }

            var requestId = Interlocked.Increment(ref _nextRequestId).ToString(System.Globalization.CultureInfo.InvariantCulture);
            var request = new PdppRequest<TParams>(
                PdppProtocol.JsonRpcVersion,
                requestId,
                method,
                parameters);
            var line = JsonSerializer.Serialize(request, PdppProtocol.SerializerOptions);
            if (Encoding.UTF8.GetByteCount(line) > _options.MaximumMessageBytes)
            {
                throw new PdppProtocolException("The PDPP request exceeds the configured message limit.");
            }

            using var timeoutCancellation = new CancellationTokenSource(timeout);
            using var linked = CancellationTokenSource.CreateLinkedTokenSource(
                cancellationToken,
                timeoutCancellation.Token,
                _lifetime.Token);
            var cancellationSignal = Task.Delay(Timeout.InfiniteTimeSpan, linked.Token);
            try
            {
                var write = _input.WriteLineAsync(line);
                if (await Task.WhenAny(write, cancellationSignal) != write)
                {
                    ObserveFault(write);
                    await ThrowAfterCancellationAsync(method, timeout, timeoutCancellation, cancellationToken);
                }

                await write;
                while (true)
                {
                    var read = ReadBoundedLineAsync();
                    if (await Task.WhenAny(read, cancellationSignal) != read)
                    {
                        ObserveFault(read);
                        await ThrowAfterCancellationAsync(method, timeout, timeoutCancellation, cancellationToken);
                    }

                    var responseLine = await read;
                    if (responseLine is null)
                    {
                        throw CreateExitedException();
                    }

                    if (Encoding.UTF8.GetByteCount(responseLine) > _options.MaximumMessageBytes)
                    {
                        throw new PdppProtocolException("The PDPP response exceeds the configured message limit.");
                    }

                    var hostRequest = ParseHostRequest(responseLine);
                    if (hostRequest is null)
                    {
                        return ParseResponse<TResult>(responseLine, requestId);
                    }

                    await RespondToHostRequestAsync(hostRequest, linked.Token);
                }
            }
            catch (OperationCanceledException) when (timeoutCancellation.IsCancellationRequested && !cancellationToken.IsCancellationRequested)
            {
                await TerminateAsync();
                throw new TimeoutException($"Plugin method '{method}' exceeded its {timeout.TotalMilliseconds:0} ms timeout.");
            }
            catch (OperationCanceledException)
            {
                await TerminateAsync();
                throw;
            }
            catch (PdppProtocolException)
            {
                await TerminateAsync();
                throw;
            }
            catch (IOException exception)
            {
                var processExited = _sandboxedProcess.HasExited;
                await TerminateAsync();
                if (processExited)
                {
                    throw CreateExitedException();
                }

                throw new PdppProtocolException("Plugin standard I/O failed.", exception);
            }
            finally
            {
                if (!linked.IsCancellationRequested)
                {
                    linked.Cancel();
                }
            }
        }
        finally
        {
            _requestLock.Release();
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref _disposeStarted, 1) != 0)
        {
            return;
        }

        _lifetime.Cancel();
        await _requestLock.WaitAsync();
        try
        {
            try
            {
                _input.Dispose();
            }
            catch (IOException)
            {
            }
            catch (ObjectDisposedException)
            {
            }

            await _sandboxedProcess.DisposeAsync();
            try
            {
                await _standardErrorTask;
            }
            catch (OperationCanceledException)
            {
            }
            catch (IOException)
            {
            }
            catch (ObjectDisposedException)
            {
            }
        }
        finally
        {
            _requestLock.Release();
            _lifetime.Dispose();
        }
    }

    private static TResult ParseResponse<TResult>(string responseLine, string requestId)
    {
        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(responseLine, new JsonDocumentOptions
            {
                AllowTrailingCommas = false,
                CommentHandling = JsonCommentHandling.Disallow,
                MaxDepth = 32,
            });
        }
        catch (JsonException exception)
        {
            throw new PdppProtocolException("The plugin returned invalid JSON.", exception);
        }

        using (document)
        {
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || !root.TryGetProperty("jsonrpc", out var jsonRpc)
                || jsonRpc.ValueKind != JsonValueKind.String
                || jsonRpc.GetString() != PdppProtocol.JsonRpcVersion
                || !root.TryGetProperty("id", out var id)
                || id.ValueKind != JsonValueKind.String
                || id.GetString() != requestId)
            {
                throw new PdppProtocolException("The plugin returned an invalid JSON-RPC envelope.");
            }

            var hasResult = root.TryGetProperty("result", out var result);
            var hasError = root.TryGetProperty("error", out var error);
            if (hasResult == hasError || root.EnumerateObject().Count() != 3)
            {
                throw new PdppProtocolException("The plugin response must contain exactly one result or error.");
            }

            if (hasError)
            {
                if (error.ValueKind != JsonValueKind.Object
                    || error.EnumerateObject().Any(property => property.Name is not ("code" or "message" or "data"))
                    || !error.TryGetProperty("code", out var code)
                    || !code.TryGetInt32(out var errorCode)
                    || !error.TryGetProperty("message", out var message)
                    || message.ValueKind != JsonValueKind.String
                    || string.IsNullOrWhiteSpace(message.GetString())
                    || message.GetString()!.Length > 1024)
                {
                    throw new PdppProtocolException("The plugin returned an invalid error object.");
                }

                throw new PdppRemoteException(errorCode, message.GetString()!);
            }

            try
            {
                return result.Deserialize<TResult>(PdppProtocol.SerializerOptions)
                    ?? throw new PdppProtocolException("The plugin returned a null result.");
            }
            catch (JsonException exception)
            {
                throw new PdppProtocolException("The plugin result does not match the expected contract.", exception);
            }
        }
    }

    private static PdppHostRequest? ParseHostRequest(string line)
    {
        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(line, new JsonDocumentOptions
            {
                AllowTrailingCommas = false,
                CommentHandling = JsonCommentHandling.Disallow,
                MaxDepth = 32,
            });
        }
        catch (JsonException exception)
        {
            throw new PdppProtocolException("The plugin returned invalid JSON.", exception);
        }

        using (document)
        {
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || !root.TryGetProperty("method", out var method))
            {
                return null;
            }

            if (root.EnumerateObject().Count() != 4
                || !root.TryGetProperty("jsonrpc", out var jsonRpc)
                || jsonRpc.ValueKind != JsonValueKind.String
                || jsonRpc.GetString() != PdppProtocol.JsonRpcVersion
                || !root.TryGetProperty("id", out var id)
                || id.ValueKind != JsonValueKind.String
                || string.IsNullOrWhiteSpace(id.GetString())
                || id.GetString()!.Length > 64
                || method.ValueKind != JsonValueKind.String
                || string.IsNullOrWhiteSpace(method.GetString())
                || method.GetString()!.Length > 128
                || !root.TryGetProperty("params", out var parameters)
                || parameters.ValueKind != JsonValueKind.Object)
            {
                throw new PdppProtocolException("The plugin returned an invalid host request envelope.");
            }

            return new PdppHostRequest(id.GetString()!, method.GetString()!, parameters.Clone());
        }
    }

    private async Task RespondToHostRequestAsync(
        PdppHostRequest request,
        CancellationToken cancellationToken)
    {
        object response;
        try
        {
            if (_hostRequestHandler is null)
            {
                throw new PdppHostRequestException(-32601, "Host method is unavailable.");
            }

            var result = await _hostRequestHandler.HandleAsync(
                request.Method,
                request.Params,
                cancellationToken);
            response = new
            {
                jsonrpc = PdppProtocol.JsonRpcVersion,
                id = request.Id,
                result,
            };
        }
        catch (PdppHostRequestException exception)
        {
            response = new
            {
                jsonrpc = PdppProtocol.JsonRpcVersion,
                id = request.Id,
                error = new { code = exception.Code, message = exception.Message },
            };
        }

        var line = JsonSerializer.Serialize(response, PdppProtocol.SerializerOptions);
        if (Encoding.UTF8.GetByteCount(line) > _options.MaximumMessageBytes)
        {
            throw new PdppProtocolException("The host response exceeds the configured message limit.");
        }

        await _input.WriteLineAsync(line.AsMemory(), cancellationToken);
    }

    private async Task CaptureStandardErrorAsync()
    {
        var buffer = new byte[1024];
        while (!_lifetime.IsCancellationRequested)
        {
            var read = await _sandboxedProcess.StandardError.ReadAsync(buffer, _lifetime.Token);
            if (read == 0)
            {
                return;
            }

            lock (_standardError)
            {
                var remaining = _options.MaximumStandardErrorBytes - Encoding.UTF8.GetByteCount(_standardError.ToString());
                if (remaining <= 0)
                {
                    continue;
                }

                _standardError.Append(Encoding.UTF8.GetString(buffer, 0, Math.Min(read, remaining)));
            }
        }
    }

    private Task<string?> ReadBoundedLineAsync()
    {
        return Task.Run(() =>
        {
            using var buffer = new MemoryStream(capacity: Math.Min(_options.MaximumMessageBytes, 64 * 1024));
            while (true)
            {
                var value = _output.ReadByte();
                if (value < 0)
                {
                    return buffer.Length == 0 ? null : DecodeUtf8(buffer);
                }

                if (value == '\n')
                {
                    return DecodeUtf8(buffer);
                }

                if (value == '\r')
                {
                    continue;
                }

                if (buffer.Length >= _options.MaximumMessageBytes)
                {
                    throw new PdppProtocolException("The PDPP response exceeds the configured message limit.");
                }

                buffer.WriteByte((byte)value);
            }
        });
    }

    private static string DecodeUtf8(MemoryStream buffer)
    {
        try
        {
            return new UTF8Encoding(
                encoderShouldEmitUTF8Identifier: false,
                throwOnInvalidBytes: true).GetString(buffer.GetBuffer(), 0, checked((int)buffer.Length));
        }
        catch (DecoderFallbackException exception)
        {
            throw new PdppProtocolException("The plugin returned invalid UTF-8.", exception);
        }
    }

    private async Task TerminateAsync()
    {
        await _sandboxedProcess.DisposeAsync();
    }

    private async Task ThrowAfterCancellationAsync(
        string method,
        TimeSpan timeout,
        CancellationTokenSource timeoutCancellation,
        CancellationToken callerCancellation)
    {
        await TerminateAsync();
        callerCancellation.ThrowIfCancellationRequested();
        if (_lifetime.IsCancellationRequested)
        {
            throw new OperationCanceledException(_lifetime.Token);
        }

        if (timeoutCancellation.IsCancellationRequested)
        {
            throw new TimeoutException($"Plugin method '{method}' exceeded its {timeout.TotalMilliseconds:0} ms timeout.");
        }

        throw new OperationCanceledException();
    }

    private PdppProcessExitedException CreateExitedException()
    {
        return new PdppProcessExitedException(_sandboxedProcess.ExitCode, StandardError);
    }

    private static void ObserveFault(Task task)
    {
        _ = task.ContinueWith(
            completed => _ = completed.Exception,
            CancellationToken.None,
            TaskContinuationOptions.ExecuteSynchronously | TaskContinuationOptions.OnlyOnFaulted,
            TaskScheduler.Default);
    }
}

public class PdppProtocolException : Exception
{
    public PdppProtocolException(string message) : base(message)
    {
    }

    public PdppProtocolException(string message, Exception innerException) : base(message, innerException)
    {
    }
}

public sealed class PdppRemoteException : PdppProtocolException
{
    public PdppRemoteException(int code, string message) : base(message) => Code = code;
    public int Code { get; }
}

public sealed class PdppProcessExitedException : PdppProtocolException
{
    public PdppProcessExitedException(int? exitCode, string standardError)
        : base(exitCode.HasValue
            ? $"The plugin process exited with code {exitCode.Value}."
            : "The plugin process exited before returning a response.")
    {
        ExitCode = exitCode;
        StandardError = standardError;
    }

    public int? ExitCode { get; }
    public string StandardError { get; }
}

public sealed class PdppHostRequestException : Exception
{
    public PdppHostRequestException(int code, string message) : base(message) => Code = code;
    public int Code { get; }
}
