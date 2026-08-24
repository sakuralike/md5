using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Crypto.Signers;
using Org.BouncyCastle.Security;
using PasswordDetective.Desktop.Plugins.Packages;

if (args.Length != 2 || !File.Exists(args[0]))
{
    Console.Error.WriteLine("Usage: PdppPackageBuilder <plugin.exe> <output.pdpkg>");
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
var privateKey = new Ed25519PrivateKeyParameters(new SecureRandom());
var publicKey = privateKey.GeneratePublicKey().GetEncoded();
var manifest = new PluginManifest(
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
    ["schemas/echo.schema.json"] = Encoding.UTF8.GetBytes(
        """
        {"type":"object","required":["message"],"properties":{"message":{"type":"string","title":"消息"},"uppercase":{"type":"boolean","title":"大写"},"mode":{"type":"string","title":"模式","enum":["plain","safe"]}}}
        """),
};
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
