using System.IO;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace PasswordDetective.Desktop.Plugins.Packages;

public sealed class PluginPackageVerifier
{
    public const string ManifestPath = "manifest.json";
    public const string ManifestSchema = "pd.plugin/v1";
    public const int ProtocolVersion = 1;
    public const string HostVersion = "0.1.0";

    private const int MaximumManifestBytes = 128 * 1024;
    private const int MaximumSignatureTextBytes = 256;
    private static readonly Regex IdentifierPattern = new(
        "^[a-z0-9]+(?:[._-][a-z0-9]+)+$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex CommandPattern = new(
        "^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex VersionPattern = new(
        "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly JsonSerializerOptions ManifestOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        RespectRequiredConstructorParameters = true,
        MaxDepth = 32,
    };

    private readonly PluginPackageLimits _limits;

    public PluginPackageVerifier(PluginPackageLimits? limits = null)
    {
        _limits = limits ?? new PluginPackageLimits();
        _limits.Validate();
    }

    public async Task<PluginPackageInspection> VerifyAsync(
        string packagePath,
        CancellationToken cancellationToken = default)
    {
        var fullPath = Path.GetFullPath(packagePath);
        if (!string.Equals(Path.GetExtension(fullPath), ".pdpkg", StringComparison.OrdinalIgnoreCase))
        {
            throw new PluginPackageException("插件包扩展名必须为 .pdpkg。");
        }

        var packageInfo = new FileInfo(fullPath);
        if (!packageInfo.Exists)
        {
            throw new PluginPackageException("插件包不存在。");
        }

        if (packageInfo.Length is <= 0 || packageInfo.Length > _limits.MaximumPackageBytes)
        {
            throw new PluginPackageException("插件包大小超出允许范围。");
        }

        await using var stream = new FileStream(
            fullPath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            bufferSize: 64 * 1024,
            FileOptions.Asynchronous | FileOptions.SequentialScan);
        var packageSha256 = Convert.ToHexStringLower(await SHA256.HashDataAsync(stream, cancellationToken));
        stream.Position = 0;

        try
        {
            using var archive = new ZipArchive(stream, ZipArchiveMode.Read, leaveOpen: true);
            return await VerifyArchiveAsync(
                fullPath,
                packageSha256,
                archive,
                cancellationToken);
        }
        catch (PluginPackageException)
        {
            throw;
        }
        catch (InvalidDataException exception)
        {
            throw new PluginPackageException("插件包不是有效的受限 ZIP 文件。", exception);
        }
        catch (JsonException exception)
        {
            throw new PluginPackageException("插件清单或输入 Schema 不是有效 JSON。", exception);
        }
        catch (DecoderFallbackException exception)
        {
            throw new PluginPackageException("插件清单或签名不是有效 UTF-8。", exception);
        }
    }

    private async Task<PluginPackageInspection> VerifyArchiveAsync(
        string packagePath,
        string packageSha256,
        ZipArchive archive,
        CancellationToken cancellationToken)
    {
        if (archive.Entries.Count is < 3 || archive.Entries.Count > _limits.MaximumEntries)
        {
            throw new PluginPackageException("插件包文件数量超出允许范围。");
        }

        var entries = new Dictionary<string, ZipArchiveEntry>(StringComparer.OrdinalIgnoreCase);
        var files = new List<PluginPackageFile>();
        long expandedSize = 0;
        foreach (var entry in archive.Entries)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var normalizedPath = ValidateEntry(entry);
            if (!entries.TryAdd(normalizedPath, entry))
            {
                throw new PluginPackageException("插件包包含重复或仅大小写不同的路径。");
            }

            if (IsDirectory(entry))
            {
                continue;
            }

            expandedSize = checked(expandedSize + entry.Length);
            if (entry.Length > _limits.MaximumSingleFileBytes
                || expandedSize > _limits.MaximumExpandedBytes)
            {
                throw new PluginPackageException("插件包单文件或总展开大小超出允许范围。");
            }

            if ((entry.Length > 1024 && entry.CompressedLength == 0)
                || (entry.CompressedLength > 0
                    && entry.Length / (double)entry.CompressedLength > _limits.MaximumCompressionRatio))
            {
                throw new PluginPackageException("插件包包含异常压缩比文件。");
            }

            await using var entryStream = entry.Open();
            var hash = Convert.ToHexStringLower(
                await SHA256.HashDataAsync(entryStream, cancellationToken));
            files.Add(new PluginPackageFile(normalizedPath, entry.Length, hash));
        }

        var manifestEntry = GetRequiredFile(entries, ManifestPath);
        var signatureEntry = GetRequiredFile(entries, PluginPackageSignature.SignaturePath);
        var manifest = await ReadManifestAsync(manifestEntry, cancellationToken);
        ValidateManifest(manifest, entries);

        byte[] publicKey;
        byte[] signature;
        try
        {
            publicKey = Convert.FromBase64String(manifest.PublisherPublicKey);
            signature = Convert.FromBase64String(
                await ReadTextAsync(signatureEntry, MaximumSignatureTextBytes, cancellationToken));
        }
        catch (FormatException exception)
        {
            throw new PluginPackageException("插件开发者公钥或签名不是有效 Base64。", exception);
        }

        if (!PluginPackageSignature.Verify(files, publicKey, signature))
        {
            throw new PluginPackageException("插件开发者 Ed25519 签名无效。");
        }

        var architecture = RuntimeInformation.ProcessArchitecture == Architecture.Arm64
            ? "windows-arm64"
            : "windows-x64";
        if (!manifest.Runtime.Entrypoints.TryGetValue(architecture, out var entryPoint))
        {
            throw new PluginPackageException($"插件包不包含当前架构 {architecture} 的入口点。");
        }

        var normalizedEntryPoint = NormalizeManifestPath(entryPoint, "插件入口点");
        if (!normalizedEntryPoint.StartsWith("bin/", StringComparison.Ordinal)
            || !normalizedEntryPoint.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
            || !entries.TryGetValue(normalizedEntryPoint, out var executable)
            || IsDirectory(executable))
        {
            throw new PluginPackageException("插件入口点必须是 bin/ 下已存在的 Windows 可执行文件。");
        }

        return new PluginPackageInspection(
            packagePath,
            packageSha256,
            manifest,
            normalizedEntryPoint,
            architecture,
            PluginPackageSignature.Fingerprint(publicKey),
            files.AsReadOnly(),
            expandedSize);
    }

    private static async Task<PluginManifest> ReadManifestAsync(
        ZipArchiveEntry entry,
        CancellationToken cancellationToken)
    {
        var json = await ReadTextAsync(entry, MaximumManifestBytes, cancellationToken);
        return JsonSerializer.Deserialize<PluginManifest>(json, ManifestOptions)
            ?? throw new PluginPackageException("插件清单不能为空。");
    }

    private static void ValidateManifest(
        PluginManifest manifest,
        IReadOnlyDictionary<string, ZipArchiveEntry> entries)
    {
        if (manifest.Protocol is null
            || manifest.Host is null
            || manifest.Runtime is null
            || manifest.Runtime.Entrypoints is null
            || manifest.Commands is null
            || manifest.Capabilities is null
            || manifest.Capabilities.Required is null
            || manifest.Capabilities.Optional is null
            || manifest.Limits is null
            || manifest.Schema != ManifestSchema
            || string.IsNullOrWhiteSpace(manifest.PluginId)
            || manifest.PluginId.Length is < 3 or > 255
            || !IdentifierPattern.IsMatch(manifest.PluginId)
            || string.IsNullOrWhiteSpace(manifest.Version)
            || !VersionPattern.IsMatch(manifest.Version))
        {
            throw new PluginPackageException("插件清单 Schema、插件 ID 或版本无效。");
        }

        ValidateText(manifest.DisplayName, 1, 100, "插件名称");
        ValidateText(manifest.Description, 1, 500, "插件说明");
        ValidateText(manifest.PublisherKeyId, 1, 128, "开发者密钥 ID");
        ValidateText(manifest.PublisherPublicKey, 1, 128, "开发者公钥");
        if (manifest.Protocol.Min > ProtocolVersion
            || manifest.Protocol.Max < ProtocolVersion
            || manifest.Protocol.Min < 1
            || manifest.Protocol.Max > ProtocolVersion)
        {
            throw new PluginPackageException("插件协议版本与 PDPP v1 不兼容。");
        }

        if (!IsHostVersionSupported(manifest.Host)
            || !string.Equals(manifest.Runtime.Kind, "process", StringComparison.Ordinal))
        {
            throw new PluginPackageException("插件宿主版本或运行时类型不兼容。");
        }

        if (manifest.Commands.Count is < 1 or > 64
            || manifest.Commands.Any(command => command is null)
            || manifest.Commands.Select(command => command.Id).Distinct(StringComparer.Ordinal).Count()
            != manifest.Commands.Count)
        {
            throw new PluginPackageException("插件命令数量或命令 ID 无效。");
        }

        if (!manifest.Capabilities.Required.Contains("ui:command", StringComparer.Ordinal))
        {
            throw new PluginPackageException("包含命令的插件必须申请 ui:command 必需权限。");
        }

        foreach (var command in manifest.Commands)
        {
            if (command is null
                || string.IsNullOrWhiteSpace(command.Id)
                || command.Id.Length > 128
                || !CommandPattern.IsMatch(command.Id))
            {
                throw new PluginPackageException("插件命令 ID 无效。");
            }

            ValidateText(command.Title, 1, 100, "插件命令名称");
            var schemaPath = NormalizeManifestPath(command.InputSchema, "命令输入 Schema");
            if (!schemaPath.StartsWith("schemas/", StringComparison.Ordinal)
                || !entries.TryGetValue(schemaPath, out var schemaEntry)
                || IsDirectory(schemaEntry)
                || schemaEntry.Length > MaximumManifestBytes)
            {
                throw new PluginPackageException("插件命令输入 Schema 缺失或超出大小限制。");
            }

            using var schemaStream = schemaEntry.Open();
            using var schema = JsonDocument.Parse(schemaStream, new JsonDocumentOptions
            {
                AllowTrailingCommas = false,
                CommentHandling = JsonCommentHandling.Disallow,
                MaxDepth = 32,
            });
            ValidateCommandInputSchema(schema.RootElement, manifest);
        }

        if (manifest.Limits.MemoryMb is < 64 or > 1024
            || manifest.Limits.CpuPercent is < 5 or > 50
            || manifest.Limits.CommandTimeoutSeconds is < 5 or > 600
            || manifest.Limits.ChildProcesses != 0)
        {
            throw new PluginPackageException("插件资源限制超出宿主允许范围。");
        }
    }

    private static void ValidateCommandInputSchema(
        JsonElement schema,
        PluginManifest manifest)
    {
        if (schema.ValueKind != JsonValueKind.Object
            || !schema.TryGetProperty("type", out var rootType)
            || rootType.ValueKind != JsonValueKind.String
            || rootType.GetString() != "object"
            || !schema.TryGetProperty("properties", out var properties)
            || properties.ValueKind != JsonValueKind.Object
            || properties.EnumerateObject().Count() > 32)
        {
            throw new PluginPackageException("插件命令输入 Schema 必须声明受限 object properties。");
        }

        var propertyNames = properties.EnumerateObject()
            .Select(property => property.Name)
            .ToHashSet(StringComparer.Ordinal);
        if (schema.TryGetProperty("required", out var required)
            && (required.ValueKind != JsonValueKind.Array
                || required.EnumerateArray().Any(item => item.ValueKind != JsonValueKind.String
                                                         || !propertyNames.Contains(item.GetString()!))))
        {
            throw new PluginPackageException("插件命令输入 Schema 的 required 字段无效。");
        }

        var requestedCapabilities = manifest.Capabilities.Required
            .Concat(manifest.Capabilities.Optional)
            .ToHashSet(StringComparer.Ordinal);
        foreach (var property in properties.EnumerateObject())
        {
            if (property.Name.Length is < 1 or > 128
                || property.Value.ValueKind != JsonValueKind.Object
                || !property.Value.TryGetProperty("type", out var type)
                || type.ValueKind != JsonValueKind.String
                || type.GetString() is not ("string" or "integer" or "number" or "boolean"))
            {
                throw new PluginPackageException("插件命令输入 Schema 包含不支持的字段类型。");
            }

            if (property.Value.TryGetProperty("title", out var title)
                && (title.ValueKind != JsonValueKind.String
                    || string.IsNullOrWhiteSpace(title.GetString())
                    || title.GetString()!.Length > 100))
            {
                throw new PluginPackageException("插件命令输入 Schema 字段标题无效。");
            }

            if (property.Value.TryGetProperty("enum", out var enumValues)
                && (type.GetString() != "string"
                    || enumValues.ValueKind != JsonValueKind.Array
                    || enumValues.GetArrayLength() is < 1 or > 100
                    || enumValues.EnumerateArray().Any(item => item.ValueKind != JsonValueKind.String)))
            {
                throw new PluginPackageException("插件命令枚举输入无效。");
            }

            if (!property.Value.TryGetProperty("format", out var format))
            {
                continue;
            }

            if (format.ValueKind != JsonValueKind.String
                || format.GetString() != "file"
                || type.GetString() != "string")
            {
                throw new PluginPackageException("v1 命令输入只支持 file 文件格式，不授予目录枚举能力。");
            }

            if (!requestedCapabilities.Contains("file:read:selected"))
            {
                throw new PluginPackageException("使用文件输入的插件必须申请 file:read:selected 权限。");
            }
        }
    }

    private static bool IsHostVersionSupported(PluginHostRange host)
    {
        if (!Version.TryParse(HostVersion, out var current)
            || string.IsNullOrWhiteSpace(host.MinVersion)
            || string.IsNullOrWhiteSpace(host.MaxVersion)
            || !Version.TryParse(host.MinVersion, out var minimum)
            || current < minimum)
        {
            return false;
        }

        if (host.MaxVersion.EndsWith(".x", StringComparison.Ordinal))
        {
            var prefix = host.MaxVersion[..^2];
            return int.TryParse(prefix, out var major) && current.Major == major;
        }

        return Version.TryParse(host.MaxVersion, out var maximum) && current <= maximum;
    }

    private static string ValidateEntry(ZipArchiveEntry entry)
    {
        var rawPath = entry.FullName;
        if (string.IsNullOrWhiteSpace(rawPath)
            || rawPath.Length > 512
            || rawPath.Contains('\\')
            || rawPath.Contains(':')
            || rawPath.Any(character => char.IsControl(character)))
        {
            throw new PluginPackageException("插件包包含非法路径。");
        }

        var directory = rawPath.EndsWith("/", StringComparison.Ordinal);
        var normalized = directory ? rawPath[..^1] : rawPath;
        var segments = normalized.Split('/');
        if (normalized.Length == 0
            || rawPath.StartsWith("/", StringComparison.Ordinal)
            || segments.Any(segment => segment is "" or "." or ".."))
        {
            throw new PluginPackageException("插件包包含绝对路径或路径穿越。");
        }

        var unixFileType = (entry.ExternalAttributes >> 16) & 0xF000;
        var windowsAttributes = (FileAttributes)(entry.ExternalAttributes & 0xFFFF);
        if (unixFileType is 0xA000 or 0x6000
            || windowsAttributes.HasFlag(FileAttributes.ReparsePoint))
        {
            throw new PluginPackageException("插件包不允许符号链接、设备文件或重解析点。");
        }

        return normalized;
    }

    internal static string NormalizeManifestPath(string path, string fieldName)
    {
        if (string.IsNullOrWhiteSpace(path)
            || path.Length > 512
            || path.Contains('\\')
            || path.Contains(':')
            || path.StartsWith("/", StringComparison.Ordinal)
            || path.Any(character => char.IsControl(character))
            || path.Split('/').Any(segment => segment is "" or "." or ".."))
        {
            throw new PluginPackageException($"{fieldName}包含非法路径。");
        }

        return path;
    }

    private static ZipArchiveEntry GetRequiredFile(
        IReadOnlyDictionary<string, ZipArchiveEntry> entries,
        string path)
    {
        if (!entries.TryGetValue(path, out var entry) || IsDirectory(entry))
        {
            throw new PluginPackageException($"插件包缺少 {path}。");
        }

        return entry;
    }

    private static bool IsDirectory(ZipArchiveEntry entry) =>
        entry.FullName.EndsWith("/", StringComparison.Ordinal);

    private static async Task<string> ReadTextAsync(
        ZipArchiveEntry entry,
        int maximumBytes,
        CancellationToken cancellationToken)
    {
        if (entry.Length > maximumBytes)
        {
            throw new PluginPackageException($"{entry.FullName} 超出大小限制。");
        }

        await using var stream = entry.Open();
        using var reader = new StreamReader(
            stream,
            new UTF8Encoding(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true),
            detectEncodingFromByteOrderMarks: false,
            bufferSize: 4096,
            leaveOpen: false);
        return await reader.ReadToEndAsync(cancellationToken);
    }

    private static void ValidateText(string value, int minimum, int maximum, string fieldName)
    {
        if (string.IsNullOrWhiteSpace(value)
            || value.Length < minimum
            || value.Length > maximum
            || value.Any(character => char.IsControl(character) && character is not '\r' and not '\n'))
        {
            throw new PluginPackageException($"{fieldName}无效。");
        }
    }
}
