using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using PasswordDetective.OfficialArchiveSecurity;
using PasswordDetective.Pdpp;

namespace PasswordDetective.Desktop.Tests;

public sealed class OfficialArchiveSecurityTests
{
    [Fact]
    public void SafeArchivePassesWithoutFindings()
    {
        var bytes = CreateZip(
            ("docs/readme.txt", Encoding.UTF8.GetBytes("synthetic archive")),
            ("images/icon.png", new byte[] { 1, 2, 3, 4 }));

        var report = Inspect("safe.zip", bytes);

        Assert.Equal("passed", report.Status);
        Assert.True(report.Summary.PathSafe);
        Assert.True(report.Summary.CompressionSafe);
        Assert.Equal(2, report.Summary.FileCount);
        Assert.Empty(report.Findings);
    }

    [Fact]
    public void TraversalAndExecutableEntriesAreReported()
    {
        var bytes = CreateZip(
            ("../escape.txt", Encoding.UTF8.GetBytes("synthetic traversal")),
            ("tools/run.ps1", Encoding.UTF8.GetBytes("Write-Output synthetic")));

        var report = Inspect("suspicious.zip", bytes);

        Assert.Equal("failed", report.Status);
        Assert.False(report.Summary.PathSafe);
        Assert.Contains(report.Findings, item => item.Code == "archive.unsafe_path");
        Assert.Contains(report.Findings, item => item.Code == "archive.executable_entry");
    }

    [Fact]
    public void HighCompressionRatioIsBlocked()
    {
        var bytes = CreateZip(("repeated.bin", new byte[2 * 1024 * 1024]));

        var report = Inspect("bomb.zip", bytes);

        Assert.Equal("failed", report.Status);
        Assert.False(report.Summary.CompressionSafe);
        Assert.Contains(report.Findings, item => item.Code == "archive.compression_ratio");
    }

    private static ArchiveSecurityReport Inspect(string name, byte[] bytes) =>
        ArchiveSecurityAnalyzer.Inspect(
            new PluginSelectedFile(Guid.NewGuid().ToString("N"), name, bytes.LongLength),
            bytes,
            Convert.ToHexStringLower(SHA256.HashData(bytes)));

    private static byte[] CreateZip(params (string Name, byte[] Content)[] entries)
    {
        using var output = new MemoryStream();
        using (var archive = new ZipArchive(output, ZipArchiveMode.Create, leaveOpen: true))
        {
            foreach (var (name, content) in entries)
            {
                var entry = archive.CreateEntry(name, CompressionLevel.Optimal);
                using var stream = entry.Open();
                stream.Write(content);
            }
        }
        return output.ToArray();
    }
}
