using System.Buffers;
using System.Security.Cryptography;
using PasswordDetective.Desktop.Models;
using System.IO;

namespace PasswordDetective.Desktop.Services;

public sealed class FileFingerprintService : IFileFingerprintService
{
    private const int BufferSize = 1024 * 1024;

    public async Task<FileFingerprintResult> CalculateAsync(
        string filePath,
        IProgress<double>? progress = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(filePath);
        var file = new FileInfo(filePath);
        if (!file.Exists)
        {
            throw new FileNotFoundException("未找到所选文件。", filePath);
        }

        await using var stream = new FileStream(
            file.FullName,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            BufferSize,
            FileOptions.Asynchronous | FileOptions.SequentialScan);
        using var sha256 = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        using var md5 = IncrementalHash.CreateHash(HashAlgorithmName.MD5);
        var buffer = ArrayPool<byte>.Shared.Rent(BufferSize);
        long processed = 0;

        try
        {
            int read;
            while ((read = await stream.ReadAsync(
                       buffer.AsMemory(0, BufferSize), cancellationToken)) > 0)
            {
                sha256.AppendData(buffer, 0, read);
                md5.AppendData(buffer, 0, read);
                processed += read;
                progress?.Report(file.Length == 0 ? 1 : (double)processed / file.Length);
            }
        }
        finally
        {
            ArrayPool<byte>.Shared.Return(buffer, clearArray: true);
        }

        progress?.Report(1);
        return new FileFingerprintResult(
            file.Name,
            file.Length,
            Convert.ToHexString(sha256.GetHashAndReset()).ToLowerInvariant(),
            Convert.ToHexString(md5.GetHashAndReset()).ToLowerInvariant(),
            DateTimeOffset.UtcNow);
    }
}
