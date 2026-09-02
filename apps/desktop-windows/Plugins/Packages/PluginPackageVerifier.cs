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
    public const string ProvenancePath = "provenance.json";
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
    private static readonly IReadOnlySet<string> CommandSchemaRootFields = new HashSet<string>(
        ["type", "properties", "required", "additionalProperties"],
        StringComparer.Ordinal);
    private static readonly IReadOnlySet<string> CommandSchemaPropertyFields = new HashSet<string>(
        [
            "type",
            "title",
            "description",
            "enum",
            "format",
            "default",
            "minLength",
            "maxLength",
            "pattern",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "multipleOf",
        ],
        StringComparer.Ordinal);
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
        ValidateProvenance(entries, files);

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

        ValidateCapabilityGrants(manifest);

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

        if (manifest.Migration is { } migration)
        {
            if (migration.FromVersions is null
                || migration.FromVersions.Count > 128
                || migration.FromVersions.Distinct(StringComparer.Ordinal).Count()
                != migration.FromVersions.Count
                || migration.FromVersions.Any(version => !VersionPattern.IsMatch(version))
                || !string.Equals(migration.Strategy, "idempotent", StringComparison.Ordinal)
                || migration.Required && migration.FromVersions.Count == 0)
            {
                throw new PluginPackageException("插件迁移声明无效，必须使用幂等策略和有效来源版本。");
            }
        }
    }

    private static void ValidateCapabilityGrants(PluginManifest manifest)
    {
        var grants = manifest.Capabilities.Grants;
        if (grants is null)
        {
            return;
        }

        var declared = manifest.Capabilities.Required
            .Concat(manifest.Capabilities.Optional)
            .ToHashSet(StringComparer.Ordinal);
        if (grants.Count > 64
            || grants.Any(grant => grant is null
                                  || string.IsNullOrWhiteSpace(grant.Capability)
                                  || !declared.Contains(grant.Capability))
            || grants.Select(grant => grant.Capability).Distinct(StringComparer.Ordinal).Count()
            != grants.Count)
        {
            throw new PluginPackageException("插件能力约束必须引用已声明且唯一的权限。");
        }

        foreach (var grant in grants)
        {
            if (grant.TtlSeconds is < 1 or > 86_400)
            {
                throw new PluginPackageException("插件能力 ttl_seconds 必须在 1 到 86400 秒之间。");
            }

            if (grant.Constraints is { } constraints
                && constraints.ValueKind is not (JsonValueKind.Object or JsonValueKind.Null))
            {
                throw new PluginPackageException("插件能力 constraints 必须是 JSON 对象。");
            }

            if (grant.Quota is { } quota
                && (quota.Requests is < 1 or > 1_000_000
                    || quota.Bytes is < 1 or > 4_294_967_296))
            {
                throw new PluginPackageException("插件能力 quota 超出允许范围。");
            }
        }
    }

    private static void ValidateProvenance(
        IReadOnlyDictionary<string, ZipArchiveEntry> entries,
        IReadOnlyList<PluginPackageFile> files)
    {
        if (!entries.TryGetValue(ProvenancePath, out var entry) || IsDirectory(entry))
        {
            return;
        }
        if (entry.Length > MaximumManifestBytes)
        {
            throw new PluginPackageException("插件构建溯源超过大小限制。");
        }
        using var stream = entry.Open();
        using var document = JsonDocument.Parse(stream, new JsonDocumentOptions
        {
            AllowTrailingCommas = false,
            CommentHandling = JsonCommentHandling.Disallow,
            MaxDepth = 32,
        });
        var root = document.RootElement;
        var fields = root.ValueKind == JsonValueKind.Object
            ? root.EnumerateObject().Select(property => property.Name).ToHashSet(StringComparer.Ordinal)
            : [];
        if (!fields.SetEquals(["schema", "source_commit", "source_files", "sbom", "binaries"])
            || root.GetProperty("schema").GetString() != "pd.plugin.provenance/v1"
            || !IsCommit(root.GetProperty("source_commit")))
        {
            throw new PluginPackageException("插件构建溯源 Schema 或源码提交无效。");
        }
        var actual = files
            .Where(file => file.Path != PluginPackageSignature.SignaturePath)
            .ToDictionary(file => file.Path, StringComparer.Ordinal);
        var source = ReadProvenanceRecords(root.GetProperty("source_files"), "源码");
        var binaries = ReadProvenanceRecords(root.GetProperty("binaries"), "二进制");
        var sbom = ReadProvenanceRecord(root.GetProperty("sbom"), "SBOM");
        var actualSource = actual.Values
            .Where(file => file.Path.StartsWith("source/", StringComparison.Ordinal))
            .ToDictionary(file => file.Path, StringComparer.Ordinal);
        var actualBinaries = actual.Values
            .Where(file => file.Path.StartsWith("bin/", StringComparison.Ordinal))
            .ToDictionary(file => file.Path, StringComparer.Ordinal);
        if (!RecordsMatch(source, actualSource)
            || !RecordsMatch(binaries, actualBinaries)
            || !actual.TryGetValue("sbom.cdx.json", out var actualSbom)
            || !RecordMatches(sbom, actualSbom))
        {
            throw new PluginPackageException("插件构建溯源与源码、SBOM 或二进制摘要不一致。");
        }
    }

    private static Dictionary<string, PluginPackageFile> ReadProvenanceRecords(
        JsonElement value,
        string label)
    {
        if (value.ValueKind != JsonValueKind.Array)
        {
            throw new PluginPackageException($"插件构建溯源 {label} 必须是数组。");
        }
        var records = value.EnumerateArray()
            .Select(item => ReadProvenanceRecord(item, label))
            .ToArray();
        if (records.Select(record => record.Path).Distinct(StringComparer.Ordinal).Count()
            != records.Length)
        {
            throw new PluginPackageException($"插件构建溯源 {label} 包含重复路径。");
        }
        return records.ToDictionary(record => record.Path, StringComparer.Ordinal);
    }

    private static PluginPackageFile ReadProvenanceRecord(JsonElement value, string label)
    {
        var fields = value.ValueKind == JsonValueKind.Object
            ? value.EnumerateObject().Select(property => property.Name).ToHashSet(StringComparer.Ordinal)
            : [];
        if (!fields.SetEquals(["path", "size_bytes", "sha256"])
            || value.GetProperty("path").GetString() is not { } path
            || !value.GetProperty("size_bytes").TryGetInt64(out var size)
            || size < 0
            || value.GetProperty("sha256").GetString() is not { Length: 64 } sha256
            || sha256.Any(character => !Uri.IsHexDigit(character)))
        {
            throw new PluginPackageException($"插件构建溯源 {label} 记录无效。");
        }
        return new PluginPackageFile(path, size, sha256.ToLowerInvariant());
    }

    private static bool IsCommit(JsonElement value) =>
        value.ValueKind == JsonValueKind.String
        && value.GetString() is { Length: 40 or 64 } commit
        && commit.All(Uri.IsHexDigit);

    private static bool RecordsMatch(
        IReadOnlyDictionary<string, PluginPackageFile> expected,
        IReadOnlyDictionary<string, PluginPackageFile> actual) =>
        expected.Count == actual.Count
        && expected.All(pair => actual.TryGetValue(pair.Key, out var file)
                                && RecordMatches(pair.Value, file));

    private static bool RecordMatches(PluginPackageFile expected, PluginPackageFile actual) =>
        expected.Path == actual.Path
        && expected.Length == actual.Length
        && string.Equals(expected.Sha256, actual.Sha256, StringComparison.OrdinalIgnoreCase);

    private static void ValidateCommandInputSchema(
        JsonElement schema,
        PluginManifest manifest)
    {
        if (schema.ValueKind != JsonValueKind.Object
            || schema.EnumerateObject().Any(property => !CommandSchemaRootFields.Contains(property.Name))
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
                                                         || !propertyNames.Contains(item.GetString()!))
                || required.EnumerateArray().Select(item => item.GetString())
                    .Distinct(StringComparer.Ordinal).Count() != required.GetArrayLength()))
        {
            throw new PluginPackageException("插件命令输入 Schema 的 required 字段无效。");
        }
        if (schema.TryGetProperty("additionalProperties", out var additionalProperties)
            && additionalProperties.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
        {
            throw new PluginPackageException("插件命令输入 Schema 的 additionalProperties 必须是布尔值。");
        }

        var requestedCapabilities = manifest.Capabilities.Required
            .Concat(manifest.Capabilities.Optional)
            .ToHashSet(StringComparer.Ordinal);
        foreach (var property in properties.EnumerateObject())
        {
            if (property.Name.Length is < 1 or > 128
                || property.Value.ValueKind != JsonValueKind.Object
                || property.Value.EnumerateObject().Any(
                    item => !CommandSchemaPropertyFields.Contains(item.Name))
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
            if (property.Value.TryGetProperty("description", out var description)
                && (description.ValueKind != JsonValueKind.String
                    || description.GetString()!.Length > 500))
            {
                throw new PluginPackageException("插件命令输入 Schema 字段说明无效。");
            }

            if (property.Value.TryGetProperty("enum", out var enumValues)
                && (type.GetString() != "string"
                    || enumValues.ValueKind != JsonValueKind.Array
                    || enumValues.GetArrayLength() is < 1 or > 100
                    || enumValues.EnumerateArray().Any(
                        item => item.ValueKind != JsonValueKind.String)
                    || enumValues.EnumerateArray().Select(item => item.GetRawText())
                        .Distinct(StringComparer.Ordinal).Count() != enumValues.GetArrayLength()))
            {
                throw new PluginPackageException("插件命令枚举输入无效。");
            }

            if (property.Value.TryGetProperty("format", out var format))
            {
                if (format.ValueKind != JsonValueKind.String
                    || format.GetString() is not ("file" or "theme-background")
                    || type.GetString() != "string")
                {
                    throw new PluginPackageException(
                        "v1 命令输入只支持 file 或 theme-background 格式，不授予目录枚举能力。");
                }

                var requiredCapability = format.GetString() == "theme-background"
                    ? "ui:theme"
                    : "file:read:selected";
                if (!requestedCapabilities.Contains(requiredCapability))
                {
                    throw new PluginPackageException($"使用 {format.GetString()} 输入的插件必须申请 {requiredCapability} 权限。");
                }
            }

            if (property.Value.TryGetProperty("default", out var defaultValue)
                && (!MatchesSchemaType(defaultValue, type.GetString()!)
                    || property.Value.TryGetProperty("enum", out enumValues)
                    && !enumValues.EnumerateArray().Any(
                        item => item.GetRawText() == defaultValue.GetRawText())))
            {
                throw new PluginPackageException("插件命令输入 Schema 默认值无效。");
            }

            ValidateCommandPropertyConstraints(property.Value, type.GetString()!);
        }
    }

    private static bool MatchesSchemaType(JsonElement value, string type) => type switch
    {
        "string" => value.ValueKind == JsonValueKind.String,
        "integer" => value.ValueKind == JsonValueKind.Number && value.TryGetInt64(out _),
        "number" => value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out _),
        "boolean" => value.ValueKind is JsonValueKind.True or JsonValueKind.False,
        _ => false,
    };

    private static void ValidateCommandPropertyConstraints(JsonElement schema, string type)
    {
        var stringConstraintNames = new[] { "minLength", "maxLength", "pattern" };
        var numericConstraintNames = new[]
        {
            "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
        };
        if (type != "string" && stringConstraintNames.Any(name => schema.TryGetProperty(name, out _))
            || type is not ("integer" or "number")
            && numericConstraintNames.Any(name => schema.TryGetProperty(name, out _)))
        {
            throw new PluginPackageException("插件命令输入 Schema 约束与字段类型不匹配。");
        }

        var minimumLength = 0;
        if (schema.TryGetProperty("minLength", out var minimumLengthElement)
            && (!minimumLengthElement.TryGetInt32(out minimumLength) || minimumLength < 0))
        {
            throw new PluginPackageException("插件命令输入 Schema 最小长度无效。");
        }
        if (schema.TryGetProperty("maxLength", out var maximumLengthElement)
            && (!maximumLengthElement.TryGetInt32(out var maximumLength)
                || maximumLength < minimumLength))
        {
            throw new PluginPackageException("插件命令输入 Schema 最大长度无效。");
        }
        if (schema.TryGetProperty("pattern", out var pattern))
        {
            if (pattern.ValueKind != JsonValueKind.String || pattern.GetString()!.Length > 512)
            {
                throw new PluginPackageException("插件命令输入 Schema 正则约束无效。");
            }
        }

        if (schema.TryGetProperty("minimum", out _)
            && schema.TryGetProperty("exclusiveMinimum", out _)
            || schema.TryGetProperty("maximum", out _)
            && schema.TryGetProperty("exclusiveMaximum", out _))
        {
            throw new PluginPackageException("插件命令输入 Schema 数值边界不能重复声明。");
        }
        foreach (var name in numericConstraintNames)
        {
            if (schema.TryGetProperty(name, out var value)
                && (value.ValueKind != JsonValueKind.Number || !value.TryGetDouble(out _)))
            {
                throw new PluginPackageException("插件命令输入 Schema 数值约束无效。");
            }
        }
        if (schema.TryGetProperty("multipleOf", out var multipleOf)
            && multipleOf.GetDouble() <= 0)
        {
            throw new PluginPackageException("插件命令输入 Schema multipleOf 必须大于零。");
        }
        var lower = schema.TryGetProperty("exclusiveMinimum", out var exclusiveMinimum)
            ? exclusiveMinimum.GetDouble()
            : schema.TryGetProperty("minimum", out var minimum)
                ? minimum.GetDouble()
                : (double?)null;
        var upper = schema.TryGetProperty("exclusiveMaximum", out var exclusiveMaximum)
            ? exclusiveMaximum.GetDouble()
            : schema.TryGetProperty("maximum", out var maximum)
                ? maximum.GetDouble()
                : (double?)null;
        if (lower.HasValue && upper.HasValue
            && (lower > upper
                || lower == upper
                && (schema.TryGetProperty("exclusiveMinimum", out _)
                    || schema.TryGetProperty("exclusiveMaximum", out _))))
        {
            throw new PluginPackageException("插件命令输入 Schema 数值范围无效。");
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
