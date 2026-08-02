using System.IO;
using SharpCompress.Archives;
using SharpCompress.Common;
using SharpCompress.Readers;
using PasswordDetective.Desktop.Models;

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
            return Failure(GetArchiveFormat(filePath), "本地验证超时，已停止读取压缩包。");
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (ArchiveSafetyException exception)
        {
            return Failure(GetArchiveFormat(filePath), exception.Message);
        }
        catch (Exception) when (File.Exists(filePath))
        {
            return Failure(
                GetArchiveFormat(filePath),
                "无法使用该候选密码完整读取压缩包，或压缩包格式不受支持/已损坏。");
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

        var archiveFormat = GetArchiveFormat(filePath);
        if (archiveFormat == "unknown")
        {
            throw new ArchiveSafetyException("仅支持 ZIP 与 7z 压缩包。");
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

        var entryCount = 0;
        long totalExpandedBytes = 0;
        long sampledBytes = 0;
        var contentRead = false;
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

        return new ArchiveVerificationResult(
            true,
            archiveFormat,
            entryCount,
            totalExpandedBytes,
            sampledBytes,
            "候选密码已通过本地目录枚举与受控内容读取验证。",
            DateTimeOffset.UtcNow);
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

    private static string GetArchiveFormat(string filePath) =>
        Path.GetExtension(filePath).ToLowerInvariant() switch
        {
            ".zip" => "zip",
            ".7z" => "7z",
            _ => "unknown",
        };

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
