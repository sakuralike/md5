using System.Globalization;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Crypto.Signers;
using PasswordDetective.Pdpp;

namespace PasswordDetective.OfficialPluginInspector;

public sealed record PackageInspectionFinding(
    string Severity,
    string Code,
    string Message,
    string? Path = null);

public sealed record PackageInspectionSummary(
    int EntryCount,
    long ExpandedSizeBytes,
    int CommandCount,
    int SourceFileCount,
    IReadOnlyList<string> Capabilities,
    bool ManifestValid,
    bool SignatureValid,
    bool SbomValid,
    bool SourceIncluded);

public sealed record PackageInspectionReport(
    string Status,
    string FileName,
    long PackageSizeBytes,
    string PackageSha256,
    string? PluginId,
    string? Version,
    PackageInspectionSummary Summary,
    int FindingCount,
    bool FindingsTruncated,
    IReadOnlyList<PackageInspectionFinding> Findings);

public static class PackageInspector
{
    public const long MaximumReadablePackageBytes = 128L * 1024 * 1024;
    private const long MaximumExpandedBytes = 1024L * 1024 * 1024;
    private const long MaximumSingleFileBytes = 256L * 1024 * 1024;
    private const int MaximumEntries = 2048;
    private const int MaximumSourceFiles = 32;
    private const long MaximumSourceFileBytes = 256L * 1024;
    private const long MaximumManifestBytes = 64L * 1024;
    private const long MaximumSbomBytes = 2L * 1024 * 1024;
    private const double MaximumCompressionRatio = 100d;
    private const int MaximumReturnedFindings = 200;

    private static readonly Regex PluginIdPattern = new(
        "^[a-z0-9]+(?:[._-][a-z0-9]+)+$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex VersionPattern = new(
        "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly IReadOnlySet<string> KnownCapabilities = new HashSet<string>(
        [
            "ui:command",
            "ui:theme",
            "ui:window",
            "storage:private",
            "file:read:selected",
            "api:profile:read",
            "api:hash:read",
            "api:verification:submit",
            "network:internet",
            "secret:candidate:ephemeral",
            "process:spawn",
            "system:persistence",
            "credential:read",
        ],
        StringComparer.Ordinal);
    private static readonly IReadOnlySet<string> ManifestFields = new HashSet<string>(
        [
            "schema",
            "plugin_id",
            "version",
            "display_name",
            "description",
            "publisher_key_id",
            "publisher_public_key",
            "protocol",
            "host",
            "runtime",
            "commands",
            "capabilities",
            "limits",
        ],
        StringComparer.Ordinal);

    public static PackageInspectionReport CreateSizeFailure(
        PluginSelectedFile selected,
        string packageSha256) =>
        CreateReport(
            selected,
            packageSha256,
            null,
            null,
            new PackageInspectionSummary(0, 0, 0, 0, [], false, false, false, false),
            [new PackageInspectionFinding(
                "error",
                "package.too_large",
                $"插件包超过体检工具 {MaximumReadablePackageBytes / 1024 / 1024} MiB 读取上限。")]);

    public static PackageInspectionReport Inspect(
        PluginSelectedFile selected,
        byte[] packageBytes,
        string packageSha256)
    {
        var findings = new List<PackageInspectionFinding>();
        if (!selected.FileName.EndsWith(".pdpkg", StringComparison.OrdinalIgnoreCase))
        {
            findings.Add(new PackageInspectionFinding(
                "warning",
                "package.extension",
                "文件扩展名不是 .pdpkg。"));
        }

        try
        {
            using var archive = new ZipArchive(
                new MemoryStream(packageBytes, writable: false),
                ZipArchiveMode.Read,
                leaveOpen: false);
            return InspectArchive(selected, packageSha256, archive, findings);
        }
        catch (InvalidDataException)
        {
            findings.Add(new PackageInspectionFinding(
                "error",
                "package.zip_invalid",
                "文件不是有效的 ZIP/PDPKG 包。"));
            return CreateReport(
                selected,
                packageSha256,
                null,
                null,
                new PackageInspectionSummary(0, 0, 0, 0, [], false, false, false, false),
                findings);
        }
    }

    private static PackageInspectionReport InspectArchive(
        PluginSelectedFile selected,
        string packageSha256,
        ZipArchive archive,
        List<PackageInspectionFinding> findings)
    {
        if (archive.Entries.Count is < 3 or > MaximumEntries)
        {
            findings.Add(new PackageInspectionFinding(
                "error",
                "package.entry_count",
                $"插件包文件项数量必须在 3 到 {MaximumEntries} 之间。"));
        }

        var entries = new Dictionary<string, ZipArchiveEntry>(StringComparer.OrdinalIgnoreCase);
        long expandedSize = 0;
        foreach (var entry in archive.Entries)
        {
            var pathValid = ValidateEntryPath(entry, findings);
            try
            {
                expandedSize = checked(expandedSize + entry.Length);
            }
            catch (OverflowException)
            {
                expandedSize = long.MaxValue;
            }

            if (entry.Length > MaximumSingleFileBytes || expandedSize > MaximumExpandedBytes)
            {
                findings.Add(new PackageInspectionFinding(
                    "error",
                    "package.expanded_size",
                    "插件包单文件或总展开大小超过宿主限制。",
                    entry.FullName));
            }
            if ((entry.Length > 1024 && entry.CompressedLength == 0)
                || (entry.CompressedLength > 0
                    && entry.Length / (double)entry.CompressedLength > MaximumCompressionRatio))
            {
                findings.Add(new PackageInspectionFinding(
                    "error",
                    "package.compression_ratio",
                    "文件压缩比超过宿主限制。",
                    entry.FullName));
            }
            if (pathValid && !entries.TryAdd(entry.FullName, entry))
            {
                findings.Add(new PackageInspectionFinding(
                    "error",
                    "package.duplicate_path",
                    "插件包包含大小写不敏感的重复路径。",
                    entry.FullName));
            }
        }

        var sourceFiles = entries
            .Where(pair => !IsDirectory(pair.Value)
                           && pair.Key.StartsWith("source/", StringComparison.Ordinal))
            .ToArray();
        InspectSource(sourceFiles, findings);
        var sbomValid = InspectSbom(entries, findings);
        var manifestFacts = InspectManifest(entries, findings);
        var packageFiles = HashPackageFiles(entries.Values, findings);
        var signatureValid = VerifySignature(entries, packageFiles, manifestFacts.PublicKey, findings);
        var summary = new PackageInspectionSummary(
            archive.Entries.Count,
            expandedSize,
            manifestFacts.CommandCount,
            sourceFiles.Length,
            manifestFacts.Capabilities,
            manifestFacts.Valid,
            signatureValid,
            sbomValid,
            sourceFiles.Length > 0);
        return CreateReport(
            selected,
            packageSha256,
            manifestFacts.PluginId,
            manifestFacts.Version,
            summary,
            findings);
    }

    private static ManifestFacts InspectManifest(
        IReadOnlyDictionary<string, ZipArchiveEntry> entries,
        List<PackageInspectionFinding> findings)
    {
        if (!entries.TryGetValue("manifest.json", out var entry) || IsDirectory(entry))
        {
            findings.Add(new PackageInspectionFinding(
                "error",
                "manifest.missing",
                "插件包缺少 manifest.json。"));
            return ManifestFacts.Empty;
        }

        try
        {
            using var document = JsonDocument.Parse(ReadEntry(entry, MaximumManifestBytes));
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                throw new JsonException();
            }

            var valid = true;
            var actualFields = root.EnumerateObject().Select(item => item.Name).ToHashSet(StringComparer.Ordinal);
            if (!actualFields.SetEquals(ManifestFields))
            {
                AddManifestError(findings, "manifest.fields", "Manifest 字段不完整或包含未知字段。");
                valid = false;
            }

            var schema = ReadString(root, "schema");
            var pluginId = ReadString(root, "plugin_id");
            var version = ReadString(root, "version");
            if (schema != "pd.plugin/v1")
            {
                AddManifestError(findings, "manifest.schema", "Manifest schema 必须是 pd.plugin/v1。");
                valid = false;
            }
            if (pluginId is null || !PluginIdPattern.IsMatch(pluginId))
            {
                AddManifestError(findings, "manifest.plugin_id", "插件 ID 不是有效的反向域名标识。");
                valid = false;
            }
            if (version is null || !VersionPattern.IsMatch(version))
            {
                AddManifestError(findings, "manifest.version", "插件版本不是严格 SemVer x.y.z。");
                valid = false;
            }

            byte[]? publicKey = null;
            try
            {
                publicKey = Convert.FromBase64String(ReadString(root, "publisher_public_key") ?? string.Empty);
                if (publicKey.Length != Ed25519PublicKeyParameters.KeySize)
                {
                    throw new FormatException();
                }
            }
            catch (FormatException)
            {
                AddManifestError(findings, "manifest.public_key", "开发者 Ed25519 公钥格式无效。");
                valid = false;
                publicKey = null;
            }

            var capabilities = ReadCapabilities(root, findings, ref valid, out var requiredCapabilities);
            if (!requiredCapabilities.Contains("ui:command", StringComparer.Ordinal))
            {
                AddManifestError(findings, "manifest.ui_command", "命令型插件必须把 ui:command 声明为必需权限。");
                valid = false;
            }

            var commands = ReadArray(root, "commands");
            var commandCount = commands?.GetArrayLength() ?? 0;
            if (commands is null || commandCount is < 1 or > 64)
            {
                AddManifestError(findings, "manifest.commands", "插件命令数量必须在 1 到 64 之间。");
                valid = false;
            }
            else
            {
                var commandIds = new HashSet<string>(StringComparer.Ordinal);
                foreach (var command in commands.Value.EnumerateArray())
                {
                    var id = command.ValueKind == JsonValueKind.Object ? ReadString(command, "id") : null;
                    var schemaPath = command.ValueKind == JsonValueKind.Object
                        ? ReadString(command, "input_schema")
                        : null;
                    if (string.IsNullOrWhiteSpace(id)
                        || !commandIds.Add(id)
                        || string.IsNullOrWhiteSpace(schemaPath)
                        || !schemaPath.StartsWith("schemas/", StringComparison.Ordinal)
                        || !entries.TryGetValue(schemaPath, out var schemaEntry)
                        || IsDirectory(schemaEntry))
                    {
                        AddManifestError(findings, "manifest.command", "插件命令 ID 或输入 Schema 无效。");
                        valid = false;
                    }
                    else if (!ValidateCommandSchema(schemaEntry, capabilities, findings))
                    {
                        valid = false;
                    }
                }
            }

            valid &= ValidateProtocolAndHost(root, findings);
            valid &= ValidateRuntime(root, entries, findings);
            valid &= ValidateLimits(root, findings);
            return new ManifestFacts(valid, pluginId, version, publicKey, commandCount, capabilities);
        }
        catch (Exception exception) when (exception is JsonException or InvalidDataException or DecoderFallbackException)
        {
            AddManifestError(findings, "manifest.invalid_json", "manifest.json 不是大小受限的有效 JSON。");
            return ManifestFacts.Empty;
        }
    }

    private static bool ValidateProtocolAndHost(
        JsonElement root,
        List<PackageInspectionFinding> findings)
    {
        var valid = true;
        if (!root.TryGetProperty("protocol", out var protocol)
            || protocol.ValueKind != JsonValueKind.Object
            || !TryReadInt(protocol, "min", out var protocolMin)
            || !TryReadInt(protocol, "max", out var protocolMax)
            || protocolMin != 1
            || protocolMax != 1)
        {
            AddManifestError(findings, "manifest.protocol", "插件协议范围必须兼容 PDPP v1。");
            valid = false;
        }

        if (!root.TryGetProperty("host", out var host)
            || host.ValueKind != JsonValueKind.Object
            || !IsHostVersion(ReadString(host, "min_version"), allowWildcard: false)
            || !IsHostVersion(ReadString(host, "max_version"), allowWildcard: true))
        {
            AddManifestError(findings, "manifest.host", "宿主版本范围必须使用 x.y.z 或主版本通配 x.x。");
            valid = false;
        }
        return valid;
    }

    private static bool ValidateCommandSchema(
        ZipArchiveEntry entry,
        IReadOnlyCollection<string> capabilities,
        List<PackageInspectionFinding> findings)
    {
        try
        {
            using var document = JsonDocument.Parse(ReadEntry(entry, MaximumManifestBytes));
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || ReadString(root, "type") != "object"
                || !root.TryGetProperty("properties", out var properties)
                || properties.ValueKind != JsonValueKind.Object
                || properties.GetRawText().Length > MaximumManifestBytes
                || properties.EnumerateObject().Count() > 32)
            {
                throw new JsonException();
            }

            var propertyNames = properties.EnumerateObject()
                .Select(item => item.Name)
                .ToHashSet(StringComparer.Ordinal);
            if (root.TryGetProperty("required", out var required)
                && (required.ValueKind != JsonValueKind.Array
                    || required.EnumerateArray().Any(item => item.ValueKind != JsonValueKind.String
                                                             || !propertyNames.Contains(item.GetString()!))))
            {
                throw new JsonException();
            }

            foreach (var property in properties.EnumerateObject())
            {
                var schema = property.Value;
                var type = schema.ValueKind == JsonValueKind.Object ? ReadString(schema, "type") : null;
                if (property.Name.Length is < 1 or > 128
                    || type is not ("string" or "integer" or "number" or "boolean"))
                {
                    throw new JsonException();
                }
                if (schema.TryGetProperty("title", out var title)
                    && (title.ValueKind != JsonValueKind.String
                        || string.IsNullOrWhiteSpace(title.GetString())
                        || title.GetString()!.Length > 100))
                {
                    throw new JsonException();
                }
                if (schema.TryGetProperty("enum", out var enumValues)
                    && (type != "string"
                        || enumValues.ValueKind != JsonValueKind.Array
                        || enumValues.GetArrayLength() is < 1 or > 100
                        || enumValues.EnumerateArray().Any(item => item.ValueKind != JsonValueKind.String)))
                {
                    throw new JsonException();
                }
                if (!schema.TryGetProperty("format", out var format))
                {
                    continue;
                }

                var formatName = format.ValueKind == JsonValueKind.String ? format.GetString() : null;
                var requiredCapability = formatName switch
                {
                    "file" => "file:read:selected",
                    "theme-background" => "ui:theme",
                    _ => null,
                };
                if (type != "string"
                    || requiredCapability is null
                    || !capabilities.Contains(requiredCapability, StringComparer.Ordinal))
                {
                    throw new JsonException();
                }
            }
            return true;
        }
        catch (Exception exception) when (exception is JsonException or InvalidDataException)
        {
            findings.Add(new PackageInspectionFinding(
                "error",
                "schema.invalid",
                "命令输入 Schema 包含无效字段类型、格式或权限声明。",
                entry.FullName));
            return false;
        }
    }

    private static bool ValidateRuntime(
        JsonElement root,
        IReadOnlyDictionary<string, ZipArchiveEntry> entries,
        List<PackageInspectionFinding> findings)
    {
        if (!root.TryGetProperty("runtime", out var runtime)
            || runtime.ValueKind != JsonValueKind.Object
            || ReadString(runtime, "kind") != "process"
            || !runtime.TryGetProperty("entrypoints", out var entrypoints)
            || entrypoints.ValueKind != JsonValueKind.Object)
        {
            AddManifestError(findings, "manifest.runtime", "插件运行时必须声明 process 入口点。");
            return false;
        }

        var valid = true;
        foreach (var entrypoint in entrypoints.EnumerateObject())
        {
            var path = entrypoint.Value.ValueKind == JsonValueKind.String
                ? entrypoint.Value.GetString()
                : null;
            if (string.IsNullOrWhiteSpace(path)
                || !path.StartsWith("bin/", StringComparison.Ordinal)
                || !path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
                || !entries.TryGetValue(path, out var executable)
                || IsDirectory(executable))
            {
                AddManifestError(findings, "manifest.entrypoint", $"运行时入口 {entrypoint.Name} 无效。");
                valid = false;
            }
        }
        return valid;
    }

    private static bool ValidateLimits(
        JsonElement root,
        List<PackageInspectionFinding> findings)
    {
        if (!root.TryGetProperty("limits", out var limits)
            || limits.ValueKind != JsonValueKind.Object
            || !TryReadInt(limits, "memory_mb", out var memory)
            || !TryReadInt(limits, "cpu_percent", out var cpu)
            || !TryReadInt(limits, "command_timeout_seconds", out var timeout)
            || !TryReadInt(limits, "child_processes", out var children)
            || memory is < 64 or > 1024
            || cpu is < 5 or > 50
            || timeout is < 5 or > 600
            || children != 0)
        {
            AddManifestError(findings, "manifest.limits", "插件资源限制超出宿主允许范围。");
            return false;
        }
        return true;
    }

    private static string[] ReadCapabilities(
        JsonElement root,
        List<PackageInspectionFinding> findings,
        ref bool valid,
        out string[] required)
    {
        required = [];
        if (!root.TryGetProperty("capabilities", out var capabilities)
            || capabilities.ValueKind != JsonValueKind.Object
            || !TryReadStringArray(capabilities, "required", out required)
            || !TryReadStringArray(capabilities, "optional", out var optional))
        {
            AddManifestError(findings, "manifest.capabilities", "插件权限声明无效。");
            valid = false;
            return [];
        }

        var all = required.Concat(optional).ToArray();
        if (required.Intersect(optional, StringComparer.Ordinal).Any()
            || all.Distinct(StringComparer.Ordinal).Count() != all.Length
            || all.Any(item => !KnownCapabilities.Contains(item)))
        {
            AddManifestError(findings, "manifest.capabilities", "插件权限包含未知项或重复项。");
            valid = false;
        }
        return all;
    }

    private static bool IsHostVersion(string? value, bool allowWildcard)
    {
        if (value is null)
        {
            return false;
        }
        if (VersionPattern.IsMatch(value))
        {
            return true;
        }
        return allowWildcard
            && value.EndsWith(".x", StringComparison.Ordinal)
            && int.TryParse(value[..^2], NumberStyles.None, CultureInfo.InvariantCulture, out _);
    }

    private static bool InspectSbom(
        IReadOnlyDictionary<string, ZipArchiveEntry> entries,
        List<PackageInspectionFinding> findings)
    {
        if (!entries.TryGetValue("sbom.cdx.json", out var entry) || IsDirectory(entry))
        {
            findings.Add(new PackageInspectionFinding(
                "error",
                "sbom.missing",
                "插件包缺少 sbom.cdx.json。"));
            return false;
        }
        try
        {
            using var document = JsonDocument.Parse(ReadEntry(entry, MaximumSbomBytes));
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || ReadString(root, "bomFormat") != "CycloneDX"
                || ReadString(root, "specVersion") != "1.5"
                || !root.TryGetProperty("components", out var components)
                || components.ValueKind != JsonValueKind.Array)
            {
                throw new JsonException();
            }
            return true;
        }
        catch (Exception exception) when (exception is JsonException or InvalidDataException)
        {
            findings.Add(new PackageInspectionFinding(
                "error",
                "sbom.invalid",
                "SBOM 必须是大小受限的 CycloneDX 1.5 JSON。",
                "sbom.cdx.json"));
            return false;
        }
    }

    private static void InspectSource(
        IReadOnlyList<KeyValuePair<string, ZipArchiveEntry>> sourceFiles,
        List<PackageInspectionFinding> findings)
    {
        if (sourceFiles.Count == 0)
        {
            findings.Add(new PackageInspectionFinding(
                "error",
                "source.missing",
                "插件包未包含可供管理员审查的 source/ 文本源码。"));
            return;
        }
        if (sourceFiles.Count > MaximumSourceFiles)
        {
            findings.Add(new PackageInspectionFinding(
                "error",
                "source.too_many_files",
                $"源码文件超过 {MaximumSourceFiles} 个限制。"));
        }
        foreach (var (path, entry) in sourceFiles)
        {
            if (entry.Length > MaximumSourceFileBytes)
            {
                findings.Add(new PackageInspectionFinding(
                    "error",
                    "source.file_too_large",
                    "源码文件超过 256 KiB 限制。",
                    path));
                continue;
            }
            try
            {
                _ = new UTF8Encoding(false, true).GetString(ReadEntry(entry, MaximumSourceFileBytes));
            }
            catch (DecoderFallbackException)
            {
                findings.Add(new PackageInspectionFinding(
                    "error",
                    "source.not_utf8",
                    "源码文件不是有效 UTF-8 文本。",
                    path));
            }
        }
    }

    private static IReadOnlyList<InspectionFile> HashPackageFiles(
        IEnumerable<ZipArchiveEntry> entries,
        List<PackageInspectionFinding> findings)
    {
        var files = new List<InspectionFile>();
        foreach (var entry in entries.Where(item => !IsDirectory(item)))
        {
            try
            {
                using var stream = entry.Open();
                files.Add(new InspectionFile(
                    entry.FullName,
                    entry.Length,
                    Convert.ToHexStringLower(SHA256.HashData(stream))));
            }
            catch (InvalidDataException)
            {
                findings.Add(new PackageInspectionFinding(
                    "error",
                    "package.entry_unreadable",
                    "无法读取插件包文件项。",
                    entry.FullName));
            }
        }
        return files;
    }

    private static bool VerifySignature(
        IReadOnlyDictionary<string, ZipArchiveEntry> entries,
        IReadOnlyList<InspectionFile> files,
        byte[]? publicKey,
        List<PackageInspectionFinding> findings)
    {
        if (publicKey is null
            || !entries.TryGetValue("signature.ed25519", out var signatureEntry)
            || IsDirectory(signatureEntry))
        {
            findings.Add(new PackageInspectionFinding(
                "error",
                "signature.missing",
                "插件包缺少可验证的开发者签名。"));
            return false;
        }

        try
        {
            var signature = Convert.FromBase64String(
                Encoding.ASCII.GetString(ReadEntry(signatureEntry, 256)).Trim());
            if (signature.Length != Ed25519PrivateKeyParameters.SignatureSize)
            {
                throw new FormatException();
            }
            var payload = BuildSignaturePayload(files);
            var verifier = new Ed25519Signer();
            verifier.Init(false, new Ed25519PublicKeyParameters(publicKey));
            verifier.BlockUpdate(payload, 0, payload.Length);
            if (verifier.VerifySignature(signature))
            {
                return true;
            }
        }
        catch (Exception exception) when (exception is FormatException or InvalidDataException)
        {
        }

        findings.Add(new PackageInspectionFinding(
            "error",
            "signature.invalid",
            "开发者 Ed25519 签名无效。",
            "signature.ed25519"));
        return false;
    }

    private static byte[] BuildSignaturePayload(IEnumerable<InspectionFile> files)
    {
        var builder = new StringBuilder("PD-PDPKG-SIGNATURE-V1\n");
        foreach (var file in files
                     .Where(file => !string.Equals(
                         file.Path,
                         "signature.ed25519",
                         StringComparison.OrdinalIgnoreCase))
                     .OrderBy(file => file.Path, StringComparer.Ordinal))
        {
            builder.Append(file.Path);
            builder.Append('\n');
            builder.Append(file.Length.ToString(CultureInfo.InvariantCulture));
            builder.Append('\n');
            builder.Append(file.Sha256);
            builder.Append('\n');
        }
        return Encoding.UTF8.GetBytes(builder.ToString());
    }

    private static bool ValidateEntryPath(
        ZipArchiveEntry entry,
        List<PackageInspectionFinding> findings)
    {
        var path = entry.FullName;
        var directory = path.EndsWith("/", StringComparison.Ordinal);
        var normalized = directory ? path[..^1] : path;
        var unixFileType = (entry.ExternalAttributes >> 16) & 0xF000;
        var windowsAttributes = (FileAttributes)(entry.ExternalAttributes & 0xFFFF);
        var invalid = string.IsNullOrWhiteSpace(normalized)
            || path.Length > 512
            || path.Contains('\\')
            || path.Contains(':')
            || path.StartsWith("/", StringComparison.Ordinal)
            || path.Any(char.IsControl)
            || normalized.Split('/').Any(segment => segment is "" or "." or "..")
            || unixFileType is 0xA000 or 0x6000
            || windowsAttributes.HasFlag(FileAttributes.ReparsePoint);
        if (!invalid)
        {
            return true;
        }

        findings.Add(new PackageInspectionFinding(
            "error",
            "path.invalid",
            "插件包包含非法路径、链接或设备文件。",
            path));
        return false;
    }

    private static byte[] ReadEntry(ZipArchiveEntry entry, long maximumBytes)
    {
        if (entry.Length > maximumBytes || entry.Length > int.MaxValue)
        {
            throw new InvalidDataException();
        }
        using var stream = entry.Open();
        using var output = new MemoryStream((int)entry.Length);
        stream.CopyTo(output);
        return output.ToArray();
    }

    private static PackageInspectionReport CreateReport(
        PluginSelectedFile selected,
        string packageSha256,
        string? pluginId,
        string? version,
        PackageInspectionSummary summary,
        IReadOnlyList<PackageInspectionFinding> findings)
    {
        var status = findings.Any(item => item.Severity == "error")
            ? "failed"
            : findings.Any(item => item.Severity == "warning")
                ? "warning"
                : "passed";
        var returnedFindings = findings.Take(MaximumReturnedFindings).ToArray();
        return new PackageInspectionReport(
            status,
            selected.FileName,
            selected.Length,
            packageSha256,
            pluginId,
            version,
            summary,
            findings.Count,
            findings.Count > returnedFindings.Length,
            returnedFindings);
    }

    private static string? ReadString(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private static JsonElement? ReadArray(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Array
            ? value
            : null;

    private static bool TryReadStringArray(
        JsonElement element,
        string name,
        out string[] values)
    {
        values = [];
        if (!element.TryGetProperty(name, out var array)
            || array.ValueKind != JsonValueKind.Array
            || array.EnumerateArray().Any(item => item.ValueKind != JsonValueKind.String))
        {
            return false;
        }
        values = array.EnumerateArray().Select(item => item.GetString()!).ToArray();
        return true;
    }

    private static bool TryReadInt(JsonElement element, string name, out int value)
    {
        value = default;
        return element.TryGetProperty(name, out var property) && property.TryGetInt32(out value);
    }

    private static void AddManifestError(
        ICollection<PackageInspectionFinding> findings,
        string code,
        string message) =>
        findings.Add(new PackageInspectionFinding("error", code, message, "manifest.json"));

    private static bool IsDirectory(ZipArchiveEntry entry) =>
        entry.FullName.EndsWith("/", StringComparison.Ordinal);

    private sealed record InspectionFile(string Path, long Length, string Sha256);

    private sealed record ManifestFacts(
        bool Valid,
        string? PluginId,
        string? Version,
        byte[]? PublicKey,
        int CommandCount,
        IReadOnlyList<string> Capabilities)
    {
        public static ManifestFacts Empty { get; } = new(false, null, null, null, 0, []);
    }
}
