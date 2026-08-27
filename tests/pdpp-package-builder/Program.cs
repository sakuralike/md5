using System.IO.Compression;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Crypto.Signers;
using Org.BouncyCastle.Security;
using PasswordDetective.Desktop.Plugins;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Protocol;
using PasswordDetective.Desktop.Plugins.Windows;

if (args.Length is not (2 or 6) || !File.Exists(args[0]))
{
    Console.Error.WriteLine("Usage: PdppPackageBuilder <plugin.exe> <output.pdpkg> [<manifest.json> <schema.json> <sbom.cdx.json> <private-key-base64>]");
    return 2;
}

var executablePath = Path.GetFullPath(args[0]);
var outputPath = Path.GetFullPath(args[1]);
if (!string.Equals(Path.GetExtension(outputPath), ".pdpkg", StringComparison.OrdinalIgnoreCase))
{
    Console.Error.WriteLine("Output path must use the .pdpkg extension.");
    return 3;
}

Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
var privateKey = args.Length == 6
    ? new Ed25519PrivateKeyParameters(Convert.FromBase64String(args[5]), 0)
    : new Ed25519PrivateKeyParameters(new SecureRandom());
var publicKey = privateKey.GeneratePublicKey().GetEncoded();
var manifest = args.Length == 6
    ? JsonSerializer.Deserialize<PluginManifest>(
        File.ReadAllText(args[2])
            .Replace("$PUBLISHER_PUBLIC_KEY", Convert.ToBase64String(publicKey), StringComparison.Ordinal)
            .Replace("$PUBLISHER_KEY_ID", Environment.GetEnvironmentVariable("PDPP_PUBLISHER_KEY_ID") ?? string.Empty, StringComparison.Ordinal))
        ?? throw new InvalidOperationException("Custom manifest is invalid.")
    : new PluginManifest(
    PluginPackageVerifier.ManifestSchema,
    "com.passworddetective.synthetic-echo",
    "1.0.0",
    "合成回显插件",
    "密码侦探社官方协议与本地安装示例插件。",
    "generated-example-ed25519-v1",
    Convert.ToBase64String(publicKey),
    new PluginProtocolRange(1, 1),
    new PluginHostRange("0.1.0", "0.x"),
    new PluginRuntimeManifest(
        "process",
        new Dictionary<string, string>
        {
            ["windows-x64"] = "bin/windows-x64/plugin.exe",
        }),
    [new PluginCommandManifest("echo", "回显输入", "schemas/echo.schema.json")],
    new PluginCapabilitiesManifest(["ui:command"], ["storage:private"]),
    new PluginLimitsManifest(128, 25, 30, 0));
var files = new Dictionary<string, byte[]>(StringComparer.Ordinal)
{
    [PluginPackageVerifier.ManifestPath] = JsonSerializer.SerializeToUtf8Bytes(manifest),
    ["bin/windows-x64/plugin.exe"] = await File.ReadAllBytesAsync(executablePath),
    ["sbom.cdx.json"] = args.Length == 6
        ? await File.ReadAllBytesAsync(args[4])
        : Encoding.UTF8.GetBytes(
        """
        {"bomFormat":"CycloneDX","specVersion":"1.5","version":1,"components":[]}
        """),
};
if (args.Length == 6)
{
    var pluginDirectory = Path.GetDirectoryName(args[2])!;
    var schemaRoot = Path.GetDirectoryName(Path.GetFullPath(args[3]))!;
    foreach (var command in manifest.Commands)
    {
        if (!command.InputSchema.StartsWith("schemas/", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Command schema path must be inside schemas/.");
        }
        var relativeSchema = command.InputSchema["schemas/".Length..]
            .Replace('/', Path.DirectorySeparatorChar);
        var schemaPath = Path.GetFullPath(Path.Combine(schemaRoot, relativeSchema));
        var containedRoot = Path.GetFullPath(schemaRoot).TrimEnd(Path.DirectorySeparatorChar)
            + Path.DirectorySeparatorChar;
        if (!schemaPath.StartsWith(containedRoot, StringComparison.OrdinalIgnoreCase)
            || !File.Exists(schemaPath))
        {
            throw new InvalidOperationException($"Command schema was not found: {command.InputSchema}");
        }
        files[command.InputSchema] = await File.ReadAllBytesAsync(schemaPath);
    }

    var assetDirectory = Path.Combine(pluginDirectory, "assets");
    if (Directory.Exists(assetDirectory))
    {
        foreach (var assetPath in Directory.EnumerateFiles(assetDirectory, "*", SearchOption.AllDirectories)
                     .Order(StringComparer.OrdinalIgnoreCase))
        {
            var relative = Path.GetRelativePath(assetDirectory, assetPath)
                .Replace(Path.DirectorySeparatorChar, '/');
            files[$"assets/{relative}"] = await File.ReadAllBytesAsync(assetPath);
        }
    }

    foreach (var sourcePath in Directory.EnumerateFiles(pluginDirectory, "*", SearchOption.AllDirectories)
                 .Where(path => Path.GetExtension(path) is ".cs" or ".csproj")
                 .Where(path => !Path.GetRelativePath(pluginDirectory, path)
                     .Split(Path.DirectorySeparatorChar)
                     .Any(segment => segment is "bin" or "obj"))
                 .Order(StringComparer.OrdinalIgnoreCase))
    {
        var relative = Path.GetRelativePath(pluginDirectory, sourcePath)
            .Replace(Path.DirectorySeparatorChar, '/');
        files[$"source/{relative}"] = await File.ReadAllBytesAsync(sourcePath);
    }
}
else
{
    files["schemas/echo.schema.json"] = Encoding.UTF8.GetBytes(
        """
        {"type":"object","required":["message"],"properties":{"message":{"type":"string","title":"消息"},"uppercase":{"type":"boolean","title":"大写"},"mode":{"type":"string","title":"模式","enum":["plain","safe"]}}}
        """);
}
var sourceCommit = ResolveSourceCommit(args.Length == 6 ? Path.GetDirectoryName(args[2])! : null);
var sourceFiles = FileRecords(files, path => path.StartsWith("source/", StringComparison.Ordinal));
var binaries = FileRecords(files, path => path.StartsWith("bin/", StringComparison.Ordinal));
var sbom = FileRecord("sbom.cdx.json", files["sbom.cdx.json"]);
files["provenance.json"] = JsonSerializer.SerializeToUtf8Bytes(new
{
    schema = "pd.plugin.provenance/v1",
    source_commit = sourceCommit,
    source_files = sourceFiles,
    sbom,
    binaries,
});
var packageFiles = files.Select(pair => new PluginPackageFile(
        pair.Key,
        pair.Value.LongLength,
        Convert.ToHexStringLower(SHA256.HashData(pair.Value))))
    .ToArray();
var payload = PluginPackageSignature.BuildPayload(packageFiles);
var signer = new Ed25519Signer();
signer.Init(forSigning: true, privateKey);
signer.BlockUpdate(payload, 0, payload.Length);
var signature = signer.GenerateSignature();

if (File.Exists(outputPath))
{
    File.Delete(outputPath);
}

using (var archive = ZipFile.Open(outputPath, ZipArchiveMode.Create))
{
    foreach (var (path, content) in files)
    {
        var entry = archive.CreateEntry(path, CompressionLevel.Optimal);
        await using var stream = entry.Open();
        await stream.WriteAsync(content);
    }

    var signatureEntry = archive.CreateEntry(
        PluginPackageSignature.SignaturePath,
        CompressionLevel.NoCompression);
    await using var signatureStream = signatureEntry.Open();
    await signatureStream.WriteAsync(Encoding.ASCII.GetBytes(Convert.ToBase64String(signature)));
}

var inspection = await new PluginPackageVerifier().VerifyAsync(outputPath);
await ValidateAppContainerAsync(outputPath, inspection);
Console.WriteLine(
    $"Created {inspection.Manifest.PluginId} {inspection.Manifest.Version}: {outputPath}");
return 0;

static object[] FileRecords(
    IReadOnlyDictionary<string, byte[]> files,
    Func<string, bool> predicate) =>
    files.Where(pair => predicate(pair.Key))
        .OrderBy(pair => pair.Key, StringComparer.Ordinal)
        .Select(pair => FileRecord(pair.Key, pair.Value))
        .ToArray();

static object FileRecord(string path, byte[] content) => new
{
    path,
    size_bytes = content.LongLength,
    sha256 = Convert.ToHexStringLower(SHA256.HashData(content)),
};

static string ResolveSourceCommit(string? repositoryPath)
{
    var configured = Environment.GetEnvironmentVariable("PDPP_SOURCE_COMMIT")?.Trim().ToLowerInvariant();
    if (IsCommit(configured))
    {
        return configured!;
    }
    if (repositoryPath is not null)
    {
        using var process = Process.Start(new ProcessStartInfo
        {
            FileName = "git",
            Arguments = $"-C \"{repositoryPath}\" rev-parse HEAD",
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        });
        process?.WaitForExit();
        var detected = process?.StandardOutput.ReadToEnd().Trim().ToLowerInvariant();
        if (process?.ExitCode == 0 && IsCommit(detected))
        {
            return detected!;
        }
    }
    return new string('0', 40);
}

static bool IsCommit(string? value) =>
    value is { Length: 40 or 64 } && value.All(Uri.IsHexDigit);

static async Task ValidateAppContainerAsync(
    string packagePath,
    PluginPackageInspection inspection)
{
    var root = Path.Combine(
        Path.GetTempPath(),
        "password-detective-package-gate",
        Guid.NewGuid().ToString("N"));
    try
    {
        Directory.CreateDirectory(root);
        ZipFile.ExtractToDirectory(packagePath, root);
        var executable = Path.Combine(
            root,
            inspection.EntryPointPath.Replace('/', Path.DirectorySeparatorChar));
        var options = new PluginProcessStartOptions
        {
            PluginId = inspection.Manifest.PluginId,
            ExecutablePath = executable,
            WorkingDirectory = root,
            Arguments = ["--pdpp", "--manifest", Path.Combine(root, PluginPackageVerifier.ManifestPath)],
            MemoryLimitBytes = inspection.Manifest.Limits.MemoryMb * 1024L * 1024L,
            ActiveProcessLimit = 1,
            CpuRatePercent = inspection.Manifest.Limits.CpuPercent,
            ReadOnlyDirectories = [root],
            DeleteAppContainerProfileOnDispose = true,
        };
        await using var host = await PluginProcessHost.StartAsync(options);
        var initialized = await host.InitializeAsync(
            PluginPackageVerifier.HostVersion,
            inspection.Manifest.Capabilities.Required,
            TimeSpan.FromSeconds(15));
        var migration = await host.InvokeAsync<PdppMigrateParams, PdppMigrateResult>(
            PdppProtocol.MigrateMethod,
            new PdppMigrateParams(inspection.Manifest.Version, inspection.Manifest.Version),
            TimeSpan.FromSeconds(10));
        var health = await host.InvokeAsync<object, PdppHealthResult>(
            PdppProtocol.HealthCheckMethod,
            new { },
            TimeSpan.FromSeconds(10));
        if (!host.IsAppContainer
            || initialized.PluginId != inspection.Manifest.PluginId
            || migration.Status is not ("migrated" or "not_required")
            || migration.Status == "not_required" && (migration.Steps?.Count ?? 0) != 0
            || health.Status != "healthy")
        {
            throw new InvalidOperationException("PDPP AppContainer package gate failed.");
        }
    }
    finally
    {
        if (Directory.Exists(root))
        {
            Directory.Delete(root, recursive: true);
        }
    }
}
