using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using SharpCompress.Archives;
using SharpCompress.Common;
using SharpCompress.Readers;
using PasswordDetective.Pdpp;

namespace PasswordDetective.OfficialArchiveSecurity;

public sealed record ArchiveSecurityFinding(
    string Severity,
    string Code,
    string Message,
    string? Path = null);

public sealed record ArchiveSecuritySummary(
    int EntryCount,
    int FileCount,
    long ExpandedSizeBytes,
    long SampledBytes,
    int EncryptedEntryCount,
    int ExecutableEntryCount,
    bool PathSafe,
    bool CompressionSafe);

public sealed record ArchiveSecurityReport(
    string Status,
    string FileName,
    string Format,
    long ArchiveSizeBytes,
    string ArchiveSha256,
    ArchiveSecuritySummary Summary,
    int FindingCount,
    bool FindingsTruncated,
    IReadOnlyList<ArchiveSecurityFinding> Findings);

public static class ArchiveSecurityAnalyzer
{
    public const long MaximumReadableArchiveBytes = 128L * 1024 * 1024;
    private const long MaximumExpandedBytes = 1024L * 1024 * 1024;
    private const int MaximumEntries = 2048;
    private const long MaximumSingleEntryBytes = 256L * 1024 * 1024;
    private const double MaximumCompressionRatio = 100d;
    private const long MaximumSampleBytes = 1024L * 1024;
    private const int MaximumReturnedFindings = 200;
    private static readonly IReadOnlySet<string> ExecutableExtensions = new HashSet<string>(
        [".exe", ".dll", ".sys", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".scr"],
        StringComparer.OrdinalIgnoreCase);

    public static ArchiveSecurityReport CreateSizeFailure(
        PluginSelectedFile selected,
        string archiveSha256) =>
        CreateReport(
            selected,
            archiveSha256,
            GetFormat(selected.FileName),
            new ArchiveSecuritySummary(0, 0, 0, 0, 0, 0, false, false),
            [new ArchiveSecurityFinding(
                "error",
                "archive.too_large",
                $"归档超过安全检查器 {MaximumReadableArchiveBytes / 1024 / 1024} MiB 读取上限。")]);

    public static ArchiveSecurityReport Inspect(
        PluginSelectedFile selected,
        byte[] archiveBytes,
        string archiveSha256)
    {
        var findings = new List<ArchiveSecurityFinding>();
        var format = GetFormat(selected.FileName);
        if (archiveBytes.Length != selected.Length)
        {
            findings.Add(new ArchiveSecurityFinding(
                "error",
                "archive.size_mismatch",
                "宿主提供的归档长度与读取结果不一致。"));
        }

        try
        {
            using var archive = ArchiveFactory.OpenArchive(
                new MemoryStream(archiveBytes, writable: false),
                new ReaderOptions { LeaveStreamOpen = false });
            var entryCount = 0;
            var fileCount = 0;
            var encryptedCount = 0;
            var executableCount = 0;
            var expandedBytes = 0L;
            var sampledBytes = 0L;
            var pathSafe = true;
            var compressionSafe = true;
            var seenPaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var sampleBuffer = new byte[8192];

            foreach (var entry in archive.Entries)
            {
                entryCount++;
                if (entryCount > MaximumEntries)
                {
                    findings.Add(new ArchiveSecurityFinding(
                        "error",
                        "archive.entry_count",
                        $"归档条目超过 {MaximumEntries} 个限制。"));
                    break;
                }

                var path = entry.Key ?? string.Empty;
                if (!ValidatePath(path, findings) || !seenPaths.Add(path))
                {
                    pathSafe = false;
                    if (!seenPaths.Add(path))
                    {
                        findings.Add(new ArchiveSecurityFinding(
                            "error",
                            "archive.duplicate_path",
                            "归档包含大小写不敏感的重复路径。",
                            path));
                    }
                }

                if (entry.IsEncrypted)
                {
                    encryptedCount++;
                    findings.Add(new ArchiveSecurityFinding(
                        "warning",
                        "archive.encrypted_entry",
                        "归档包含加密条目，无法在无密码模式下完整检查其内容。",
                        path));
                }

                if (entry.IsDirectory)
                {
                    continue;
                }

                fileCount++;
                if (ExecutableExtensions.Contains(Path.GetExtension(path)))
                {
                    executableCount++;
                    findings.Add(new ArchiveSecurityFinding(
                        "warning",
                        "archive.executable_entry",
                        "归档包含可执行或脚本文件，请确认来源和用途。",
                        path));
                }

                if (entry.Size < 0 || entry.Size > MaximumSingleEntryBytes)
                {
                    compressionSafe = false;
                    findings.Add(new ArchiveSecurityFinding(
                        "error",
                        "archive.entry_size",
                        "归档单个文件展开大小超过安全限制。",
                        path));
                    continue;
                }

                expandedBytes = checked(expandedBytes + entry.Size);
                if (expandedBytes > MaximumExpandedBytes)
                {
                    compressionSafe = false;
                    findings.Add(new ArchiveSecurityFinding(
                        "error",
                        "archive.expanded_size",
                        "归档总展开大小超过 1 GiB 安全限制。",
                        path));
                }

                var compressedSize = Math.Max(1, entry.CompressedSize);
                if (entry.Size >= 1024 && (double)entry.Size / compressedSize > MaximumCompressionRatio)
                {
                    compressionSafe = false;
                    findings.Add(new ArchiveSecurityFinding(
                        "error",
                        "archive.compression_ratio",
                        "归档条目压缩比超过 100 倍安全限制。",
                        path));
                }

                if (entry.IsEncrypted || sampledBytes >= MaximumSampleBytes)
                {
                    continue;
                }

                try
                {
                    using var stream = entry.OpenEntryStream();
                    var target = Math.Min(64 * 1024, MaximumSampleBytes - sampledBytes);
                    long entrySampled = 0;
                    while (entrySampled < target)
                    {
                        var read = stream.Read(
                            sampleBuffer,
                            0,
                            (int)Math.Min(sampleBuffer.Length, target - entrySampled));
                        if (read == 0)
                        {
                            break;
                        }
                        entrySampled += read;
                        sampledBytes += read;
                    }
                }
                catch (Exception exception) when (exception is InvalidDataException or IOException)
                {
                    findings.Add(new ArchiveSecurityFinding(
                        "error",
                        "archive.entry_unreadable",
                        "归档条目无法读取，可能已损坏或使用了不兼容的压缩方法。",
                        path));
                }
            }

            var summary = new ArchiveSecuritySummary(
                entryCount,
                fileCount,
                expandedBytes,
                sampledBytes,
                encryptedCount,
                executableCount,
                pathSafe,
                compressionSafe);
            return CreateReport(selected, archiveSha256, format, summary, findings);
        }
        catch (Exception exception) when (exception is InvalidDataException or IOException or NotSupportedException)
        {
            findings.Add(new ArchiveSecurityFinding(
                "error",
                "archive.invalid",
                "归档格式无效、已损坏或当前检查器不支持。"));
            return CreateReport(
                selected,
                archiveSha256,
                format,
                new ArchiveSecuritySummary(0, 0, 0, 0, 0, 0, false, false),
                findings);
        }
    }

    private static bool ValidatePath(
        string path,
        ICollection<ArchiveSecurityFinding> findings)
    {
        var normalized = path.Replace('\\', '/');
        if (string.IsNullOrWhiteSpace(path)
            || path.Length > 512
            || path.Contains(':')
            || normalized.StartsWith('/')
            || normalized.Split('/', StringSplitOptions.RemoveEmptyEntries)
                .Any(segment => segment is "." or ".."))
        {
            findings.Add(new ArchiveSecurityFinding(
                "error",
                "archive.unsafe_path",
                "归档包含绝对路径或路径穿越条目。",
                path));
            return false;
        }
        return true;
    }

    private static string GetFormat(string fileName)
    {
        var lower = fileName.ToLowerInvariant();
        return lower.EndsWith(".tar.gz") || lower.EndsWith(".tgz")
            ? "tgz"
            : lower.EndsWith(".tar.bz2") || lower.EndsWith(".tbz2")
                ? "tbz2"
                : Path.GetExtension(lower).TrimStart('.') switch
                {
                    "7z" => "7z",
                    "rar" => "rar",
                    "tar" => "tar",
                    "gz" => "gz",
                    "bz" or "bz2" => "bz2",
                    "zip" => "zip",
                    _ => "unknown",
                };
    }

    private static ArchiveSecurityReport CreateReport(
        PluginSelectedFile selected,
        string archiveSha256,
        string format,
        ArchiveSecuritySummary summary,
        IReadOnlyList<ArchiveSecurityFinding> findings)
    {
        var status = findings.Any(item => item.Severity == "error")
            ? "failed"
            : findings.Any(item => item.Severity == "warning")
                ? "warning"
                : "passed";
        var returned = findings.Take(MaximumReturnedFindings).ToArray();
        return new ArchiveSecurityReport(
            status,
            selected.FileName,
            format,
            selected.Length,
            archiveSha256,
            summary,
            findings.Count,
            findings.Count > returned.Length,
            returned);
    }
}
