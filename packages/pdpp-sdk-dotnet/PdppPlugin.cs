using System.Text.Json;

namespace PasswordDetective.Pdpp;

public sealed class PdppHostException(int code, string message) : Exception(message)
{
    public int Code { get; } = code;
}

public sealed class PdppHostClient
{
    private readonly TextReader _input;
    private readonly TextWriter _output;
    private int _requestNumber;

    internal PdppHostClient(TextReader input, TextWriter output)
    {
        _input = input;
        _output = output;
    }

    public async Task<JsonElement> ApplyThemeAsync(
        string preset,
        string? backgroundReference,
        double backgroundOpacity,
        bool clearBackground,
        bool useDefaultBackground = false,
        CancellationToken cancellationToken = default)
    {
        var payload = new Dictionary<string, object?>
        {
            ["preset"] = preset,
            ["background_opacity"] = backgroundOpacity,
            ["clear_background"] = clearBackground,
            ["use_default_background"] = useDefaultBackground,
        };
        if (!string.IsNullOrWhiteSpace(backgroundReference))
        {
            payload["background_ref"] = backgroundReference;
        }

        return await CallAsync("host/ui/theme/apply", payload, cancellationToken);
    }

    public async Task<PluginFileReadResult> ReadFileAsync(
        string fileReference,
        long offset,
        int count,
        CancellationToken cancellationToken = default)
    {
        var result = await CallAsync(
            "host/file/read",
            new { file_ref = fileReference, offset, count },
            cancellationToken);
        return result.Deserialize<PluginFileReadResult>(PdppJson.Options)
            ?? throw new InvalidOperationException("宿主返回了无效的文件读取结果。");
    }

    public async Task<PluginFileDigestResult> DigestFileAsync(
        string fileReference,
        string algorithm,
        CancellationToken cancellationToken = default)
    {
        var result = await CallAsync(
            "host/file/digest",
            new { file_ref = fileReference, algorithm },
            cancellationToken);
        return result.Deserialize<PluginFileDigestResult>(PdppJson.Options)
            ?? throw new InvalidOperationException("宿主返回了无效的文件摘要结果。");
    }

    public async Task<byte[]> ReadFileToEndAsync(
        PluginSelectedFile file,
        long maximumBytes,
        CancellationToken cancellationToken = default)
    {
        if (file.Length is < 0 || file.Length > maximumBytes || file.Length > int.MaxValue)
        {
            throw new InvalidOperationException("所选文件超过插件允许的读取大小。");
        }

        var output = GC.AllocateUninitializedArray<byte>((int)file.Length);
        long offset = 0;
        while (offset < file.Length)
        {
            var chunk = await ReadFileAsync(
                file.FileRef,
                offset,
                (int)Math.Min(512 * 1024, file.Length - offset),
                cancellationToken);
            var bytes = Convert.FromBase64String(chunk.DataBase64);
            if (bytes.Length != chunk.BytesRead || bytes.Length == 0)
            {
                throw new InvalidOperationException("宿主返回的文件分块无效。");
            }

            bytes.CopyTo(output, (int)offset);
            offset += bytes.Length;
        }

        return output;
    }

    public async Task<JsonElement?> GetStorageAsync(
        string key,
        CancellationToken cancellationToken = default)
    {
        var result = await CallAsync("host/storage/get", new { key }, cancellationToken);
        return result.GetProperty("found").GetBoolean()
            ? result.GetProperty("value").Clone()
            : null;
    }

    public async Task SetStorageAsync(
        string key,
        object value,
        CancellationToken cancellationToken = default)
    {
        var result = await CallAsync("host/storage/set", new { key, value }, cancellationToken);
        if (!result.GetProperty("stored").GetBoolean())
        {
            throw new InvalidOperationException("宿主未保存插件私有数据。");
        }
    }

    public async Task<bool> RemoveStorageAsync(
        string key,
        CancellationToken cancellationToken = default)
    {
        var result = await CallAsync("host/storage/remove", new { key }, cancellationToken);
        return result.GetProperty("removed").GetBoolean();
    }

    public Task<JsonElement> ReadProfileAsync(CancellationToken cancellationToken = default) =>
        CallAsync("host/api/profile/read", new { }, cancellationToken);

    public Task<JsonElement> ReadHashAsync(
        string algorithm,
        string digest,
        CancellationToken cancellationToken = default) =>
        CallAsync("host/api/hash/read", new { algorithm, digest }, cancellationToken);

    public Task<JsonElement> SubmitVerificationAsync(
        PluginVerificationSubmission submission,
        CancellationToken cancellationToken = default) =>
        CallAsync("host/api/verification/submit", submission, cancellationToken);

    public async Task<JsonElement> CallAsync(
        string method,
        object parameters,
        CancellationToken cancellationToken = default)
    {
        var id = $"plugin-host-{Interlocked.Increment(ref _requestNumber)}";
        await WriteAsync(new { jsonrpc = "2.0", id, method, @params = parameters }, cancellationToken);
        var line = await _input.ReadLineAsync(cancellationToken)
            ?? throw new IOException("宿主在 Broker 响应前关闭了标准输入。");
        using var response = JsonDocument.Parse(line);
        var root = response.RootElement;
        if (!root.TryGetProperty("id", out var responseId)
            || !string.Equals(responseId.GetString(), id, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("宿主返回了不匹配的 Broker 响应。");
        }
        if (root.TryGetProperty("error", out var error))
        {
            throw new PdppHostException(
                error.GetProperty("code").GetInt32(),
                error.GetProperty("message").GetString() ?? "宿主 Broker 请求失败。");
        }

        return root.GetProperty("result").Clone();
    }

    internal async Task WriteAsync(object value, CancellationToken cancellationToken)
    {
        await _output.WriteLineAsync(JsonSerializer.Serialize(value, PdppJson.Options).AsMemory(), cancellationToken);
        await _output.FlushAsync(cancellationToken);
    }
}

public sealed record PluginFileReadResult(
    string DataBase64,
    int BytesRead,
    bool Eof);

public sealed record PluginFileDigestResult(
    string Algorithm,
    string Digest);

public sealed record PluginSelectedFile(
    string FileRef,
    string FileName,
    long Length)
{
    public static PluginSelectedFile FromJson(JsonElement element)
    {
        var file = element.Deserialize<PluginSelectedFile>(PdppJson.Options);
        if (file is null
            || file.FileRef.Length != 32
            || file.FileRef.Any(character => !Uri.IsHexDigit(character))
            || string.IsNullOrWhiteSpace(file.FileName)
            || file.Length < 0)
        {
            throw new InvalidOperationException("宿主提供的所选文件描述无效。");
        }
        return file;
    }
}

public sealed record PluginVerificationSubmission(
    string CandidateId,
    string FingerprintAlgorithm,
    string FingerprintDigest,
    string CandidateDigest,
    string Outcome,
    string ArchiveFormat);

public abstract class PdppPlugin
{
    protected PdppPlugin(string pluginId, string pluginVersion, IReadOnlyList<string> capabilities)
    {
        PluginId = pluginId;
        PluginVersion = pluginVersion;
        Capabilities = capabilities;
    }

    protected string PluginId { get; }
    protected string PluginVersion { get; }
    protected IReadOnlyList<string> Capabilities { get; }

    public async Task RunAsync(CancellationToken cancellationToken = default)
    {
        var host = new PdppHostClient(Console.In, Console.Out);
        while (await Console.In.ReadLineAsync(cancellationToken) is { } line)
        {
            using var request = JsonDocument.Parse(line);
            var root = request.RootElement;
            var id = root.GetProperty("id").GetString() ?? throw new InvalidOperationException("PDPP 请求缺少 ID。");
            var method = root.GetProperty("method").GetString();
            var parameters = root.GetProperty("params").Clone();
            try
            {
                switch (method)
                {
                    case "initialize":
                        await host.WriteAsync(new
                        {
                            jsonrpc = "2.0",
                            id,
                            result = new
                            {
                                protocol_version = "1.0",
                                plugin_id = PluginId,
                                plugin_version = PluginVersion,
                                capabilities = Capabilities,
                            },
                        }, cancellationToken);
                        break;
                    case "health/check":
                        await host.WriteAsync(new { jsonrpc = "2.0", id, result = new { status = "healthy" } }, cancellationToken);
                        break;
                    case "command/execute":
                        await host.WriteAsync(new
                        {
                            jsonrpc = "2.0",
                            id,
                            result = await ExecuteAsync(
                                parameters.GetProperty("command").GetString() ?? string.Empty,
                                parameters.GetProperty("input").Clone(),
                                host,
                                cancellationToken),
                        }, cancellationToken);
                        break;
                    case "shutdown":
                        await host.WriteAsync(new { jsonrpc = "2.0", id, result = new { stopped = true } }, cancellationToken);
                        return;
                    default:
                        await WriteErrorAsync(host, id, -32601, "Method not found", cancellationToken);
                        break;
                }
            }
            catch (PdppHostException exception)
            {
                await WriteErrorAsync(host, id, exception.Code, exception.Message, cancellationToken);
            }
            catch (Exception)
            {
                await WriteErrorAsync(host, id, -32603, "插件命令执行失败。", cancellationToken);
            }
        }
    }

    protected abstract Task<object> ExecuteAsync(
        string command,
        JsonElement input,
        PdppHostClient host,
        CancellationToken cancellationToken);

    private static Task WriteErrorAsync(
        PdppHostClient host,
        string id,
        int code,
        string message,
        CancellationToken cancellationToken) =>
        host.WriteAsync(new { jsonrpc = "2.0", id, error = new { code, message } }, cancellationToken);
}

internal static class PdppJson
{
    public static JsonSerializerOptions Options { get; } = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
    };
}
