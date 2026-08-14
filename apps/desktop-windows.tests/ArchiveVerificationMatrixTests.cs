using System.Formats.Tar;
using System.IO;
using System.IO.Compression;
using System.Text;
using PasswordDetective.Desktop.Models;
using PasswordDetective.Desktop.Services;
using SharpCompress.Compressors.BZip2;
using SharpCompressionMode = SharpCompress.Compressors.CompressionMode;

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

    [Theory]
    [InlineData("sample.rar", "rar")]
    [InlineData("sample.tar", "tar")]
    [InlineData("sample.gz", "gz")]
    [InlineData("sample.tar.gz", "tar.gz")]
    [InlineData("sample.tgz", "tgz")]
    [InlineData("sample.bz", "bz")]
    [InlineData("sample.bz2", "bz2")]
    [InlineData("sample.tar.bz", "tar.bz")]
    [InlineData("sample.tar.bz2", "tar.bz2")]
    [InlineData("sample.tbz", "tbz")]
    [InlineData("sample.tbz2", "tbz2")]
    public void SupportedArchiveSuffixesAreRecognized(string fileName, string expectedFormat)
    {
        Assert.True(ArchiveFormatCatalog.IsSupportedPath(fileName));
        Assert.Equal(expectedFormat, ArchiveFormatCatalog.GetArchiveFormat(fileName));
    }

    [Fact]
    public async Task TarAndCompressedTarFormatsAreReadButDoNotClaimPasswordValidation()
    {
        var tarPayload = CreateTarPayload();
        var tarPath = await WriteBytesAsync("sample.tar", tarPayload);
        var tarGzPath = await CreateGZipAsync("sample.tar.gz", tarPayload);
        var tgzPath = await CreateGZipAsync("sample.tgz", tarPayload);
        var tarBz2Path = await CreateBZip2Async("sample.tar.bz2", tarPayload);
        var service = new ArchiveVerificationService();

        foreach (var path in new[] { tarPath, tarGzPath, tgzPath, tarBz2Path })
        {
            var result = await service.VerifyAsync(path, SyntheticPassword);

            Assert.False(result.Success);
            Assert.True(result.EntryCount > 0, $"{Path.GetFileName(path)}: {result.Message}");
            Assert.True(result.BytesSampled > 0, $"{Path.GetFileName(path)}: {result.Message}");
            Assert.Contains("不能确认", result.Message);
        }
    }

    [Fact]
    public async Task StandaloneGZipAndBZip2StreamsAreReadWithoutClaimingPasswordValidation()
    {
        var payload = Encoding.UTF8.GetBytes("synthetic standalone compressed stream");
        var gzipPath = await CreateGZipAsync("sample.gz", payload);
        var bzip2Path = await CreateBZip2Async("sample.bz2", payload);
        var service = new ArchiveVerificationService();

        var gzip = await service.VerifyAsync(gzipPath, SyntheticPassword);
        var bzip2 = await service.VerifyAsync(bzip2Path, SyntheticPassword);

        Assert.False(gzip.Success);
        Assert.Equal("gz", gzip.ArchiveFormat);
        Assert.True(gzip.BytesSampled > 0, gzip.Message);
        Assert.Contains("不能确认", gzip.Message);
        Assert.False(bzip2.Success);
        Assert.Equal("bz2", bzip2.ArchiveFormat);
        Assert.True(bzip2.BytesSampled > 0, bzip2.Message);
        Assert.Contains("不支持密码加密校验", bzip2.Message);
    }

    [Fact]
    public async Task CorruptAndUnsupportedArchivesAreRejectedWithoutLeakingCandidate()
    {
        var corruptPath = await WriteBytesAsync(
            "corrupt.zip",
            Encoding.UTF8.GetBytes("synthetic-corrupt-data"));
        var corruptRarPath = await WriteBytesAsync(
            "corrupt.rar",
            Encoding.UTF8.GetBytes("synthetic-corrupt-rar"));
        var unsupportedPath = await WriteBytesAsync(
            "unsupported.exe",
            Encoding.UTF8.GetBytes("synthetic-data"));
        var service = new ArchiveVerificationService();

        var corrupt = await service.VerifyAsync(corruptPath, SyntheticPassword);
        var corruptRar = await service.VerifyAsync(corruptRarPath, SyntheticPassword);
        var unsupported = await service.VerifyAsync(unsupportedPath, SyntheticPassword);

        Assert.False(corrupt.Success);
        Assert.Contains("已损坏", corrupt.Message);
        Assert.DoesNotContain(SyntheticPassword, corrupt.Message);
        Assert.False(corruptRar.Success);
        Assert.Equal("rar", corruptRar.ArchiveFormat);
        Assert.Contains("已损坏", corruptRar.Message);
        Assert.False(unsupported.Success);
        Assert.Contains(ArchiveFormatCatalog.SupportedFormatsDescription, unsupported.Message);
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

    private byte[] CreateTarPayload()
    {
        using var output = new MemoryStream();
        using (var writer = new TarWriter(output, TarEntryFormat.Pax, leaveOpen: true))
        {
            using var content = new MemoryStream(Encoding.UTF8.GetBytes("synthetic tar entry"));
            var entry = new PaxTarEntry(TarEntryType.RegularFile, "synthetic.txt")
            {
                DataStream = content,
            };
            writer.WriteEntry(entry);
        }

        return output.ToArray();
    }

    private async Task<string> CreateGZipAsync(string fileName, byte[] payload)
    {
        var path = Path.Combine(_temporaryDirectory, fileName);
        await using var output = File.Create(path);
        await using (var gzip = new GZipStream(output, CompressionLevel.Optimal, leaveOpen: false))
        {
            await gzip.WriteAsync(payload);
        }

        return path;
    }

    private async Task<string> CreateBZip2Async(string fileName, byte[] payload)
    {
        var path = Path.Combine(_temporaryDirectory, fileName);
        await using var output = File.Create(path);
        using (var bzip2 = BZip2Stream.Create(
            output,
            SharpCompressionMode.Compress,
            decompressConcatenated: false,
            leaveOpen: false,
            tolerateTruncatedStream: false))
        {
            await bzip2.WriteAsync(payload);
            bzip2.Finish();
        }

        return path;
    }

    private async Task<string> WriteBytesAsync(string fileName, byte[] payload)
    {
        var path = Path.Combine(_temporaryDirectory, fileName);
        await File.WriteAllBytesAsync(path, payload);
        return path;
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
