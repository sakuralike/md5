using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Protocol;
using PasswordDetective.Desktop.Plugins.Storage;
using PasswordDetective.Desktop.Plugins.Theme;
using PasswordDetective.Desktop.Plugins.UI;

namespace PasswordDetective.Desktop.Plugins.Runtime;

public sealed class PluginHostBroker : IPdppHostRequestHandler, IDisposable
{
    public const int MaximumFileChunkBytes = 512 * 1024;

    private readonly string _pluginId;
    private readonly string _pluginVersion;
    private readonly string? _installedDirectory;
    private readonly IReadOnlySet<string> _capabilities;
    private readonly PluginFileBroker _files = new(maximumChunkBytes: MaximumFileChunkBytes);
    private readonly PluginPrivateStorage _storage;
    private readonly IPluginApiBroker? _apiBroker;
    private readonly IPluginThemeService? _themeService;
    private readonly IPluginPanelHost? _panelHost;
    private bool _disposed;
    private static readonly Regex PanelIdPattern = new(
        "^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);

    public PluginHostBroker(
        string pluginId,
        string pluginVersion,
        IEnumerable<string> capabilities,
        PluginPrivateStorage storage,
        IPluginApiBroker? apiBroker = null,
        IPluginThemeService? themeService = null,
        string? installedDirectory = null,
        IPluginPanelHost? panelHost = null)
    {
        _pluginId = pluginId;
        _pluginVersion = pluginVersion;
        _capabilities = capabilities.ToHashSet(StringComparer.Ordinal);
        _storage = storage;
        _apiBroker = apiBroker;
        _themeService = themeService;
        _installedDirectory = installedDirectory;
        _panelHost = panelHost;
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

            if (format.GetString() == "theme-background")
            {
                EnsureCapability("ui:theme");
                if (!input.TryGetProperty(property.Name, out var backgroundPathElement)
                    || backgroundPathElement.ValueKind != JsonValueKind.String
                    || string.IsNullOrWhiteSpace(backgroundPathElement.GetString()))
                {
                    output.Remove(property.Name);
                    continue;
                }

                if (_themeService is null)
                {
                    throw new InvalidOperationException("当前桌面端不支持主题背景。 ");
                }

                output[property.Name] = JsonSerializer.SerializeToNode(new
                {
                    background_ref = _themeService.ImportBackground(_pluginId, backgroundPathElement.GetString()!),
                });
                continue;
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
            "host/file/digest" => DigestFileAsync(parameters, cancellationToken),
            "host/storage/get" => GetStorageAsync(parameters, cancellationToken),
            "host/storage/set" => SetStorageAsync(parameters, cancellationToken),
            "host/storage/remove" => RemoveStorageAsync(parameters, cancellationToken),
            PdppProtocol.HostApiProfileReadMethod => CallApiAsync("api:profile:read", parameters, cancellationToken),
            PdppProtocol.HostApiHashReadMethod => CallApiAsync("api:hash:read", parameters, cancellationToken),
            PdppProtocol.HostApiVerificationSubmitMethod => CallApiAsync("api:verification:submit", parameters, cancellationToken),
            PdppProtocol.HostUiThemeApplyMethod => ApplyThemeAsync(parameters, cancellationToken),
            PdppProtocol.HostUiWindowOpenMethod => OpenWindowAsync(parameters, cancellationToken),
            PdppProtocol.HostUiPanelShowMethod => ShowPanelAsync(parameters, cancellationToken),
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

    private async Task<JsonElement> DigestFileAsync(
        JsonElement parameters,
        CancellationToken cancellationToken)
    {
        EnsureCapability("file:read:selected");
        if (!TryReadFileReference(parameters, out var grantId)
            || !parameters.TryGetProperty("algorithm", out var algorithmElement)
            || algorithmElement.ValueKind != JsonValueKind.String
            || algorithmElement.GetString() is not ("md5" or "sha1" or "sha256" or "sha512"))
        {
            throw new PdppHostRequestException(-32602, "File digest parameters are invalid.");
        }

        try
        {
            var algorithm = algorithmElement.GetString()!;
            var digest = await _files.DigestAsync(grantId, algorithm, cancellationToken);
            return JsonSerializer.SerializeToElement(new
            {
                algorithm,
                digest,
            });
        }
        catch (Exception exception) when (exception is UnauthorizedAccessException or ArgumentException or IOException)
        {
            throw new PdppHostRequestException(-32602, "File grant is missing, revoked, or unreadable.");
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

    private Task<JsonElement> RemoveStorageAsync(
        JsonElement parameters,
        CancellationToken cancellationToken)
    {
        EnsureCapability("storage:private");
        var key = ReadStorageKey(parameters);
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            return Task.FromResult(JsonSerializer.SerializeToElement(new
            {
                removed = _storage.Remove(_pluginId, key),
            }));
        }
        catch (ArgumentException)
        {
            throw new PdppHostRequestException(-32602, "Storage key is invalid.");
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

    private Task<JsonElement> ApplyThemeAsync(JsonElement parameters, CancellationToken cancellationToken)
    {
        EnsureCapability("ui:theme");
        if (_themeService is null)
        {
            return Task.FromException<JsonElement>(
                new PdppHostRequestException(-32003, "主题宿主能力当前不可用。"));
        }

        return _themeService.ApplyAsync(_pluginId, parameters, _installedDirectory, cancellationToken);
    }

    private Task<JsonElement> OpenWindowAsync(
        JsonElement parameters,
        CancellationToken cancellationToken)
    {
        EnsureCapability("ui:window");
        cancellationToken.ThrowIfCancellationRequested();
        if (parameters.ValueKind != JsonValueKind.Object
            || !parameters.TryGetProperty("window_id", out var idElement)
            || idElement.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(idElement.GetString())
            || idElement.GetString()!.Length > 64
            || !parameters.TryGetProperty("title", out var titleElement)
            || titleElement.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(titleElement.GetString())
            || titleElement.GetString()!.Length > 120
            || !parameters.TryGetProperty("width", out var widthElement)
            || !widthElement.TryGetDouble(out var width)
            || width is < 320 or > 1920
            || !parameters.TryGetProperty("height", out var heightElement)
            || !heightElement.TryGetDouble(out var height)
            || height is < 240 or > 1200
            || parameters.TryGetProperty("modal", out var modalElement)
                && modalElement.ValueKind is not JsonValueKind.True and not JsonValueKind.False)
        {
            throw new PdppHostRequestException(-32602, "窗口参数无效。窗口尺寸必须在 320x240 到 1920x1200 之间。");
        }

        return Task.FromResult(JsonSerializer.SerializeToElement(new
        {
            opened = true,
            window_id = idElement.GetString(),
            title = titleElement.GetString(),
            width,
            height,
            modal = modalElement.ValueKind == JsonValueKind.True,
            process_owned = true,
        }));
    }

    private async Task<JsonElement> ShowPanelAsync(
        JsonElement parameters,
        CancellationToken cancellationToken)
    {
        EnsureCapability("ui:panel");
        if (_panelHost is null)
        {
            throw new PdppHostRequestException(-32003, "声明式面板宿主当前不可用。");
        }

        var descriptor = ParsePanelDescriptor(parameters);
        return await _panelHost.ShowAsync(_pluginId, descriptor, cancellationToken);
    }

    private static PluginPanelDescriptor ParsePanelDescriptor(JsonElement parameters)
    {
        if (parameters.ValueKind != JsonValueKind.Object
            || parameters.EnumerateObject().Any(property => property.Name is not
                ("panel_id" or "title" or "width" or "height" or "controls")))
        {
            throw new PdppHostRequestException(-32602, "面板参数包含未知字段。");
        }

        var panelId = parameters.TryGetProperty("panel_id", out var idElement)
            && idElement.ValueKind == JsonValueKind.String
            ? idElement.GetString()
            : null;
        var title = parameters.TryGetProperty("title", out var titleElement)
            && titleElement.ValueKind == JsonValueKind.String
            ? titleElement.GetString()
            : null;
        if (string.IsNullOrWhiteSpace(panelId)
            || panelId.Length > 64
            || !PanelIdPattern.IsMatch(panelId)
            || string.IsNullOrWhiteSpace(title)
            || title.Length > 120)
        {
            throw new PdppHostRequestException(-32602, "面板 ID 或标题无效。");
        }

        var width = ReadPanelDimension(parameters, "width", 640, 320, 1920);
        var height = ReadPanelDimension(parameters, "height", 480, 240, 1200);
        if (!parameters.TryGetProperty("controls", out var controlsElement)
            || controlsElement.ValueKind != JsonValueKind.Array
            || controlsElement.GetArrayLength() is < 1 or > 32)
        {
            throw new PdppHostRequestException(-32602, "面板必须包含 1 到 32 个控件。");
        }

        var controls = new List<PluginPanelControl>(controlsElement.GetArrayLength());
        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (var element in controlsElement.EnumerateArray())
        {
            if (element.ValueKind != JsonValueKind.Object
                || element.EnumerateObject().Any(property => property.Name is not
                    ("id" or "type" or "label" or "value" or "checked")))
            {
                throw new PdppHostRequestException(-32602, "面板控件包含未知字段。");
            }

            var id = ReadPanelText(element, "id", 64);
            var type = ReadPanelText(element, "type", 16);
            var label = ReadPanelText(element, "label", 200);
            if (!PanelIdPattern.IsMatch(id)
                || !ids.Add(id)
                || type is not ("text" or "label" or "input" or "checkbox" or "button"))
            {
                throw new PdppHostRequestException(-32602, "面板控件 ID 或类型无效。");
            }

            string? value = null;
            if (element.TryGetProperty("value", out var valueElement))
            {
                if (valueElement.ValueKind != JsonValueKind.String
                    || valueElement.GetString()!.Length > 4096)
                {
                    throw new PdppHostRequestException(-32602, "面板控件 value 无效。");
                }

                value = valueElement.GetString();
            }

            bool? isChecked = null;
            if (element.TryGetProperty("checked", out var checkedElement))
            {
                if (checkedElement.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
                {
                    throw new PdppHostRequestException(-32602, "面板控件 checked 无效。");
                }

                isChecked = checkedElement.GetBoolean();
            }

            if (type == "checkbox" && isChecked is null)
            {
                isChecked = false;
            }

            controls.Add(new PluginPanelControl(id, type, label, value, isChecked));
        }

        return new PluginPanelDescriptor(panelId, title, width, height, controls);
    }

    private static double ReadPanelDimension(
        JsonElement parameters,
        string name,
        double defaultValue,
        double minimum,
        double maximum)
    {
        if (!parameters.TryGetProperty(name, out var element))
        {
            return defaultValue;
        }

        if (!element.TryGetDouble(out var value) || value < minimum || value > maximum)
        {
            throw new PdppHostRequestException(-32602, $"面板 {name} 超出允许范围。");
        }

        return value;
    }

    private static string ReadPanelText(JsonElement element, string name, int maximum)
    {
        if (!element.TryGetProperty(name, out var value)
            || value.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(value.GetString())
            || value.GetString()!.Length > maximum)
        {
            throw new PdppHostRequestException(-32602, $"面板控件 {name} 无效。");
        }

        return value.GetString()!;
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

    private static bool TryReadFileReference(JsonElement parameters, out Guid grantId)
    {
        grantId = default;
        return parameters.ValueKind == JsonValueKind.Object
            && parameters.TryGetProperty("file_ref", out var reference)
            && reference.ValueKind == JsonValueKind.String
            && Guid.TryParseExact(reference.GetString(), "N", out grantId);
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
