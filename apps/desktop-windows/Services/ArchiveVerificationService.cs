using System.IO;
using PasswordDetective.Desktop.Models;
using SharpCompress.Archives;
using SharpCompress.Archives.Tar;
using SharpCompress.Common;
using SharpCompress.Compressors;
using SharpCompress.Compressors.BZip2;
using SharpCompress.Readers;

namespace PasswordDetective.Desktop.Services;

public sealed class ArchiveVerificationService : IArchiveVerificationService
{
    private readonly ArchiveVerificationLimits _limits;

    public ArchiveVerificationService(ArchiveVerificationLimits? limits = null)
    {
        _limits = limits ?? new ArchiveVerificationLimits();
        _limits.Validate();
    }

    public async Task<ArchiveVerificationResult> VerifyAsync(
        string filePath,
        string candidatePassword,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(filePath);
        ArgumentNullException.ThrowIfNull(candidatePassword);
        if (candidatePassword.Length > 1024)
        {
            throw new ArgumentException("候选密码长度超过本地验证限制。", nameof(candidatePassword));
        }

        using var linkedCancellation = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken);
        linkedCancellation.CancelAfter(_limits.VerificationTimeout);

        try
        {
            return await Task.Run(
                () => VerifyCore(filePath, candidatePassword, linkedCancellation.Token),
                linkedCancellation.Token);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return Failure(ArchiveFormatCatalog.GetArchiveFormat(filePath), "本地验证超时，已停止读取压缩包。");
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (ArchiveSafetyException exception)
        {
            return Failure(ArchiveFormatCatalog.GetArchiveFormat(filePath), exception.Message);
        }
        catch (Exception exception) when (File.Exists(filePath))
        {
            return Failure(
                ArchiveFormatCatalog.GetArchiveFormat(filePath),
                $"无法使用该候选密码完整读取压缩包，或压缩包格式不受支持/已损坏（{exception.GetType().Name}）。");
        }
    }

    private ArchiveVerificationResult VerifyCore(
        string filePath,
        string candidatePassword,
        CancellationToken cancellationToken)
    {
        var file = new FileInfo(filePath);
        if (!file.Exists)
        {
            throw new FileNotFoundException("未找到所选文件。", filePath);
        }
        if (file.Length > _limits.MaxArchiveBytes)
        {
            throw new ArchiveSafetyException(
                $"压缩包超过 {FormatByteLimit(_limits.MaxArchiveBytes)} 本地验证上限。");
        }

        var archiveFormat = ArchiveFormatCatalog.GetArchiveFormat(filePath);
        if (!ArchiveFormatCatalog.IsSupportedPath(filePath))
        {
            throw new ArchiveSafetyException(
                $"仅支持 {ArchiveFormatCatalog.SupportedFormatsDescription} 压缩包。");
        }

        if (ArchiveFormatCatalog.IsGZipPath(filePath))
        {
            return VerifyGZipCore(file, archiveFormat, candidatePassword, cancellationToken);
        }

        if (ArchiveFormatCatalog.IsBZip2Path(filePath))
        {
            return VerifyBZip2Core(file, archiveFormat, candidatePassword, cancellationToken);
        }

        using var stream = new FileStream(
            file.FullName,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            1024 * 1024,
            FileOptions.SequentialScan);
        using var archive = ArchiveFactory.OpenArchive(
            stream,
            new ReaderOptions
            {
                Password = candidatePassword,
                LeaveStreamOpen = false,
            });

        return VerifyArchiveEntries(archive, archiveFormat, cancellationToken);
    }

    private ArchiveVerificationResult VerifyGZipCore(
        FileInfo file,
        string archiveFormat,
        string candidatePassword,
        CancellationToken cancellationToken)
    {
        using var source = new FileStream(
            file.FullName,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            1024 * 1024,
            FileOptions.SequentialScan);
        using var decompressed = new System.IO.Compression.GZipStream(
            source,
            System.IO.Compression.CompressionMode.Decompress,
            leaveOpen: false);
        return VerifyCompressedStreamPayload(
            decompressed,
            archiveFormat,
            candidatePassword,
            "GZ/TGZ 压缩流已成功解压读取，但该格式本身不支持密码加密校验，不能确认候选密码正确。",
            cancellationToken);
    }

    private ArchiveVerificationResult VerifyBZip2Core(
        FileInfo file,
        string archiveFormat,
        string candidatePassword,
        CancellationToken cancellationToken)
    {
        using var source = new FileStream(
            file.FullName,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            1024 * 1024,
            FileOptions.SequentialScan);
        using var decompressed = BZip2Stream.Create(
            source,
            CompressionMode.Decompress,
            decompressConcatenated: true,
            leaveOpen: false,
            tolerateTruncatedStream: false);
        return VerifyCompressedStreamPayload(
            decompressed,
            archiveFormat,
            candidatePassword,
            "BZ/BZ2 压缩流已成功解压读取，但该格式本身不支持密码加密校验，不能确认候选密码正确。",
            cancellationToken);
    }

    private ArchiveVerificationResult VerifyCompressedStreamPayload(
        Stream decompressed,
        string archiveFormat,
        string candidatePassword,
        string nonPasswordMessage,
        CancellationToken cancellationToken)
    {
        using var payload = new MemoryStream();
        var buffer = new byte[8192];
        long expandedBytes = 0;
        int read;
        while ((read = decompressed.Read(buffer, 0, buffer.Length)) > 0)
        {
            cancellationToken.ThrowIfCancellationRequested();
            expandedBytes = checked(expandedBytes + read);
            if (expandedBytes > _limits.MaxExpandedBytes)
            {
                throw new ArchiveSafetyException(
                    $"压缩包展开内容超过 {FormatByteLimit(_limits.MaxExpandedBytes)} 安全上限。");
            }

            payload.Write(buffer, 0, read);
        }

        payload.Position = 0;
        if (TarArchive.IsTarFile(payload))
        {
            payload.Position = 0;
            using var archive = ArchiveFactory.OpenArchive(
                payload,
                new ReaderOptions
                {
                    Password = candidatePassword,
                    LeaveStreamOpen = false,
                });
            return VerifyArchiveEntries(archive, archiveFormat, cancellationToken);
        }

        if (expandedBytes == 0)
        {
            return Failure(archiveFormat, "未读取到可用于验证的压缩流内容，结果不计为成功。");
        }

        payload.Position = 0;
        var sampledBytes = ReadSample(payload, _limits.MaxSampleBytes, cancellationToken);
        return new ArchiveVerificationResult(
            false,
            archiveFormat,
            1,
            expandedBytes,
            sampledBytes,
            nonPasswordMessage,
            DateTimeOffset.UtcNow);
    }

    private ArchiveVerificationResult VerifyArchiveEntries(
        IArchive archive,
        string archiveFormat,
        CancellationToken cancellationToken)
    {
        var entryCount = 0;
        long totalExpandedBytes = 0;
        long sampledBytes = 0;
        var contentRead = false;
        var encryptedContentRead = false;
        var encryptedEntryCount = 0;
        var buffer = new byte[8192];

        foreach (var entry in archive.Entries)
        {
            cancellationToken.ThrowIfCancellationRequested();
            entryCount++;
            if (entryCount > _limits.MaxEntries)
            {
                throw new ArchiveSafetyException(
                    $"压缩包条目数超过 {_limits.MaxEntries:N0} 个本地验证上限。");
            }

            ValidateEntryPath(entry.Key);
            if (entry.IsEncrypted)
            {
                encryptedEntryCount++;
            }

            if (entry.IsDirectory)
            {
                continue;
            }

            totalExpandedBytes = checked(totalExpandedBytes + entry.Size);
            if (totalExpandedBytes > _limits.MaxExpandedBytes)
            {
                throw new ArchiveSafetyException(
                    $"压缩包声明的展开大小超过 {FormatByteLimit(_limits.MaxExpandedBytes)} 安全上限。");
            }

            var compressedSize = Math.Max(1, entry.CompressedSize);
            if (entry.Size >= _limits.RatioCheckMinimumBytes
                && (double)entry.Size / compressedSize > _limits.MaxCompressionRatio)
            {
                throw new ArchiveSafetyException("压缩包的声明压缩比超过安全上限。");
            }

            using var entryStream = entry.OpenEntryStream();
            var perEntryTarget = sampledBytes < _limits.MaxSampleBytes
                ? Math.Min(64 * 1024, _limits.MaxSampleBytes - sampledBytes)
                : 1;
            long entrySampled = 0;
            while (entrySampled < perEntryTarget)
            {
                cancellationToken.ThrowIfCancellationRequested();
                var requested = (int)Math.Min(buffer.Length, perEntryTarget - entrySampled);
                var read = entryStream.Read(buffer, 0, requested);
                if (read == 0)
                {
                    break;
                }

                contentRead = true;
                encryptedContentRead |= entry.IsEncrypted;
                entrySampled += read;
                sampledBytes += read;
            }
        }

        if (entryCount == 0 || !contentRead)
        {
            return new ArchiveVerificationResult(
                false,
                archiveFormat,
                entryCount,
                totalExpandedBytes,
                sampledBytes,
                "未读取到可用于验证的文件内容，结果不计为成功。",
                DateTimeOffset.UtcNow);
        }

        if (encryptedEntryCount == 0 || !encryptedContentRead)
        {
            return new ArchiveVerificationResult(
                false,
                archiveFormat,
                entryCount,
                totalExpandedBytes,
                sampledBytes,
                "压缩包内容已成功读取，但未检测到可验证候选密码的加密条目，不能确认密码正确。",
                DateTimeOffset.UtcNow);
        }

        return new ArchiveVerificationResult(
            true,
            archiveFormat,
            entryCount,
            totalExpandedBytes,
            sampledBytes,
            "候选密码已通过加密条目目录枚举与受控内容读取验证。",
            DateTimeOffset.UtcNow);
    }

    private static long ReadSample(
        Stream stream,
        long maximumBytes,
        CancellationToken cancellationToken)
    {
        var buffer = new byte[8192];
        long sampledBytes = 0;
        while (sampledBytes < maximumBytes)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var requested = (int)Math.Min(buffer.Length, maximumBytes - sampledBytes);
            var read = stream.Read(buffer, 0, requested);
            if (read == 0)
            {
                break;
            }

            sampledBytes += read;
        }

        return sampledBytes;
    }

    private static void ValidateEntryPath(string? entryPath)
    {
        if (string.IsNullOrWhiteSpace(entryPath))
        {
            throw new ArchiveSafetyException("压缩包包含无效条目路径。");
        }

        var normalized = entryPath.Replace('\\', '/');
        if (normalized.StartsWith("/", StringComparison.Ordinal)
            || Path.IsPathRooted(normalized)
            || normalized.Split('/', StringSplitOptions.RemoveEmptyEntries)
                .Any(segment => segment is "." or ".."))
        {
            throw new ArchiveSafetyException("压缩包包含不安全的绝对路径或路径穿越条目。");
        }
    }

    private static string FormatByteLimit(long bytes)
    {
        const long gibibyte = 1024L * 1024 * 1024;
        const long mebibyte = 1024L * 1024;
        return bytes switch
        {
            >= gibibyte when bytes % gibibyte == 0 => $"{bytes / gibibyte} GiB",
            >= mebibyte when bytes % mebibyte == 0 => $"{bytes / mebibyte} MiB",
            _ => $"{bytes:N0} 字节",
        };
    }

    private static ArchiveVerificationResult Failure(string format, string message) => new(
        false,
        format,
        0,
        0,
        0,
        message,
        DateTimeOffset.UtcNow);

    private sealed class ArchiveSafetyException(string message) : Exception(message);
}
