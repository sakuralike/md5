using System.IO;
using System.IO.Compression;
using System.Text;
using PasswordDetective.Desktop.Models;
using PasswordDetective.Desktop.Services;

namespace PasswordDetective.Desktop.Tests;

public sealed class ArchiveVerificationMatrixTests : IDisposable
{
    private const string SyntheticPassword = "synthetic-password";
    private readonly string _temporaryDirectory = Path.Combine(
        Path.GetTempPath(),
        "password-detective-archive-matrix",
        Guid.NewGuid().ToString("N"));

    public ArchiveVerificationMatrixTests() => Directory.CreateDirectory(_temporaryDirectory);

    [Theory]
    [InlineData("encrypted-valid.zip", "zip")]
    [InlineData("encrypted-valid.7z", "7z")]
    public async Task EncryptedFixturesAcceptCorrectAndRejectWrongPassword(
        string fixtureName,
        string expectedFormat)
    {
        var service = new ArchiveVerificationService();
        var fixturePath = Path.Combine(AppContext.BaseDirectory, "Fixtures", fixtureName);

        var accepted = await service.VerifyAsync(fixturePath, SyntheticPassword);
        var rejected = await service.VerifyAsync(fixturePath, "synthetic-wrong-password");

        Assert.True(accepted.Success, accepted.Message);
        Assert.Equal(expectedFormat, accepted.ArchiveFormat);
        Assert.True(accepted.BytesSampled > 0);
        Assert.False(rejected.Success);
        Assert.Equal(expectedFormat, rejected.ArchiveFormat);
    }

    [Fact]
    public async Task CorruptAndUnsupportedArchivesAreRejectedWithoutLeakingCandidate()
    {
        var corruptPath = Path.Combine(_temporaryDirectory, "corrupt.zip");
        await File.WriteAllBytesAsync(corruptPath, Encoding.UTF8.GetBytes("synthetic-corrupt-data"));
        var unsupportedPath = Path.Combine(_temporaryDirectory, "unsupported.rar");
        await File.WriteAllBytesAsync(unsupportedPath, Encoding.UTF8.GetBytes("synthetic-data"));
        var service = new ArchiveVerificationService();

        var corrupt = await service.VerifyAsync(corruptPath, SyntheticPassword);
        var unsupported = await service.VerifyAsync(unsupportedPath, SyntheticPassword);

        Assert.False(corrupt.Success);
        Assert.Contains("已损坏", corrupt.Message);
        Assert.DoesNotContain(SyntheticPassword, corrupt.Message);
        Assert.False(unsupported.Success);
        Assert.Contains("ZIP 与 7z", unsupported.Message);
    }

    [Fact]
    public async Task ConfigurableLimitsRejectArchiveSizeEntryCountExpandedSizeAndRatio()
    {
        var singleEntryPath = await CreateZipAsync(
            "single.zip",
            ("synthetic.txt", Enumerable.Repeat((byte)'A', 4096).ToArray()));
        var twoEntriesPath = await CreateZipAsync(
            "two-entries.zip",
            ("first.txt", Encoding.UTF8.GetBytes("first synthetic entry")),
            ("second.txt", Encoding.UTF8.GetBytes("second synthetic entry")));

        var archiveSize = await new ArchiveVerificationService(new ArchiveVerificationLimits
        {
            MaxArchiveBytes = 16,
        }).VerifyAsync(singleEntryPath, SyntheticPassword);
        var entryCount = await new ArchiveVerificationService(new ArchiveVerificationLimits
        {
            MaxEntries = 1,
        }).VerifyAsync(twoEntriesPath, SyntheticPassword);
        var expandedSize = await new ArchiveVerificationService(new ArchiveVerificationLimits
        {
            MaxExpandedBytes = 32,
        }).VerifyAsync(singleEntryPath, SyntheticPassword);
        var compressionRatio = await new ArchiveVerificationService(new ArchiveVerificationLimits
        {
            RatioCheckMinimumBytes = 1,
            MaxCompressionRatio = 2,
        }).VerifyAsync(singleEntryPath, SyntheticPassword);

        Assert.False(archiveSize.Success);
        Assert.Contains("16 字节", archiveSize.Message);
        Assert.False(entryCount.Success);
        Assert.Contains("条目数", entryCount.Message);
        Assert.False(expandedSize.Success);
        Assert.Contains("展开大小", expandedSize.Message);
        Assert.False(compressionRatio.Success);
        Assert.Contains("压缩比", compressionRatio.Message);
    }

    [Fact]
    public async Task CallerCancellationIsPropagated()
    {
        var archivePath = await CreateZipAsync(
            "cancel.zip",
            ("synthetic.txt", Encoding.UTF8.GetBytes("synthetic cancellation content")));
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => new ArchiveVerificationService().VerifyAsync(
                archivePath,
                SyntheticPassword,
                cancellation.Token));
    }

    private async Task<string> CreateZipAsync(
        string fileName,
        params (string Name, byte[] Content)[] entries)
    {
        var path = Path.Combine(_temporaryDirectory, fileName);
        using var archive = ZipFile.Open(path, ZipArchiveMode.Create);
        foreach (var (name, content) in entries)
        {
            var entry = archive.CreateEntry(name, CompressionLevel.Optimal);
            await using var stream = entry.Open();
            await stream.WriteAsync(content);
        }
        return path;
    }

    public void Dispose()
    {
        if (Directory.Exists(_temporaryDirectory))
        {
            Directory.Delete(_temporaryDirectory, recursive: true);
        }
    }
}
