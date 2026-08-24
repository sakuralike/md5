using System.IO.Compression;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Crypto.Signers;
using Org.BouncyCastle.Security;
using PasswordDetective.Desktop.Plugins.Packages;

namespace PasswordDetective.Desktop.Tests;

internal sealed class PluginPackageTestFactory
{
    private readonly Ed25519PrivateKeyParameters _privateKey = new(new SecureRandom());

    public string Create(
        string directory,
        string version = "1.0.0",
        string pluginId = "com.synthetic.local-plugin",
        IReadOnlyList<string>? requiredCapabilities = null,
        IReadOnlyList<string>? optionalCapabilities = null,
        IReadOnlyDictionary<string, byte[]>? runtimeFiles = null,
        IReadOnlyDictionary<string, byte[]>? additionalFiles = null,
        Action<ZipArchive>? mutateArchive = null)
    {
        Directory.CreateDirectory(directory);
        var packagePath = Path.Combine(directory, $"{pluginId}-{version}-{Guid.NewGuid():N}.pdpkg");
        var publicKey = _privateKey.GeneratePublicKey().GetEncoded();
        var manifest = new PluginManifest(
            PluginPackageVerifier.ManifestSchema,
            pluginId,
            version,
            "合成本地插件",
            "仅用于本地插件包、安装与隔离测试。",
            "synthetic-ed25519-v1",
            Convert.ToBase64String(publicKey),
            new PluginProtocolRange(1, 1),
            new PluginHostRange("0.1.0", "0.x"),
            new PluginRuntimeManifest(
                "process",
                new Dictionary<string, string>
                {
                    ["windows-x64"] = "bin/windows-x64/plugin.exe",
                    ["windows-arm64"] = "bin/windows-arm64/plugin.exe",
                }),
            [new PluginCommandManifest("echo", "回显输入", "schemas/echo.schema.json")],
            new PluginCapabilitiesManifest(
                requiredCapabilities ?? ["ui:command"],
                optionalCapabilities ?? ["storage:private"]),
            new PluginLimitsManifest(128, 25, 30, 0));
        var files = new Dictionary<string, byte[]>(StringComparer.Ordinal)
        {
            [PluginPackageVerifier.ManifestPath] = JsonSerializer.SerializeToUtf8Bytes(manifest),
            ["bin/windows-x64/plugin.exe"] = Encoding.UTF8.GetBytes("MZ-synthetic-x64-plugin"),
            ["bin/windows-arm64/plugin.exe"] = Encoding.UTF8.GetBytes("MZ-synthetic-arm64-plugin"),
            ["schemas/echo.schema.json"] = Encoding.UTF8.GetBytes(
                """
                {"type":"object","required":["message"],"properties":{"message":{"type":"string","title":"消息"},"repeat":{"type":"integer","title":"次数"},"uppercase":{"type":"boolean","title":"大写"},"mode":{"type":"string","title":"模式","enum":["plain","safe"]}}}
                """),
        };
        if (runtimeFiles is not null)
        {
            foreach (var (path, content) in runtimeFiles)
            {
                files[path] = content;
            }
        }

        if (additionalFiles is not null)
        {
            foreach (var (path, content) in additionalFiles)
            {
                files.Add(path, content);
            }
        }

        var packageFiles = files.Select(pair => new PluginPackageFile(
                pair.Key,
                pair.Value.LongLength,
                Convert.ToHexStringLower(SHA256.HashData(pair.Value))))
            .ToArray();
        var payload = PluginPackageSignature.BuildPayload(packageFiles);
        var signer = new Ed25519Signer();
        signer.Init(forSigning: true, _privateKey);
        signer.BlockUpdate(payload, 0, payload.Length);
        var signature = signer.GenerateSignature();

        using (var archive = ZipFile.Open(packagePath, ZipArchiveMode.Create))
        {
            foreach (var (path, content) in files)
            {
                var entry = archive.CreateEntry(path, CompressionLevel.Optimal);
                using var stream = entry.Open();
                stream.Write(content);
            }

            var signatureEntry = archive.CreateEntry(
                PluginPackageSignature.SignaturePath,
                CompressionLevel.NoCompression);
            using (var writer = new StreamWriter(
                       signatureEntry.Open(),
                       new UTF8Encoding(encoderShouldEmitUTF8Identifier: false)))
            {
                writer.Write(Convert.ToBase64String(signature));
            }
        }

        if (mutateArchive is not null)
        {
            using var archive = ZipFile.Open(packagePath, ZipArchiveMode.Update);
            mutateArchive(archive);
        }

        return packagePath;
    }
}
