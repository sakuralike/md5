using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Crypto.Signers;
using Org.BouncyCastle.Security;
using PasswordDetective.Desktop.Plugins.Packages;

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
Console.WriteLine(
    $"Created {inspection.Manifest.PluginId} {inspection.Manifest.Version}: {outputPath}");
return 0;
