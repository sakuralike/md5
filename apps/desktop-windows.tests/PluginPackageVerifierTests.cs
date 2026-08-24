using System.IO.Compression;
using System.IO;
using System.Text;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Permissions;

namespace PasswordDetective.Desktop.Tests;

public sealed class PluginPackageVerifierTests : IDisposable
{
    private readonly string _directory = Path.Combine(
        Path.GetTempPath(),
        "password-detective-package-tests",
        Guid.NewGuid().ToString("N"));
    private readonly PluginPackageTestFactory _factory = new();

    public PluginPackageVerifierTests() => Directory.CreateDirectory(_directory);

    [Fact]
    public async Task SignedPackageReturnsCurrentArchitectureInspection()
    {
        var path = _factory.Create(_directory);

        var inspection = await new PluginPackageVerifier().VerifyAsync(path);

        Assert.Equal("com.synthetic.local-plugin", inspection.Manifest.PluginId);
        Assert.Equal("1.0.0", inspection.Manifest.Version);
        Assert.EndsWith("plugin.exe", inspection.EntryPointPath, StringComparison.Ordinal);
        Assert.Equal(64, inspection.PackageSha256.Length);
        Assert.Equal(64, inspection.PublisherKeyFingerprint.Length);
        Assert.Contains(inspection.Files, file => file.Path == PluginPackageVerifier.ManifestPath);
        Assert.Contains(inspection.Files, file => file.Path == PluginPackageSignature.SignaturePath);
    }

    [Fact]
    public async Task TamperedSignatureIsRejected()
    {
        var path = _factory.Create(
            _directory,
            mutateArchive: archive =>
            {
                var entry = archive.GetEntry(PluginPackageSignature.SignaturePath)!;
                entry.Delete();
                var replacement = archive.CreateEntry(PluginPackageSignature.SignaturePath);
                using var writer = new StreamWriter(replacement.Open());
                writer.Write(Convert.ToBase64String(new byte[64]));
            });

        var exception = await Assert.ThrowsAsync<PluginPackageException>(
            () => new PluginPackageVerifier().VerifyAsync(path));

        Assert.Contains("签名无效", exception.Message);
    }

    [Fact]
    public async Task TraversalAndCaseInsensitiveDuplicatesAreRejectedBeforeExtraction()
    {
        var traversal = _factory.Create(
            _directory,
            additionalFiles: new Dictionary<string, byte[]>
            {
                ["../escape.txt"] = Encoding.UTF8.GetBytes("synthetic traversal"),
            });
        var duplicate = _factory.Create(
            _directory,
            mutateArchive: archive =>
            {
                var entry = archive.CreateEntry("MANIFEST.JSON");
                using var writer = new StreamWriter(entry.Open());
                writer.Write("{}");
            });

        var traversalError = await Assert.ThrowsAsync<PluginPackageException>(
            () => new PluginPackageVerifier().VerifyAsync(traversal));
        var duplicateError = await Assert.ThrowsAsync<PluginPackageException>(
            () => new PluginPackageVerifier().VerifyAsync(duplicate));

        Assert.Contains("路径穿越", traversalError.Message);
        Assert.Contains("重复", duplicateError.Message);
    }

    [Fact]
    public async Task SymlinkAndCompressionBombEntriesAreRejected()
    {
        var symlink = _factory.Create(
            _directory,
            mutateArchive: archive =>
            {
                var entry = archive.CreateEntry("bin/windows-x64/link.exe");
                entry.ExternalAttributes = 0xA000 << 16;
                using var writer = new StreamWriter(entry.Open());
                writer.Write("target");
            });
        var compressed = _factory.Create(
            _directory,
            additionalFiles: new Dictionary<string, byte[]>
            {
                ["assets/repeated.bin"] = new byte[2 * 1024 * 1024],
            });

        var symlinkError = await Assert.ThrowsAsync<PluginPackageException>(
            () => new PluginPackageVerifier().VerifyAsync(symlink));
        var compressionError = await Assert.ThrowsAsync<PluginPackageException>(
            () => new PluginPackageVerifier().VerifyAsync(compressed));

        Assert.Contains("符号链接", symlinkError.Message);
        Assert.Contains("压缩比", compressionError.Message);
    }

    [Fact]
    public async Task PackageWithUnsupportedRequiredCapabilityCannotBeGrantedLocally()
    {
        var path = _factory.Create(
            _directory,
            requiredCapabilities: ["ui:command", "network:internet"]);
        var inspection = await new PluginPackageVerifier().VerifyAsync(path);

        var decision = new PluginPermissionPolicy().Evaluate(
            inspection.Manifest,
            ["ui:command", "network:internet"]);

        Assert.Equal(["network:internet"], decision.DeniedRequired);
        Assert.Equal(["ui:command"], decision.Granted);
    }

    [Fact]
    public async Task FileSchemaRequiresCapabilityAndDirectorySchemaIsRejected()
    {
        var fileWithoutCapability = _factory.Create(
            _directory,
            pluginId: "com.synthetic.file-without-capability",
            runtimeFiles: new Dictionary<string, byte[]>
            {
                ["schemas/echo.schema.json"] = Encoding.UTF8.GetBytes(
                    """{"type":"object","properties":{"file":{"type":"string","format":"file"}}}"""),
            });
        var directorySchema = _factory.Create(
            _directory,
            pluginId: "com.synthetic.directory-schema",
            requiredCapabilities: ["ui:command", "file:read:selected"],
            runtimeFiles: new Dictionary<string, byte[]>
            {
                ["schemas/echo.schema.json"] = Encoding.UTF8.GetBytes(
                    """{"type":"object","properties":{"directory":{"type":"string","format":"directory"}}}"""),
            });

        var capabilityError = await Assert.ThrowsAsync<PluginPackageException>(
            () => new PluginPackageVerifier().VerifyAsync(fileWithoutCapability));
        var directoryError = await Assert.ThrowsAsync<PluginPackageException>(
            () => new PluginPackageVerifier().VerifyAsync(directorySchema));

        Assert.Contains("file:read:selected", capabilityError.Message);
        Assert.Contains("不授予目录枚举", directoryError.Message);
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory))
        {
            Directory.Delete(_directory, recursive: true);
        }
    }
}
