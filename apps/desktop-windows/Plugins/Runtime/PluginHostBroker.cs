using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Protocol;
using PasswordDetective.Desktop.Plugins.Storage;

namespace PasswordDetective.Desktop.Plugins.Runtime;

public sealed class PluginHostBroker : IPdppHostRequestHandler, IDisposable
{
    public const int MaximumFileChunkBytes = 512 * 1024;

    private readonly string _pluginId;
    private readonly string _pluginVersion;
    private readonly IReadOnlySet<string> _capabilities;
    private readonly PluginFileBroker _files = new(maximumChunkBytes: MaximumFileChunkBytes);
    private readonly PluginPrivateStorage _storage;
    private readonly IPluginApiBroker? _apiBroker;
    private bool _disposed;

    public PluginHostBroker(
        string pluginId,
        string pluginVersion,
        IEnumerable<string> capabilities,
        PluginPrivateStorage storage,
        IPluginApiBroker? apiBroker = null)
    {
        _pluginId = pluginId;
        _pluginVersion = pluginVersion;
        _capabilities = capabilities.ToHashSet(StringComparer.Ordinal);
        _storage = storage;
        _apiBroker = apiBroker;
    }

    public JsonElement PrepareCommandInput(
        PluginCommandManifest command,
        string installedDirectory,
        JsonElement input)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        if (input.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidOperationException("插件命令输入必须是对象。");
        }

        var schemaPath = ResolveContainedPath(installedDirectory, command.InputSchema);
        using var schemaDocument = JsonDocument.Parse(File.ReadAllText(schemaPath), new JsonDocumentOptions
        {
            AllowTrailingCommas = false,
            CommentHandling = JsonCommentHandling.Disallow,
            MaxDepth = 32,
        });
        var schema = schemaDocument.RootElement;
        if (!schema.TryGetProperty("properties", out var properties)
            || properties.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidOperationException("插件命令 Schema 缺少 properties。");
        }

        var allowed = properties.EnumerateObject()
            .Select(property => property.Name)
            .ToHashSet(StringComparer.Ordinal);
        if (input.EnumerateObject().Any(property => !allowed.Contains(property.Name)))
        {
            throw new InvalidOperationException("插件命令输入包含未声明字段。");
        }

        var output = JsonNode.Parse(input.GetRawText())?.AsObject()
            ?? throw new InvalidOperationException("插件命令输入无效。");
        foreach (var property in properties.EnumerateObject())
        {
            if (!property.Value.TryGetProperty("format", out var format))
            {
                continue;
            }

            if (format.GetString() == "directory")
            {
                throw new InvalidOperationException("v1 不向插件授予目录枚举能力。");
            }

            if (format.GetString() != "file")
            {
                continue;
            }

            EnsureCapability("file:read:selected");
            if (!input.TryGetProperty(property.Name, out var pathElement)
                || pathElement.ValueKind != JsonValueKind.String
                || string.IsNullOrWhiteSpace(pathElement.GetString()))
            {
                throw new InvalidOperationException($"文件字段 {property.Name} 未选择文件。");
            }

            var grant = _files.GrantRead(pathElement.GetString()!);
            output[property.Name] = JsonSerializer.SerializeToNode(new
            {
                file_ref = grant.GrantId.ToString("N"),
                file_name = grant.FileName,
                length = grant.Length,
            });
        }

        return JsonSerializer.SerializeToElement(output);
    }

    public Task<JsonElement> HandleAsync(
        string method,
        JsonElement parameters,
        CancellationToken cancellationToken = default) => method switch
        {
            "host/file/read" => ReadFileAsync(parameters, cancellationToken),
            "host/storage/get" => GetStorageAsync(parameters, cancellationToken),
            "host/storage/set" => SetStorageAsync(parameters, cancellationToken),
            PdppProtocol.HostApiProfileReadMethod => CallApiAsync("api:profile:read", parameters, cancellationToken),
            PdppProtocol.HostApiHashReadMethod => CallApiAsync("api:hash:read", parameters, cancellationToken),
            PdppProtocol.HostApiVerificationSubmitMethod => CallApiAsync("api:verification:submit", parameters, cancellationToken),
            _ => Task.FromException<JsonElement>(
                new PdppHostRequestException(-32601, "Host method is not supported.")),
        };

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _files.Dispose();
    }

    private async Task<JsonElement> ReadFileAsync(
        JsonElement parameters,
        CancellationToken cancellationToken)
    {
        EnsureCapability("file:read:selected");
        if (!parameters.TryGetProperty("file_ref", out var reference)
            || reference.ValueKind != JsonValueKind.String
            || !Guid.TryParseExact(reference.GetString(), "N", out var grantId)
            || !parameters.TryGetProperty("offset", out var offsetElement)
            || !offsetElement.TryGetInt64(out var offset)
            || !parameters.TryGetProperty("count", out var countElement)
            || !countElement.TryGetInt32(out var count)
            || count is < 1 or > MaximumFileChunkBytes)
        {
            throw new PdppHostRequestException(-32602, "File read parameters are invalid.");
        }

        try
        {
            var bytes = await _files.ReadAsync(grantId, offset, count, cancellationToken);
            return JsonSerializer.SerializeToElement(new
            {
                data_base64 = Convert.ToBase64String(bytes),
                bytes_read = bytes.Length,
                eof = bytes.Length < count,
            });
        }
        catch (Exception exception) when (exception is UnauthorizedAccessException or ArgumentOutOfRangeException)
        {
            throw new PdppHostRequestException(-32602, "File grant is missing, revoked, or out of range.");
        }
    }

    private async Task<JsonElement> GetStorageAsync(
        JsonElement parameters,
        CancellationToken cancellationToken)
    {
        EnsureCapability("storage:private");
        var key = ReadStorageKey(parameters);
        try
        {
            var value = await _storage.GetAsync(_pluginId, key, cancellationToken);
            return value.HasValue
                ? JsonSerializer.SerializeToElement(new { found = true, value = value.Value })
                : JsonSerializer.SerializeToElement(new { found = false });
        }
        catch (ArgumentException)
        {
            throw new PdppHostRequestException(-32602, "Storage key is invalid.");
        }
    }

    private async Task<JsonElement> SetStorageAsync(
        JsonElement parameters,
        CancellationToken cancellationToken)
    {
        EnsureCapability("storage:private");
        var key = ReadStorageKey(parameters);
        if (!parameters.TryGetProperty("value", out var value))
        {
            throw new PdppHostRequestException(-32602, "Storage value is required.");
        }

        try
        {
            await _storage.SetAsync(_pluginId, key, value.Clone(), cancellationToken);
            return JsonSerializer.SerializeToElement(new { stored = true });
        }
        catch (ArgumentException)
        {
            throw new PdppHostRequestException(-32602, "Storage key is invalid.");
        }
        catch (InvalidOperationException)
        {
            throw new PdppHostRequestException(-32002, "Storage quota or value limit was exceeded.");
        }
    }

    private void EnsureCapability(string capability)
    {
        if (!_capabilities.Contains(capability))
        {
            throw new PdppHostRequestException(-32001, $"Capability {capability} is not granted.");
        }
    }

    private Task<JsonElement> CallApiAsync(
        string capability,
        JsonElement parameters,
        CancellationToken cancellationToken)
    {
        EnsureCapability(capability);
        if (_apiBroker is null)
        {
            return Task.FromException<JsonElement>(
                new PdppHostRequestException(-32003, "插件平台 API Broker 当前不可用。"));
        }

        return _apiBroker.CallAsync(
            _pluginId,
            _pluginVersion,
            capability,
            parameters,
            cancellationToken);
    }

    private static string ReadStorageKey(JsonElement parameters)
    {
        if (!parameters.TryGetProperty("key", out var key)
            || key.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(key.GetString()))
        {
            throw new PdppHostRequestException(-32602, "Storage key is required.");
        }

        return key.GetString()!;
    }

    private static string ResolveContainedPath(string root, string relativePath)
    {
        var normalized = PluginPackageVerifier.NormalizeManifestPath(relativePath, "命令输入 Schema");
        var fullRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar)
            + Path.DirectorySeparatorChar;
        var fullPath = Path.GetFullPath(Path.Combine(root, normalized.Replace('/', Path.DirectorySeparatorChar)));
        if (!fullPath.StartsWith(fullRoot, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("插件命令 Schema 逃逸安装目录。");
        }

        return fullPath;
    }
}
