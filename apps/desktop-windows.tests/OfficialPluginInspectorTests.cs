using System.IO;
using System.Security.Cryptography;
using System.Text;
using PasswordDetective.OfficialPluginInspector;
using PasswordDetective.Pdpp;

namespace PasswordDetective.Desktop.Tests;

public sealed class OfficialPluginInspectorTests : IDisposable
{
    private readonly string _directory = Path.Combine(
        Path.GetTempPath(),
        "password-detective-official-inspector-tests",
        Guid.NewGuid().ToString("N"));
    private readonly PluginPackageTestFactory _factory = new();

    public OfficialPluginInspectorTests() => Directory.CreateDirectory(_directory);

    [Fact]
    public async Task SignedPackageWithSbomAndSourcePassesInspection()
    {
        var package = _factory.Create(
            _directory,
            additionalFiles: RequiredReviewFiles());

        var report = await InspectAsync(package);

        Assert.Equal("passed", report.Status);
        Assert.True(report.Summary.ManifestValid);
        Assert.True(report.Summary.SignatureValid);
        Assert.True(report.Summary.SbomValid);
        Assert.True(report.Summary.SourceIncluded);
        Assert.Empty(report.Findings);
    }

    [Fact]
    public async Task TraversalEntryFailsInspection()
    {
        var files = RequiredReviewFiles();
        files["../escape.txt"] = Encoding.UTF8.GetBytes("synthetic traversal");
        var package = _factory.Create(_directory, additionalFiles: files);

        var report = await InspectAsync(package);

        Assert.Equal("failed", report.Status);
        Assert.Contains(report.Findings, item => item.Code == "path.invalid");
    }

    [Fact]
    public async Task PackageWithoutReviewSourceFailsInspection()
    {
        var package = _factory.Create(
            _directory,
            additionalFiles: new Dictionary<string, byte[]>
            {
                ["sbom.cdx.json"] = SbomBytes(),
            });

        var report = await InspectAsync(package);

        Assert.Equal("failed", report.Status);
        Assert.False(report.Summary.SourceIncluded);
        Assert.Contains(report.Findings, item => item.Code == "source.missing");
    }

    [Fact]
    public async Task UnsupportedCommandSchemaFailsInspection()
    {
        var package = _factory.Create(
            _directory,
            commandSchema: Encoding.UTF8.GetBytes(
                """{"type":"object","properties":{"items":{"type":"array"}}}"""),
            additionalFiles: RequiredReviewFiles());

        var report = await InspectAsync(package);

        Assert.Equal("failed", report.Status);
        Assert.Contains(report.Findings, item => item.Code == "schema.invalid");
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory))
        {
            Directory.Delete(_directory, recursive: true);
        }
    }

    private static async Task<PackageInspectionReport> InspectAsync(string package)
    {
        var bytes = await File.ReadAllBytesAsync(package);
        return PackageInspector.Inspect(
            new PluginSelectedFile(
                Guid.NewGuid().ToString("N"),
                Path.GetFileName(package),
                bytes.LongLength),
            bytes,
            Convert.ToHexStringLower(SHA256.HashData(bytes)));
    }

    private static Dictionary<string, byte[]> RequiredReviewFiles() => new(StringComparer.Ordinal)
    {
        ["sbom.cdx.json"] = SbomBytes(),
        ["source/Program.cs"] = Encoding.UTF8.GetBytes("internal static class SyntheticSource { }")
    };

    private static byte[] SbomBytes() => Encoding.UTF8.GetBytes(
        """
        {"bomFormat":"CycloneDX","specVersion":"1.5","version":1,"components":[]}
        """);
}
